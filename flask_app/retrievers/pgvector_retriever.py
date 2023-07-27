from langchain.vectorstores.base import VectorStoreRetriever
from langchain.schema import Document
from langchain.vectorstores.pgvector import PGVector
from typing import List, Dict, Tuple
import os
import copy
import ast
from .tools import load_json_file
from .base import Retriever, INDEX_PATH

class PGVectorRetriever(Retriever):
    index_type: str = 'pgvector'
    index_config_path: str = os.path.join(INDEX_PATH, index_type, 'index_config.json')
    
    # Parameters from the program_info to use in the metadata filter for queries
    filter_params: List[str]
    # Maximum number of documents to return
    k: int
    
    def __init__(self, connection_string: str, filter_params = []):
        """
        Initialize the RDS PGvector retriever
        - connection_string: connection string for the pgvector DB
                             can be created using PGVector.connection_string_from_db_params
        - filter_params:
                 keys of entries in the program_info dict passed
                 to semantic_search that should be used as a metadata
                 filter when querying pinecone
        """
        self.filter_params = filter_params
        
        # Load the config file
        index_config = load_json_file(self.index_config_path)
        
        # Load the dense embedding model
        embeddings_model = self._embeddings_model_from_config(index_config)
        self.num_embed_concats = len(index_config['embeddings'])
        
        # Connect to the pgvector db
        db = PGVector.from_existing_index(embeddings_model, index_config['name'], connection_string=connection_string)
        self.retriever = VectorStoreRetriever(vectorstore=db)
    
    def semantic_search(self, program_info: Dict, topic: str, query: str, k = 5, threshold = 0) -> List[Document]:
        """
        Return the documents from similarity search with the given context and query
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        - k: number of documents to return
        - threshold: relevance threshold, all returned documents must surpass the threshold
                     relevance is cosine-similarity based, so ranges between 0 and 1
                     larger scores indicate greater relevance
        """
        self.set_top_k(k)
        query_str, kwargs = self._query_converter(program_info,topic,query)
        
        if threshold > 0:
            self.retriever.search_type = "similarity_score_threshold"
            self.retriever.search_kwargs['score_threshold'] = threshold
        else:
            self.retriever.search_type = 'similarity'
            
        docs = self.retriever.get_relevant_documents(query_str,**kwargs)
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
        self.retriever.search_kwargs['k'] = k
        
    def _query_converter(self, program_info: Dict, topic: str, query: str) -> Tuple[str,Dict]:
        """
        Generates a text query and keyword args for the retriever from the input
        - program_info: Dict of program information
        - topic: keyword topic of the query
        - query: the full query question
        Returns:
        - Tuple of the query string, and Dict of kwargs to pass to the retriever
        """
        # Create a filter from the program info
        program_info_copy = copy.copy(program_info)
        filter = {}
        for param in self.filter_params:
            if param in program_info:
                filter[param] = program_info[param]
                program_info_copy.pop(param)

        self.retriever.search_kwargs['filter'] = filter
        
        query_str = ' : '.join(list(program_info_copy.values()) + [topic,query])
        return self._retriever_combined_query(query_str), {}
    
    def _response_converter(self, response: List[Document]) -> List[Document]:
        """
        Decode the document metadatas from rds
        Since rds requires primitive datatypes for metadatas,
        evaluates strings into dicts/arrays
        """
        decode_columns = ['titles','parent_titles','links']
        for doc in response:
            for column in decode_columns:
                doc.metadata[column] = ast.literal_eval(doc.metadata[column])
            doc.page_content = doc.metadata['text']

        return response