from langchain.docstore.document import Document
from langchain import LLMChain
from langchain.retrievers.document_compressors import LLMChainFilter, LLMChainExtractor
import regex as re
from typing import List, Dict
from dotenv import load_dotenv
import os
from download_s3_files import download_all_dirs
import llm_utils
import doc_graph_utils
from comparator import Comparator
from numpy import isnan
from retrievers import PineconeRetriever, Retriever
import copy 

load_dotenv()
GRAPH_FILEPATH = os.path.join('data','documents','website_graph.txt')

### LOAD MODELS 
huggingface_model_names = ['google/flan-t5-xxl','google/flan-ul2','tiiuae/falcon-7b-instruct']
llm, prompt = llm_utils.load_huggingface_endpoint(huggingface_model_names[0])
llm_chain = LLMChain(prompt=prompt, llm=llm)
filter = LLMChainFilter.from_llm(llm, verbose=True)
compressor = LLMChainExtractor.from_llm(llm)
graph = doc_graph_utils.read_graph(GRAPH_FILEPATH)
download_all_dirs()

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

def get_related_links_from_sim(retriever: Retriever, context, query, docs, score_threshold = 0.5):
    """
    Searches through links in the given documents:
    - Computes similarity between the query and the link text
    - If the similarities are over the threshold, adds the links to the document metadata
    """
    titles = []
    spans = []
    context_str = retriever.retriever_context_str(context)

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

def combine_sib_docs(retriever: Retriever, docs: List[Document]) -> List[Document]:
    """
    For each document, combine its context with all of its immediate siblings
    """
    for doc in docs:
        sib_ids = doc_graph_utils.get_split_sib_ids(graph, doc.metadata['doc_id'])
        sib_docs = retriever.docs_from_ids(sib_ids)
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

def generate_answer(doc, query):
    """
    Generate an answer based on the given document, plus additional context if defined for the document
    """
    titles = ' -> '.join(doc.metadata['parent_titles'] + doc.metadata['titles'])
    content = titles + '\n\n' + doc.page_content
    return llm_chain.run(doc=content,query=query)

def docs_for_llms(docs: List[Document]):
    """
    Modifies the page_content of each doc, so the page contents are optimized for input to an LLM
    Does the following transformations:
    - Adds the sequence of page titles to the contents
    - Adds the context sentence if provided
    """
    for doc in docs:
        content = ' -> '.join(doc.metadata['parent_titles'] + doc.metadata['titles'])
        if 'context' in doc.metadata and not isnan(doc.metadata['context']) and doc.metadata['context'] != '': 
            content += '\n\n' + doc.metadata['context']
        content += '\n\n' + doc.page_content
        doc.metadata['original_page_content'] = doc.page_content
        doc.page_content = content

def format_docs_for_display(docs: List[Document]):
    """
    Perform any processing steps to make documents suitable for display
    """
    for doc in docs:
        # Handle documents starting with a list item
        doc.page_content = doc.page_content.strip()
        if doc.page_content.startswith('*'): doc.page_content = '  ' + doc.page_content

        # Replace any occurrence of 4 spaces, since it will be interepreted as a code block in markdown
        doc.page_content = doc.page_content.replace('    ', '   ')

def backoff_retrieval(retriever: Retriever, program_info: Dict, topic: str, query:str, k:int = 5, threshold = 0, do_filter: bool = False) -> List[Document]:
    """
    Perform a multistep retrieval where, if not enough documents are returned for the full
    program_info filter, filters are progressively removed and attempts retrieval again.
    - program_info: Dict of values describe the faculty, program, specialization, and/or year
    - topic: Topic of the question
    - query: The text query
    - k: number of documents to return
    - threshold: relevance threshold, all returned documents must surpass the threshold
                 the threshold range depends on the scoring function of the chosen retriever
    - do_filter: If true, performs an LLM filter step on returned documents
    """ 
    backoff_order = ['specialization','program','faculty'] # order of filter elements to remove
    llm_query = llm_utils.llm_query(program_info, topic, query)
    program_info_copy = copy.copy(program_info) # copy the dict since elements will be popped
    
    # Perform initial search
    docs = retriever.semantic_search(program_info_copy, topic, query, k=k)
    if do_filter: 
            docs = filter.compress_documents(docs, llm_query)
    
    # Perform additional backoff searches as necessary
    for key in backoff_order:
        if len(docs) >= k: 
            # Enough documents already retrieved
            break
        
        if key not in program_info:
            # This key isn't being filtered on, continue
            continue
        
        # Remove the key from the filter and redo search
        program_info_copy[key] = 'None'
        result = retriever.semantic_search(program_info_copy, topic, query, k=k, threshold=threshold)
        
        if do_filter: 
            result = filter.compress_documents(result, llm_query)
            
        # Ensure we don't include the same document twice
        current_ids = [doc.metadata['doc_id'] for doc in docs]
        for doc in result:
            if doc.metadata['doc_id'] not in current_ids: docs.append(doc)
            
    return docs[:min(len(docs),k)] 
    
async def run_chain(program_info: Dict, topic: str, query:str, start_doc:int=None,
                    combine_with_sibs:bool=False, do_filter:bool=True, compress:bool=False, generate:bool=False):

    """
    Run the question answering chain with the given context and query
    - program_info: Dict of values describe the faculty, program, specialization, and/or year
    - topic: Topic of the question
    - query: The text query
    - start_doc: If provided, will start searching with the provided document index rather than performing similarity search
    - combine_with_sibs: If true, combines all documents with their immediate sibling documents
    - do_filter: If true, applies a LLM filter step to the retrieved documents to remove irrelevant documents
    - compress: If true, applies a LLM compres step to compress documents, extracting relevant sections
    - generate: If true, generates a response for each final document
    """

    retriever = PineconeRetriever(filter_params=['faculty','program'])
    llm_query = llm_utils.llm_query(program_info, topic, query)
    
    docs = []
    if start_doc:
        docs += retriever.docs_from_ids([start_doc])
    else:
        docs += backoff_retrieval(retriever, program_info, topic, query, k=5, do_filter=do_filter)

    docs_for_llms(docs)

    if combine_with_sibs: combine_sib_docs(retriever, docs)

    compressed_docs = None
    if compress: 
        compressed_docs = compressor.compress_documents(docs, llm_query)
        get_related_links_from_compressed(docs, compressed_docs)

    for doc in docs:
        highlighted_text = None
        
        if compress:
            compressed_content = [c_doc.page_content for c_doc in compressed_docs if c_doc.metadata['doc_id'] == doc.metadata['doc_id']]
            if len(compressed_content) > 0: 
                compressed_content = compressed_content[0]
                compressed_re = re.escape(compressed_content).replace('\ ','(\s|\n)*')
                if match := re.search(compressed_re, doc.page_content):
                    # Highlight the compressed section
                    new = add_italics(match.group())
                    highlighted_text = doc.page_content.replace(match.group(), new)
                    
        if generate:
            generated = generate_answer(doc, llm_query)
            doc.metadata['generated_response'] = generated
        else:
            doc.metadata['generated_response'] = 'Text generation is turned off'
        
        if highlighted_text: doc.page_content = highlighted_text
    
    format_docs_for_display(docs)
    return docs