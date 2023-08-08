from langchain.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document, BaseRetriever
from typing import List, Dict, Tuple
import os
from abc import ABC, abstractmethod
from embeddings import CombinedEmbeddings

### Constants
INDEX_PATH = os.path.join('data','indexes')

### Globals
# Stores the base embedding model to be shared between retriever(s)
base_embeddings = {}

### Interface
class Retriever(ABC):
    """
    Wrapper class for a LangChain retriever that performs additional
    query and response conversion
    """
    # The retriever being wrapped
    retriever: BaseRetriever
    # Number of concatenated embeddings
    # Used to prepare query embeddings for retrieval
    num_embed_concats: int
    # Set the retriever to verbose mode
    verbose: bool
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        
    @abstractmethod
    def semantic_search(self, filter: Dict, program_info: Dict, topic: str, query: str, k = 5, threshold = 0) -> List[Document]:
        """
        Return the documents from similarity search with the given context and query
        - filter: Dict of metadata filter keys and values
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

    def _output_query_verbose(self, query: str, kwargs: dict):
        """
        If in verbose mode, log the query and kwargs to console
        """
        if self.verbose:
            print(f"Querying {self.index_type} retriever: '{query}', {kwargs}")
            
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
    
    def _retriever_combined_query(self, query: str):
        """
        Concatenate the query with itself as many times as necessary
        For the correct embedding dimensions with the concatenated embeddings
        """
        queries = [query for _ in range(self.num_embed_concats)]
        joined = CombinedEmbeddings.query_separator.join(queries)
        return joined

    @abstractmethod
    def _query_converter(self, filter: Dict, program_info: Dict, topic: str, query: str) -> Tuple[str,Dict]:
        """
        Generates a text query and keyword args for the retriever from the input
        - filter: Dict of metadata filter keys and values
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