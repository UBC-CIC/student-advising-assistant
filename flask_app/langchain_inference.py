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
from retrievers import PineconeRetriever

load_dotenv()
GRAPH_FILEPATH = os.path.join('data','documents','website_graph.txt')

### LOAD MODELS 
huggingface_model_names = ['google/flan-t5-xxl','google/flan-ul2','tiiuae/falcon-7b-instruct']
llm, prompt = llm_utils.load_huggingface_endpoint(huggingface_model_names[0])
llm_chain = LLMChain(prompt=prompt, llm=llm)
filter = LLMChainFilter.from_llm(llm)
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

def get_doc_children(docs: List[Document], retriever_name: str) -> List[Document]:
    
    # Finding child doc ids
    doc_ids = [doc.metadata['doc_id'] for doc in docs]
    child_doc_ids = []
    
    for doc_id in doc_ids:
        child_doc_ids.extend(doc_graph_utils.get_doc_child_extract_ids(graph, doc_id))

    if len(child_doc_ids) == 0:
        return []
    
    # Fetching related docs
    child_docs = retrievers.docs_from_ids(child_doc_ids, retriever_name)
    
    return child_docs

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

def choose_retrievers(program_info: Dict):
    """
    Choose the appropriate retriever(s) given the program information dict
    If more than one retriever should be included, returns multiple
    """
    if 'faculty' in program_info and program_info['faculty'] == 'The Faculty of Science':
        #return ['sc-triple','none-triple']
        return ['sc-triple']
    else:
        return ['all-triple']
    
async def run_chain(program_info: Dict, topic: str, query:str, start_doc:int=None, children:bool=False,
                    combine_with_sibs:bool=False, do_filter:bool=False, compress:bool=False, generate:bool=False):

    """
    Run the question answering chain with the given context and query
    - program_info: Dict of values describe the faculty, program, specialization, and/or year
    - topic: Topic of the question
    - query: The text query
    - start_doc: If provided, will start searching with the provided document index rather than performing similarity search
    - children: If true, fetches child extracts of all retrieved documents
    - combine_with_sibs: If true, combines all documents with their immediate sibling documents
    - filter: If true, applies a LLM filter step to the retrieved documents to remove irrelevant documents
    - compress: If true, applies a LLM compres step to compress documents, extracting relevant sections
    - generate: If true, generates a response for each final document
    """

    retriever = PineconeRetriever()
    llm_query = llm_utils.llm_query(program_info, topic, query)
    
    print(llm_query)
    
    docs = []
    if start_doc:
        docs += retriever.docs_from_ids([start_doc])
    else:
        docs += retriever.semantic_search(program_info, topic, query)

    docs_for_llms(docs)
    
    if children: 
        docs += get_doc_children(docs, 'all-triple')

    if combine_with_sibs: combine_sib_docs(docs)

    if do_filter: docs = filter.compress_documents(docs, llm_query)

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
        
        # Handle documents starting with a list item
        doc.page_content = doc.page_content.strip()
        if doc.page_content.startswith('*'): doc.page_content = '  ' + doc.page_content

        # Replace any occurrence of 4 spaces, since it will be interepreted as a code block in markdown
        doc.page_content = doc.page_content.replace('    ', '   ')
    
    return docs