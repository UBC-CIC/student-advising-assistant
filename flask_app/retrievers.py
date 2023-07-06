"""
Functions relating to the document embeddings, indexes, and retrievers
"""
from langchain.vectorstores import FAISS
from langchain.embeddings.base import Embeddings
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores.base import VectorStoreRetriever
from langchain.schema import Document
from typing import List, Dict
import json
import copy
from combined_embeddings import CombinedEmbeddings
import os

FACULTIES_PATH = os.path.join('data','documents','faculties.txt')
INDEXES_PATH = os.path.join('data','indexes')
DOCS_PATH = os.path.join('data','documents','website_extracts.csv')

def load_json_file(file: str):
    with open(file,'r') as f: 
        return json.load(f)
    
index_config = load_json_file(f'{INDEXES_PATH}/index_config.json')
base_embeddings = HuggingFaceEmbeddings(model_name=index_config['base_embedding_model'],model_kwargs={'device': 'cpu'})
indexes: Dict = {}
retrievers: Dict = {}
query_converters: Dict = {}

def load_faculties():
    """
    Load the available faculties from json
    """
    with open(FACULTIES_PATH,'r') as f:
        return json.load(f)
    
def load_retriever_from_faiss(path: str, embedding_model: Embeddings):
    """
    Load a retriever from a previously saved FAISS index
    - path: filepath to the saved FAISS index
    - embedding_model: embedding model used for the index
    """
    faiss = FAISS.load_local(path, embedding_model)
    retriever = VectorStoreRetriever(vectorstore=faiss)
    retriever.search_kwargs = {'k':5}
    return faiss,retriever
    
def load_retrievers():
    """
    Load retrievers as defined in index_config.json from the s3 bucket
    """
    for name, i_config in index_config['indexes'].items():
        index_path = os.path.join(INDEXES_PATH,name)
        embeddings_model = CombinedEmbeddings(base_embeddings, len(i_config['embeddings']))
        faiss,retriever = load_retriever_from_faiss(index_path,embeddings_model)
        indexes[name] = faiss
        retrievers[name] = retriever
        query_converters[name] = lambda context, query: retriever_combined_query([context + ':' + query, context + ':' + query, context + ':' + query])

def docs_from_ids(doc_ids: List[int], retriever_name: str):
    """
    Return a list of documents from a list of document indexes
    """
    docs = []
    retriever = retrievers[retriever_name]
    for doc_id in doc_ids:
        id = retriever.vectorstore.index_to_docstore_id[doc_id]
        docs.append(retriever.vectorstore.docstore.search(id))
    return [copy.deepcopy(doc) for doc in docs]

def retriever_context_str(program_info: Dict, topic: str, retriever_name: str):
    """
    Create a context string for a retriever
    - program_info: Dict of faculty and program information
    - topic: Topic of the query
    - retriever_name: Name of the retriever to prepare context for
    Information included from the program_info may be different depending on the retriever
    """
    program_info_copy = copy.copy(program_info)
    
    if 'faculty' in index_config['indexes'][retriever_name]:
        # Ignore faculty in context if the retriever is already for a particular faculty
        program_info_copy.pop('faculty',None)
        program_info_copy.pop('program',None)
        
    return ' : '.join(list(program_info_copy.values()) + [topic])

def retriever_combined_query(args: List[str]):
    """
    Combine all args into a single query separated by the separation character
    """
    joined = CombinedEmbeddings.query_separator.join(args)
    return joined

async def get_documents(context: str, query: str, retriever_name: str, k = 5) -> List[Document]:
    """
    Return the documents from similarity search with the given context and query
    - context: Text that describes the topic or other context of the query
    - query: The question to answer
    - k: number of documents to return
    """
    retriever = retrievers[retriever_name]
    retriever.search_kwargs = {'k':k}
    combined_query = query_converters[retriever_name](context,query)
    docs = retriever.get_relevant_documents(combined_query)
    return [copy.deepcopy(doc) for doc in docs]

def choose_retriever(context: str | Dict) -> str:
    """
    Choose the right document retriever based on the context
    If the context includes a faculty and the faculty retrievers are loaded,
    returns the name of the associated retriever
    """
    if type(context) == dict and 'faculty' in context and context['faculty'] in retrievers:
        return context['faculty']
    else: return 'All'