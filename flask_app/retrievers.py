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
import pathlib
import pickle
from doc_loader import load_docs

FAISS_TITLE_PATH = './data/faiss-title'
FAISS_DOUBLE_PATH = './data/faiss-double'
FAISS_TRIPLE_PATH = './data/faiss-triple'
FACULTIES_PATH = './data/faculties.txt'
EMBEDDINGS_PATH = './data/embeddings'
BASE_EMBEDDING_MODEL = 'sentence-transformers/all-mpnet-base-v2'
#BASE_EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
DOCS_PATH = '../document_scraping/processed/website_extracts.csv'

class CombinedEmbeddings(Embeddings):
    """
    Embeddings wrapper class that combines precomputed embeddings
    into concatenated embeddings
    """

    query_separator: str = '|'

    def __init__(self, base_model: Embeddings, d: int):
        """
        - base_model: the base embeddings model
        - d: number of embeddings to concatenate
        """
        self.base_model = base_model
        self.d = d

    def concat_embeddings(self, embeddings: List[List[List[float]]]) -> List[List[float]]:
        """
        Create a list of concatenated embeddings from a list of embeddings
        - embeddings: List of precomputed embeddings (d x n x e) 
                        - d is the number of different embeddings
                        - n is the number of documents
                        - e is the embedding dimension
        Outputs a list of embeddings concatenated by document, (n x (d*e))
        """
        assert(len(embeddings) == self.d)
        return [sum(embed_list,[]) for embed_list in zip(*embeddings)]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Not implemented and not necessary for this purpose since
        we are loading precomputed embeddings
        Function included for the LangChain Embedding interface
        """
        return []

    def embed_query(self, text: str) -> List[float]:
        """
        Embed query text.
        If text split by the query_separator has dimension d,
        concatenates embeddings for each split portion
        Otherwise, concatenates entire text and concatenates to
        itself d times
        """
        texts = text.split(self.query_separator)
        if len(texts) == self.d:
            query_embeds = [self.base_model.embed_query(text_split) for text_split in texts]
            return sum(query_embeds,[])
        else:
            query_embed = self.base_model.embed_query(text)
            return sum([query_embed for _ in range(self.d)],[])
        
base_embeddings = HuggingFaceEmbeddings(model_name=BASE_EMBEDDING_MODEL,model_kwargs={'device': 'cpu'})
embeddings: Dict = {}
indexes: Dict = {}
retrievers: Dict = {}
query_converters: Dict = {}

def load_faculties():
    """
    Load the available faculties from json
    """
    with open(FACULTIES_PATH,'r') as f:
        return json.load(f)
        
def load_embeddings(embeddings_dir: str):
    """
    Load all pickled embeddings in the given directory path
    """
    for file in pathlib.Path(embeddings_dir).glob('*.pkl'):
        with open(file, "rb") as f:
            data = pickle.load(f)
            embeddings[file.stem] = data['embeddings']

def load_retriever_from_embeddings(embedding_names: List[str], doc_contents: List[str], doc_metadatas: List[Dict], doc_ids: List[int]):
    """
    Create a retriever that indexes concatenated embeddings
    Creates concatenation of the embeddings specified by name in 'embedding_names'
    """
    d = len(embedding_names)
    combined_embeddings_model = CombinedEmbeddings(base_embeddings,d)
    combined_embeddings = combined_embeddings_model.concat_embeddings([embeddings[name] for name in embedding_names])
    faiss = FAISS.from_embeddings(list(zip(doc_contents,combined_embeddings)), 
                                  combined_embeddings_model, doc_metadatas, doc_ids)
    retriever = VectorStoreRetriever(vectorstore=faiss)
    retriever.search_kwargs = {'k':5}
    return faiss,retriever
    
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

def load_retrievers_from_faiss(by_faculty:bool = False):
    """
    Loads retrievers from saved FAISS indexes
    - by_faculty: if true, loads an index for each faculty 
    """
    global indexes, retrievers
    embeddings_model = CombinedEmbeddings(base_embeddings, 3)
    indexes = {}
    retrievers = {}
    if by_faculty:
        faculties = load_faculties()
        for name in faculties.keys():
            path = f'{FAISS_TRIPLE_PATH}/{name}'
            faiss,retriever = load_retriever_from_faiss(path,embeddings_model)
            indexes[name] = faiss
            retrievers[name] = retriever

    faiss,retriever = load_retriever_from_faiss(FAISS_TRIPLE_PATH,embeddings_model)
    indexes['All'] = faiss
    retrievers['All'] = retriever

def load_retrievers_from_embeddings():
    """
    Loads retrievers by combining precomputed embeddings
    Loads the following retrievers:
    - 'triple': concatenation of parent titles, titles, and page content embeddings
    - 'titles': concatenation of parent titles and titles embeddings
    """
    load_embeddings(EMBEDDINGS_PATH)
    docs: List[Document] = load_docs(DOCS_PATH)
    doc_contents: List[str] = [doc.page_content for doc in docs]
    doc_metadatas: List[Dict] = [doc.metadata for doc in docs]
    doc_ids: List[int] = [doc.metadata['doc_id'] for doc in docs]
    
    faiss, retriever = load_retriever_from_embeddings(['parent_title_embeddings','title_embeddings','document_embeddings'],
                                                      doc_contents, doc_metadatas, doc_ids)
    indexes['triple'] = faiss
    retrievers['triple'] = retriever
    query_converters['triple'] = lambda context, query: retriever_combined_query([context, context, query])
    
    faiss, retriever = load_retriever_from_embeddings(['parent_title_embeddings','title_embeddings'],
                                                      doc_contents, doc_metadatas, doc_ids)
    indexes['titles'] = faiss
    retrievers['titles'] = retriever
    query_converters['titles'] = lambda context, _: retriever_combined_query([context, context])

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
    return CombinedEmbeddings.query_separator.join(args)

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