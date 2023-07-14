"""
Functions relating to the document embeddings, indexes, and retrievers
"""
from langchain.vectorstores import FAISS
from langchain.embeddings.base import Embeddings
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores.base import VectorStoreRetriever
from langchain.schema import Document, BaseRetriever
from langchain.retrievers import PineconeHybridSearchRetriever
from pinecone_text.sparse import BM25Encoder
import pinecone 
from typing import List, Dict, Callable, Optional, Tuple
import json
import copy
import os
import ast
from abc import ABC, abstractmethod
from combined_embeddings import CombinedEmbeddings

FACULTIES_PATH = os.path.join('data','documents','faculties.txt')
INDEX_PATH = os.path.join('data','indexes')

def load_json_file(file: str):
    with open(file,'r') as f: 
        return json.load(f)

base_embeddings: Dict = {}
retrievers: Dict = {}

class MyPineconeRetriever(PineconeHybridSearchRetriever):
    """
    Wrapper of LangChain PineconeHybridSearchRetriever
    that allows for additional parameters in query,
    and fetching documents by ID
    """
    # Key for the original text in the pinecone document's metadata
    _text_key: str = 'context'
    # Key to place the document similarity score in metadata after retrieval
    _score_key: str = 'score'
    
    def _handle_pinecone_docs(self, vectors: List[dict]) -> List[Document]:
        """
        Convert a list of vectors from a pinecone query or fetch to a list
        of Langchain documents
        """                
        docs = []
        for res in vectors:
            context = res["metadata"].pop(self._text_key)
            doc = Document(page_content=context, metadata=res["metadata"])
            if self._score_key in res: doc.metadata[self._score_key] = res["score"]
            docs.append(doc)
        return docs
        
    def _get_relevant_documents(
        self, 
        query: str, 
        **kwargs
    ) -> List[Document]:
        """
        Adapted from langchain.retrievers.pinecone_hybrid_search, with support for
        additional keyword arguments to the pinecone query.
        Example keyword arguments
        - namespace: pinecone namespace to search in
        - filter: metadata filter to apply in the pinecone call, see
                           https://docs.pinecone.io/docs/metadata-filtering
        The similarity score of each document is placed in the document metadata
        under the 'score' key.
        """
        
        from pinecone_text.hybrid import hybrid_convex_scale

        sparse_vec = self.sparse_encoder.encode_queries(query)
        # convert the question into a dense vector
        dense_vec = self.embeddings.embed_query(query)
        # scale alpha with hybrid_scale
        dense_vec, sparse_vec = hybrid_convex_scale(dense_vec, sparse_vec, self.alpha)
        sparse_vec["values"] = [float(s1) for s1 in sparse_vec["values"]]
        # query pinecone with the query parameters
        print(kwargs['filter'])
        response = self.index.query(
            vector=dense_vec,
            sparse_vector=sparse_vec,
            top_k=self.top_k,
            include_metadata=True,
            **kwargs
        )
        return self._handle_pinecone_docs(response["matches"])
    
    def fetch_by_id(self, ids: List[int], namespace: Optional[str] = None):
        """
        Fetch a set of documents by ids
        """
        ids = [str(id) for id in ids]
        response = self.index.fetch(ids=ids, namespace=namespace)
        return self._handle_pinecone_docs(response['vectors'].values())
    
