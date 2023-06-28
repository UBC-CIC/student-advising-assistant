from langchain.docstore.document import Document
from langchain import LLMChain
from langchain.retrievers.document_compressors import LLMChainFilter, LLMChainExtractor
import doc_graph_utils
from comparator import Comparator
import retrievers
from llm_utils import load_huggingface_endpoint, llm_combined_query
import regex as re
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

### LOAD MODELS 
comparator = Comparator(retrievers.base_embeddings)
huggingface_model_names = ['google/flan-t5-xxl','google/flan-ul2','tiiuae/falcon-7b-instruct']
llm, prompt = load_huggingface_endpoint(huggingface_model_names[0])
llm_chain = LLMChain(prompt=prompt, llm=llm)
filter = LLMChainFilter.from_llm(llm)
compressor = LLMChainExtractor.from_llm(llm)
graph = doc_graph_utils.read_graph()
#retrievers.load_retrievers_from_embeddings()
retrievers.load_retrievers_from_faiss(by_faculty=True)

def print_results(results: List[Document], print_content=False):
    """
    Debug function to display a list of documents
    """
    for doc in results:
        print()
        print(doc.metadata['titles'])
        print(f"- {doc.metadata['doc_id']}")
        print(f"- {doc.metadata['parent_titles']}")
        print(f"- {doc.metadata['url']}")
        if print_content: print(f"- {doc.page_content}")

def get_related_links_from_compressed(docs, compressed_docs):
    """
    For each document, adds to the metadata a list of links that are contained in the compressed version of the doc
    """
    for doc, compressed in zip(docs, compressed_docs):
        links = [(title,link,doc_id) for title,(link,doc_id) in doc.metadata['links'].items() if title in compressed.page_content]
        doc.metadata['related_links'] = links

def get_related_links_from_sim(context, query, docs, score_threshold = 0.5):
    """
    Searches through links in the given documents:
    - Computes similarity between the query and the link text
    - If the similarities are over the threshold, adds the links to the document metadata
    """
    titles = []
    spans = []
    context_str = retrievers.retriever_context_str(context)

    # Finding linked docs
    for doc in docs:
        spans.append([len(titles)])
        for title,(link,_) in doc.metadata['links'].items():
            if type(link) == int: # only consider links to internal documents
                titles.append(title)
        spans[-1].append(len(titles))

    if len(titles) == 0:
        return [],[]
    
    # Score the query against the link titles
    scores = comparator.compare_query_to_texts(query,titles,context_str)[0]
    
    for doc,span in zip(docs,spans):
        scores_span = scores[span[0]:span[1]]
        links = [(title,link,doc_id) for (title,(link,doc_id)),score in zip(doc.metadata['links'].items(),scores_span) if score >= score_threshold]
        doc.metadata['related_links'] = links

def get_related_docs(context, query, docs, child_docs = False, sib_docs = False, score_threshold = 0.5) -> List[Document]:
    """
    Searches through documents related to the given documents:
    - Gets immediate children and/or siblings
    - Computes similarity between the query and the related document's title
    - Returns documents with similarity over the threshold
    """
    candidate_doc_ids = set()
    doc_ids = [doc.metadata['doc_id'] for doc in docs]
    context_str = retrievers.retriever_context_str(context)

    # Finding related doc ids
    for doc_id in doc_ids:
        if child_docs: candidate_doc_ids.update(doc_graph_utils.get_doc_child_ids(graph, doc_id))
        if sib_docs: candidate_doc_ids.update(doc_graph_utils.get_doc_sib_ids(graph, doc_id))

    if len(candidate_doc_ids) == 0:
        return []
    
    # Fetching related docs
    candidate_docs = retrievers.docs_from_ids(candidate_doc_ids)

    # Score the query against the doc titles
    scores = comparator.compare_query_to_texts(query,[' : '.join(doc.metadata['titles']) for doc in candidate_docs],context_str)[0]

    related_docs = [doc for (score,doc) in sorted(zip(scores,candidate_docs), key=lambda x: x[0]) 
                      if score >= score_threshold and doc.metadata['doc_id'] not in doc_ids]

    return related_docs

def combine_sib_docs(docs) -> List[Document]:
    """
    For each document, combine its context with all of its immediate siblings
    """
    for doc in docs:
        sib_ids = doc_graph_utils.get_split_sib_ids(graph, doc.metadata['doc_id'])
        sib_docs = retrievers.docs_from_ids(sib_ids)
        combined_content = ' '.join([sib_doc.page_content for sib_doc in sib_docs])
        doc.page_content = combined_content
        doc.metadata['titles'] = doc.metadata['titles'][:-1]

def add_italics(text):
    """
    Add italics markings around every line of the text
    """
    for match in re.finditer('[\w\d][^\n\*]+[\w\d]',text):
        text = text.replace(match.group(),f"*{match.group()}*")
    return text
    
async def run_chain(context: str | Dict, query:str, start_doc:int=None, related:bool=False,
                    combine_with_sibs:bool=False, filter:bool=False, compress:bool=True, generate:bool=True):

    """
    Run the question answering chain with the given context and query
    - context: A string or dict describing the context of the query, eg. values describe the faculty and program
    - query: The text query
    - start_doc: If provided, will start searching with the provided document index rather than performing similarity search
    - related: If true, fetches related documents with high enough cosine similarity
    - combine_with_sibs: If true, combines all documents with their immediate sibling documents
    - filter: If true, applies a LLM filter step to the retrieved documents to remove irrelevant documents
    - compress: If true, applies a LLM compres step to compress documents, extracting relevant sections
    - generate: If true, generates a response for each final document
    """

    retriever = retrievers.choose_retriever(context)
    
    docs = None
    if start_doc:
        docs = retrievers.docs_from_ids([start_doc])
    else:
        docs = await retrievers.get_documents(retriever,context,query)

    if related: 
        related_docs = get_related_docs(retriever,context,query,docs,score_threshold=0.3)
        docs += related_docs

    if combine_with_sibs: combine_sib_docs(retriever,context,query,docs)

    if filter: docs = filter.compress_documents(docs, llm_combined_query(context,query))

    compressed_docs = None
    if compress: 
        compressed_docs = compressor.compress_documents(docs, llm_combined_query(context,query))
        get_related_links_from_compressed(docs, compressed_docs)

    for idx,doc in enumerate(docs):
        print(idx)
        if compress:
            compressed_content = compressed_docs[idx].page_content
            compressed_re = re.escape(compressed_content).replace('\ ','(\s|\n)*')
            if match := re.search(compressed_re, doc.page_content):
                # highlight the compressed section
                doc.page_content.replace('*','-')
                new = add_italics(match.group())
                doc.page_content = doc.page_content.replace(match.group(), new)

        # Handle documents starting with a list item
        doc.page_content = doc.page_content.strip()
        if doc.page_content.startswith('*'): doc.page_content = '  ' + doc.page_content

        if generate:
            generated = llm_chain.run(doc=doc.page_content,query=llm_combined_query(context,query))
            doc.metadata['generated_response'] = generated
        else:
            doc.metadata['generated_response'] = 'Text generation is turned off'
    
    return docs