from langchain.vectorstores import FAISS
from langchain.vectorstores.base import VectorStoreRetriever
from langchain.schema import Document
from typing import List, Dict, Tuple
import copy
import os
from .tools import load_json_file
from .base import Retriever

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
        raise NotImplemented()
    
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