class Retriever(ABC):
    """
    Wrapper class for a LangChain retriever that performs additional
    query and response conversion
    """
    retriever: BaseRetriever
    
    @abstractmethod
    def semantic_search(self, program_info: Dict, topic: str, query: str, k = 5, threshold = 0) -> List[Document]:
        """
        Return the documents from similarity search with the given context and query
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        - k: number of documents to return
        - threshold: relevance threshold, all returned documents must surpass the threshold
                     the threshold range depends on the scoring function of the chosen retriever
        """
        pass
    
    @abstractmethod
    def docs_from_ids(self, doc_ids: List[int]) -> List[Document]:
        """
        Return a list of documents from a list of document indexes
        """
        pass
    
    @abstractmethod
    def set_top_k(self, k: int):
        """
        Set the retriever's 'top k' parameter, determines how many
        documents to return from semantic search
        """
        pass

    @classmethod
    def _load_base_embedding(cls, name: str):
        if name in base_embeddings:
            return base_embeddings[name]
        else:
            model = HuggingFaceEmbeddings(model_name=name, model_kwargs={'device': 'cpu'})
            base_embeddings[name] = model
        return base_embeddings[name]
    
    @classmethod
    def _embeddings_model_from_config(cls, index_config: Dict):
        # Load the base embeddings model
        base_embeddings = cls._load_base_embedding(index_config['base_embedding_model'])
        
        # Get the number of embeddings to concatenate
        n = len(index_config['embeddings']) 
        
        # Create combined model if necessary
        embedding_model = base_embeddings
        if n > 1:
            embedding_model = CombinedEmbeddings(base_embeddings, n)
        
        return embedding_model
    
    @classmethod
    def _retriever_combined_query(cls, args: List[str]):
        """
        Combine all args into a single query separated by the separation character
        """
        joined = CombinedEmbeddings.query_separator.join(args)
        return joined

    @abstractmethod
    def _query_converter(self, program_info: Dict, topic: str, query: str) -> Tuple[str,Dict]:
        """
        Generates a text query and keyword args for the retriever from the input
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        Returns:
        - Tuple of the query string, and Dict of metadata to pass to the retriever
        """
        pass
    
    @abstractmethod
    def _response_converter(self, response: List[Document]) -> List[Document]:
        """
        Performs any necessary postprocessing on the returned documents from the retriever
        """
        pass

class PineconeRetriever(Retriever):
    index_type: str = 'pinecone'
    index_config_path: str = os.path.join(INDEX_PATH, index_type, 'index_config.json')
    bm25_weights_path: str = os.path.join(INDEX_PATH, index_type, 'bm25_params.json')
    
    # Parameters from the program_info to use in the metadata filter for queries
    filter_params: List[str]
    # Namespace to use for all queries to the pinecone index
    namespace: Optional[str] 
    
    def __init__(self, pinecone_key: str, pinecone_region: str, alpha = 0.4, filter_params = []):
        """
        Initialize the pinecone retriever
        - pinecone_key: API key for pinecone
        - pinecone_region: region for the pinecone index
        - alpha: weighting of the sparse vs dense vectors
                 0 = pure semantic search (dense vectors)
                 1 = pure keyword search (sparse vectors)
        - filter_params:
                 keys of entries in the program_info dict passed
                 to semantic_search that should be used as a metadata
                 filter when querying pinecone
        """
        self.filter_params = filter_params
        
        # Load the config file
        index_config = load_json_file(self.index_config_path)
        
        # Load the sparse vector model
        bm25_encoder = BM25Encoder().load(self.bm25_weights_path)
        
        # Load the dense embedding model
        embeddings_model = self._embeddings_model_from_config(index_config)
        
        # Connect to the pinecone index
        pinecone.init(      
            api_key=pinecone_key,      
            environment=pinecone_region     
        )     
        index = pinecone.Index(index_config['name'])
        self.namespace = index_config['namespace']
        
        # Create the retriever
        hybrid_retriever = MyPineconeRetriever(
            embeddings=embeddings_model, sparse_encoder=bm25_encoder, index=index
        )
        hybrid_retriever.alpha = alpha
        self.retriever = hybrid_retriever
    
    def semantic_search(self, program_info: Dict, topic: str, query: str, k = 5, threshold = 0) -> List[Document]:
        """
        Return the documents from similarity search with the given context and query
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        - k: number of documents to return
        - threshold: relevance threshold, all returned documents must surpass the threshold
                     relevance is dot-product based, so not normalized
                     larger scores indicate greater relevance
        """
        self.set_top_k(k)
        query_str, kwargs = self._query_converter(program_info,topic,query)
        if self.namespace: kwargs['namespace'] = self.namespace
        docs = self.retriever.get_relevant_documents(query_str,**kwargs)
        #docs = self._apply_score_threshold(docs, threshold)
        return self._response_converter(docs)
    
    def docs_from_ids(self, doc_ids: List[int]) -> List[Document]:
        """
        Return a list of documents from a list of document indexes
        """
        docs = self.retriever.fetch_by_id(doc_ids, self.namespace)
        return self._response_converter(docs)
    
    def set_top_k(self, k: int):
        """
        Set the retriever's 'top k' parameter, determines how many
        documents to return from semantic search
        """
        self.retriever.top_k = k
        
    def _query_converter(self, program_info: Dict, topic: str, query: str) -> Tuple[str,Dict]:
        """
        Generates a text query and keyword args for the retriever from the input
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        Returns:
        - Tuple of the query string, and Dict of metadata to pass to the retriever
        """
        # Create a filter from the program info
        program_info_copy = copy.copy(program_info)
        filter = {}
        for param in self.filter_params:
            if param in program_info:
                filter[param] = {"$eq": program_info[param]}
                program_info_copy.pop(param)

        query_str = ' : '.join(list(program_info_copy.values()) + [topic,query])
        return self._retriever_combined_query([query_str, query_str, query_str]), {'filter': filter}
    
    def _response_converter(self, response: List[Document]) -> List[Document]:
        """
        Decode the document metadatas from pinecone
        Since pinecone requires primitive datatypes for metadatas,
        evaluates strings into dicts/arrays
        """
        decode_columns = ['titles','parent_titles','links']
        for doc in response:
            for column in decode_columns:
                doc.metadata[column] = ast.literal_eval(doc.metadata[column])
            doc.page_content = doc.metadata['text']

        return response
    
    def _apply_score_threshold(self, docs: List[Document], threshold) -> List[Document]:
        """
        Filters out documents that do not meet the similarity score threshold
        Assumes the similarity score is in document metadata 'score' key
        - docs: List of documents to filter
        - threshold: relevance threshold, all returned documents must surpass the threshold
                     relevance is in the range [0,1] where 0 is dissimilar, and 1 is most similar
        """
        return [doc for doc in docs if doc.metadata['score'] >= threshold]
    
