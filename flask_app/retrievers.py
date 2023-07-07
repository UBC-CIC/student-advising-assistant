"""
Functions relating to the document embeddings, indexes, and retrievers
"""
from langchain.vectorstores import FAISS
from langchain.embeddings.base import Embeddings
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores.base import VectorStoreRetriever
from langchain.schema import Document, BaseRetriever
from typing import List, Dict, Callable
import json
import copy
from combined_embeddings import CombinedEmbeddings
import os
from langchain.retrievers import PineconeHybridSearchRetriever
from pinecone_text.sparse import BM25Encoder
import pinecone 
import ast
from abc import ABC, abstractmethod

FACULTIES_PATH = os.path.join('data','documents','faculties.txt')
INDEX_PATH = os.path.join('data','indexes')

def load_json_file(file: str):
    with open(file,'r') as f: 
        return json.load(f)

base_embeddings: Dict = {}
retrievers: Dict = {}

class Retriever(ABC):
    """
    Wrapper class for a LangChain retriever that performs additional
    query and response conversion
    """
    retriever: BaseRetriever
    
    def semantic_search(self, program_info: Dict, topic: str, query: str, k = 5) -> List[Document]:
        """
        Return the documents from similarity search with the given context and query
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        - k: number of documents to return
        """
        self.set_top_k(k)
        query_str = self.query_converter(program_info,topic,query)
        docs = self.retriever.get_relevant_documents(query_str)
        return self.response_converter(docs)

    @classmethod
    def load_base_embedding(cls, name: str):
        if name in base_embeddings:
            return base_embeddings[name]
        else:
            model = HuggingFaceEmbeddings(model_name=name, model_kwargs={'device': 'cpu'})
            base_embeddings[name] = model
        return base_embeddings[name]
    
    @classmethod
    def embeddings_model_from_config(cls, index_config: Dict):
        # Load the base embeddings model
        base_embeddings = cls.load_base_embedding(index_config['base_embedding_model'])
        
        # Get the number of embeddings to concatenate
        n = len(index_config['embeddings']) 
        
        # Create combined model if necessary
        embedding_model = base_embeddings
        if n > 1:
            embedding_model = CombinedEmbeddings(base_embeddings, n)
        
        return embedding_model
    
    @classmethod
    def retriever_combined_query(cls, args: List[str]):
        """
        Combine all args into a single query separated by the separation character
        """
        joined = CombinedEmbeddings.query_separator.join(args)
        return joined

    @abstractmethod
    def query_converter(self, program_info: Dict, topic: str, query: str) -> List[Document]:
        """
        Generates a text query for the retriever from the input
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        """
        pass
    
    @abstractmethod
    def response_converter(self, response: List[Document]) -> List[Document]:
        """
        Performs any necessary postprocessing on the returned documents from the retriever
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

class PineconeRetriever(Retriever):
    index_type: str = 'pinecone'
    index_config_path: str = os.path.join(INDEX_PATH, index_type, 'index_config.json')
    bm25_weights_path: str = os.path.join(INDEX_PATH, index_type, 'bm25_params.json')
    
    def __init__(self, alpha = 0.4):
        """
        Initialize the pinecone retriever
        - alpha: weighting of the sparse vs dense vectors
                 0 = pure semantic search (dense vectors)
                 1 = pure keyword search (sparse vectors)
        """
        # Load the config file
        index_config = load_json_file(self.index_config_path)
        
        # Load the sparse vector model
        bm25_encoder = BM25Encoder().load(self.bm25_weights_path)
        
        # Load the dense embedding model
        embeddings_model = self.embeddings_model_from_config(index_config)
        
        # Connect to the pinecone index
        pinecone.init(      
            api_key=os.environ.get('PINECONE_KEY'),      
            environment=os.environ.get('PINECONE_REGION')      
        )     
        index = pinecone.Index(index_config['name'])
        
        # Create the retriever
        hybrid_retriever = PineconeHybridSearchRetriever(
            embeddings=embeddings_model, sparse_encoder=bm25_encoder, index=index
        )
        
        self.retriever = hybrid_retriever
    
    def query_converter(self, program_info: Dict, topic: str, query: str) -> List[Document]:
        """
        Generates a text query for the retriever from the input
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        """
        query_str = ' : '.join(list(program_info.values()) + [topic,query])
        return self.retriever_combined_query([query_str, query_str, query_str])
    
    def response_converter(self, response: List[Document]) -> List[Document]:
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
    
    def docs_from_ids(self, doc_ids: List[int]) -> List[Document]:
        """
        Return a list of documents from a list of document indexes
        """
        raise NotImplementedError()
    
    def set_top_k(self, k: int):
        """
        Set the retriever's 'top k' parameter, determines how many
        documents to return from semantic search
        """
        self.retriever.top_k = k
    
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
        embeddings_model = self.embeddings_model_from_config(index_config)
        
        # Create the retriever
        faiss = FAISS.load_local(path, embeddings_model)
        self.retriever = VectorStoreRetriever(vectorstore=faiss)

    def query_converter(self, program_info: Dict, topic: str, query: str) -> List[Document]:
        """
        Generates a text query for the retriever from the input
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        """
        program_info_copy = copy.copy(program_info)
    
        if self.faculty:
            # Ignore faculty in context if the retriever is already for a particular faculty
            program_info_copy.pop('faculty',None)
            program_info_copy.pop('program',None)
            
        query_str = ' : '.join(list(program_info.values()) + [topic,query])
        return self.retriever_combined_query([query_str, query_str, query_str])  
      
    def response_converter(self, response: List[Document]) -> List[Document]:
        """
        Since FAISS is an in-memory vectorstore, deepcopy the documents so
        that they can be modified without modifying the docstore
        """
        return [copy.deepcopy(doc) for doc in response]
    
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