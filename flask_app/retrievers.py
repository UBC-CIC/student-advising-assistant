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
    for i_config in index_config['indexes']:
        index_path = os.path.join(INDEXES_PATH,i_config['name'])
        embeddings_model = CombinedEmbeddings(base_embeddings, len(i_config['embeddings']))
        faiss,retriever = load_retriever_from_faiss(index_path,embeddings_model)
        indexes[i_config['name']] = faiss
        retrievers[i_config['name']] = retriever
        query_converters[i_config['name']] = lambda context, query: retriever_combined_query([query,query,query])

def docs_from_ids(doc_ids: List[int], retriever: VectorStoreRetriever = None):
    """
    Return a list of documents from a list of document indexes
    """
    docs = []
    if not retriever: retriever = retrievers['All']
    for doc_id in doc_ids:
        id = retriever.vectorstore.index_to_docstore_id[doc_id]
        docs.append(retriever.vectorstore.docstore.search(id))
    return [copy.deepcopy(doc) for doc in docs]

def retriever_context_str(context: str | Dict):
    """
    Convert a context string or dict to a string for the document retriever
    """
    context_str = context
    if type(context) == dict:
        context_str = ' : '.join(context.values())
    return context_str

def retriever_combined_query(args: List[str]):
    """
    Combine all args into a single query separated by the separation character
    """
    joined = CombinedEmbeddings.query_separator.join(args)
    print(joined)
    return joined

async def get_documents(context,query,k=None,retriever_name=None) -> List[Document]:
    """
    Return the documents from similarity search with the given context and query
    - k: number of documents to return
    """
    if not retriever_name: retriever_name = choose_retriever(context)
    retriever = retrievers[retriever_name]
    
    if k: retriever.search_kwargs = {'k':k}
    context_str = retriever_context_str(context)
    combined_query = query_converters[retriever_name](context_str,query)
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