class FaissRetriever(Retriever):
    def __init__(self, path: str):
        """
        Load a retriever from a previously saved FAISS index
        - path: filepath to the saved FAISS index
        """
        index_config = load_json_file(os.path.join(path,'index_config.json'))
        
        # Check if index is for a particular faculty
        faculty = None
        if 'faculty' in index_config: faculty = index_config['faculty']
        self.faculty = faculty
        
        # Load embedings model
        embeddings_model = self._embeddings_model_from_config(index_config)
        
        # Create the retriever
        faiss = FAISS.load_local(path, embeddings_model)
        self.retriever = VectorStoreRetriever(vectorstore=faiss)

    def semantic_search(self, program_info: Dict, topic: str, query: str, k = 5, threshold = 0) -> List[Document]:
        """
        Return the documents from similarity search with the given context and query
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        - k: number of documents to return
        - threshold: relevance threshold, all returned documents must surpass the threshold
                     relevance is in the range [0,1] where 0 is dissimilar, and 1 is most similar
        """
        self.set_top_k(k)
        query_str, kwargs = self._query_converter(program_info,topic,query)
        self.retriever.search_type = 'similarity_search_with_relevance_scores'
        docs = self.retriever.get_relevant_documents(query_str,score_threshold=threshold,**kwargs)
        return self._response_converter(docs)
    
    def docs_from_ids(self, doc_ids: List[int]) -> List[Document]:
        """
        Return a list of documents from a list of document indexes
        """
        docs = []
        for doc_id in doc_ids:
            id = self.retriever.vectorstore.index_to_docstore_id[doc_id]
            docs.append(self.retriever.vectorstore.docstore.search(id))
        return [copy.deepcopy(doc) for doc in docs]
    
    def set_top_k(self, k: int):
        """
        Set the retriever's 'top k' parameter, determines how many
        documents to return from semantic search
        """
        self.retriever.search_kwargs = {'k':k}
        
    def _query_converter(self, program_info: Dict, topic: str, query: str) -> Tuple[str,Dict]:
        """
        Generates a text query and keyword args for the retriever from the input
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        Returns:
        - Tuple of the query string, and Dict of metadata to pass to the retriever
        """
        program_info_copy = copy.copy(program_info)
    
        if self.faculty:
            # Ignore faculty in context if the retriever is already for a particular faculty
            program_info_copy.pop('faculty',None)
            program_info_copy.pop('program',None)
            
        query_str = ' : '.join(list(program_info.values()) + [topic,query])
        return self.retriever_combined_query([query_str, query_str, query_str]), {}  
      
    def _response_converter(self, response: List[Document]) -> List[Document]:
        """
        Since FAISS is an in-memory vectorstore, deepcopy the documents so
        that they can be modified without modifying the docstore
        """
        return [copy.deepcopy(doc) for doc in response]

def load_faculties():
    """
    Load the available faculties from json
    """
    with open(FACULTIES_PATH,'r') as f:
        return json.load(f)

def load_faiss_retrievers():
    """
    Load faiss retrievers from file
    """
    faiss_path = os.path.join(INDEX_PATH, 'faiss')
    
    for dirname in os.listdir(faiss_path):
        retriever = FaissRetriever(dirname)
        retrievers[dirname] = retriever