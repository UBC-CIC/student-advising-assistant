# Loads env variable when running locally
from dotenv import load_dotenv
load_dotenv()

## Add parent directory to path for aws_helpers
import sys
sys.path.append('..')

# Imports
from langchain.docstore.document import Document
from langchain import LLMChain
from langchain.retrievers.document_compressors import LLMChainExtractor
import regex as re
from typing import List, Dict, Tuple
from retrievers import Retriever, load_retriever
import copy 
import json
import os
from langchain.chains.question_answering import load_qa_chain
import llms
from documents import load_graph, get_split_sib_ids
import prompts
from aws_helpers.param_manager import get_param_manager
from aws_helpers.s3_tools import download_s3_directory

# If process is running locally, activate dev mode
DEV_MODE = 'MODE' in os.environ and os.environ.get('MODE') == 'dev'
VERBOSE_LLMS = DEV_MODE
GRAPH_FILEPATH = os.path.join('data','documents','website_graph.txt')

### CONSTANTS
# Remove documents below a certain character length - helps with some LLM hallucinations
min_doc_length = 100

### LOAD AWS CONFIG
param_manager = get_param_manager()
retriever_config = param_manager.get_parameter('retriever')
generator_config = param_manager.get_parameter('generator')

### LOAD FILES
def read_text(filename: str, as_json = False):
    result = ''
    with open(filename) as f:
        if as_json: result = json.load(f)
        else: result = f.read()
    return result
    
graph = load_graph(GRAPH_FILEPATH)

def download_all_dirs(retriever: str):
    """
    Downloads the directories from s3 necessary for the flask app
    - retriever: Specify the retriever so the appropriate documents can be downloaded
                 Choices are 'pinecone', 'pgvector'
    """
    # Specify directories to download
    dirs = ['documents']

    if retriever == 'pinecone':
        dirs.append('indexes/pinecone')
    elif retriever == 'pgvector':
        dirs.append('indexes/pgvector')
        
    for dir in dirs:
        download_s3_directory(dir, output_prefix='data')
        
download_all_dirs(retriever_config['RETRIEVER_NAME'])

data_source_annotations = read_text(os.path.join('static','data_source_annotations.json'), as_json=True)

### LOAD MODELS 

# LLMs
base_llm, qa_prompt = llms.load_model_and_prompt(generator_config['ENDPOINT_TYPE'], generator_config['ENDPOINT_NAME'], generator_config['MODEL_NAME'])
concise_llm = llms.load_fastchat_adapter(base_llm, generator_config['MODEL_NAME'], prompts.fastchat_system_concise)
detailed_llm = llms.load_fastchat_adapter(base_llm, generator_config['MODEL_NAME'], prompts.fastchat_system_detailed)

# Chains
spell_correct_chain = LLMChain(llm=concise_llm,prompt=prompts.spelling_correction_prompt)
combine_documents_chain = load_qa_chain(llm=detailed_llm, chain_type="stuff", prompt=qa_prompt)

# Document compressors
filter, filter_question_fn = llms.load_chain_filter(concise_llm, generator_config['MODEL_NAME'])
compressor = LLMChainExtractor.from_llm(concise_llm)

# Retriever
retriever: Retriever = load_retriever(retriever_config['RETRIEVER_NAME'], dev_mode=DEV_MODE, 
                                      verbose=VERBOSE_LLMS)

### UTILITY FUNCTIONS

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

def combine_sib_docs(retriever: Retriever, docs: List[Document]) -> List[Document]:
    """
    For each document, combine its context with all of its immediate siblings
    """
    for doc in docs:
        sib_ids = get_split_sib_ids(graph, doc.metadata['doc_id'])
        sib_docs = retriever.docs_from_ids(sib_ids)
        combined_content = ' '.join([sib_doc.page_content for sib_doc in sib_docs])
        doc.page_content = combined_content
        doc.metadata['titles'] = doc.metadata['titles'][:-1]

def highlight_compressed_sections(original_text: str, compressed_text: str):
    """
    Places italics markings around the sections of the original text that are referenced in the compressed text
    - original_text: the original text
    - compressed_text: a response from an LLM asked to extract relevant sections of the original text
    """
    highlighted_text = original_text
    
    compressed_sentences = compressed_text.split('\n')
    
    # Vicuna likes to add numbers to each returned sentence, this removes t he numbers
    compressed_sentences = [re.sub('\d(\.)\s','',sent.strip()) for sent in compressed_sentences]
    
    for sent in compressed_sentences:
        if len(sent) == 0: continue 
        
        # Remove quotations around the sentence, if applicable
        if sent[0] == '"': sent = sent[1:]
        if sent[-1] == '"': sent = sent[:-1]
        
        # Vicuna likes to add numbers to each returned sentence, this removes the numbers
        sent = re.sub('\d(\.)\s','',sent)
        
        if match := re.search(sent, original_text):
            # Add italics markings as the indicator to highlight
            highlighted_section = add_italics(match.group())
            highlighted_text = highlighted_text.replace(match.group(), highlighted_section)
            
    return highlighted_text

def add_italics(text):
    """
    Add italics markings around every line of the text
    """
    for match in re.finditer('[\w\d][^\n\*]+[\w\d]',text):
        text = text.replace(match.group(),f"*{match.group()}*")
    return text

def doc_display_title(doc: Document):
    """
    Return a display formatted title for a document
    """
    return ' -> '.join(doc.metadata['parent_titles'][:-1] + doc.metadata['titles'])

def docs_for_llms(docs: List[Document]):
    """
    Modifies the page_content of each doc, so the page contents are optimized for input to an LLM
    Does the following transformations:
    - Adds the sequence of page titles to the contents
    - Adds the context sentence if provided
    """
    for doc in docs:
        content = doc_display_title(doc)
        if 'context' in doc.metadata and type(doc.metadata['context']) == str and doc.metadata['context'] != '': 
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
        
        # Render links in markdown
        for title,(link,_) in doc.metadata['links'].items():
            if len(title) < 4: continue # Don't display links of only a few characters
            doc.page_content = doc.page_content.replace(title, f'[{title}]({link})')
            
        # Add data source annotation
        for key, data in data_source_annotations.items():
            if len(key) < 4: continue 
            if key in doc.metadata['url']: 
                doc.metadata['source'] = f"{data['name']}: {data['annotation']}"

def llm_filter_docs(docs: List[Document], program_info: Dict, topic: str, query:str, 
                    return_removed: bool = False) -> List[Document] | Tuple[List[Document],List[Document]]:
    """
    Filters the documents for relevance using a LLM
    - return_removed: If true, returns the list of removed documents as well as the filtered docs
    """
    
    # Run the filter chain
    query = filter_question_fn(program_info, topic, query)
    filtered, removed = filter.compress_documents(docs, query)
    if return_removed:
        return filtered, removed
    else:
        return filtered
    
def backoff_retrieval(retriever: Retriever, program_info: Dict, topic: str, query:str, k:int = 5, threshold = 0, 
                      do_filter: bool = False) -> List[Document]:
    """
    Perform a multistep retrieval where, if no documents are returned for the full
    program_info filter, filters are progressively removed and attempts retrieval again.
    - program_info: Dict of values describe the faculty, program, specialization, and/or year
    - topic: Topic of the question
    - query: The text query
    - k: number of documents to return
    - threshold: relevance threshold, all returned documents must surpass the threshold
                 the threshold range depends on the scoring function of the chosen retriever
    - do_filter: If true, performs an LLM filter step on returned documents
    """ 
    backoff_order = [['specialization','year'],['program'],['faculty']] 
    # ^ order of context elements to remove
    metadata_filter_keys = ['program','faculty']
    # ^ these keys will be included in the metadata filter when the value is not empty
    metadata_filter_when_empty = ['specialization','program','faculty'] 
    # ^ these keys will be included in the metadata filter when the value is empty
    
    program_info_copy = copy.copy(program_info) # copy the dict since elements will be popped
    docs = []
    removed_docs = []
    
    backoff_index = 0
    removed_keys = []
    while len(docs) == 0 and backoff_index < len(backoff_order):
        # Prepare the metadata filter
        filter = {}
        nonfiltered_program_info = copy.copy(program_info_copy)
        for key, val in program_info_copy.items():
            if (key in metadata_filter_keys and val is not None and val != '') or \
               (key in metadata_filter_when_empty and val == ''):
                filter[key] = val
                nonfiltered_program_info.pop(key)
        
        # Perform search
        docs = retriever.semantic_search(filter, nonfiltered_program_info, topic, query, k=k)
        
        # Prefilter documents that are too short
        # Some LLMs will hallucinate if the document content is empty
        docs = [doc for doc in docs if len(doc.page_content) >= min_doc_length]
        
        # Filter docs
        docs_for_llms(docs)
        if do_filter: 
            docs, removed = llm_filter_docs(docs, nonfiltered_program_info, topic, query, return_removed=True)
            removed_docs += removed
    
        if len(docs) > 0: 
            # Enough documents already retrieved, break loop
            break
        
        has_key = False
        # Find the next key(s) that can be removed from the program info
        while not has_key and backoff_index < len(backoff_order):
            for key in backoff_order[backoff_index]:
                if key in program_info_copy and program_info_copy[key] != '':
                    # Remove the key from the filter and redo search
                    program_info_copy[key] = ''
                    has_key = True
                    removed_keys.append(key)
                    
            backoff_index += 1
        
        if not has_key:
            # No key left to remove, break loop
            break
    
    if len(docs) > k:
        # If there are extra relevant docs beyond k, move them
        # to removed docs
        removed_docs = docs[k:] + removed_docs
        docs = docs[:k+1]
        
    # If any docs in removed_docs were included in the docs in a later iteration,
    # don't include them in removed_docs
    doc_ids = [doc.metadata['doc_id'] for doc in docs]
    removed_docs = [doc for doc in removed_docs if doc.metadata['doc_id'] not in doc_ids]
    return docs, removed_keys, removed_docs

async def run_chain(program_info: Dict, topic: str, query:str, start_doc:int=None,
                    combine_with_sibs:bool=False, spell_correct:bool=True, 
                    do_filter:bool=True, compress:bool=False, 
                    generate_by_document:bool=False,
                    generate_combined:bool=True, k:int=3):

    """
    Run the question answering chain with the given context and query
    - program_info: Dict of values describe the faculty, program, specialization, and/or year
    - topic: Topic of the question
    - query: The text query
    - start_doc: If provided, will start searching with the provided document index rather than performing similarity search
    - combine_with_sibs: If true, combines all documents with their immediate sibling documents
    - spell_correct: If true, prompts a LLM to fix spelling and grammar of the prompt
    - do_filter: If true, applies a LLM filter step to the retrieved documents to remove irrelevant documents
    - compress: If true, applies a LLM compres step to compress documents, extracting relevant sections
    - generate_by_document: If true, generates a response for each final document
    - generate_combined: If true, generates a reponse using the combined documents
    """

    main_response: str = None
    alerts: str = []
    removed_docs: List[Document] = []
    
    # Spell correct the query if the option is turned on
    if spell_correct:
        corrected_query = spell_correct_chain.run(query)
        if query.lower() != corrected_query.lower(): alerts.append(f'Used spell/grammar corrected query: {corrected_query}')
        query = corrected_query
        
    llm_query = prompts.llm_query(program_info, topic, query)
    
    docs = []
    ignored_keys = []
    if start_doc:
        # If given a document id to start with, retrieve that document
        docs += retriever.docs_from_ids([start_doc])
    else:
        # Peform retrieval
        result, ignored_keys, removed_docs = backoff_retrieval(retriever, program_info, topic, query, k=k, do_filter=do_filter)
        docs += result

    if combine_with_sibs: combine_sib_docs(retriever, docs)

    # Perform compression step if the option is turned on
    compressed_docs = None
    if compress: 
        compressed_docs = compressor.compress_documents(docs, llm_query)
        get_related_links_from_compressed(docs, compressed_docs)

    # Perform a combined generation if the option is turned on
    if generate_combined:
        input_docs = compressed_docs if compressed_docs else docs
        if len(input_docs) > 0:
            combined_answer = combine_documents_chain.run(input_documents=input_docs, question=llm_query)
            main_response = combined_answer
    
    for doc in docs:    
        # Generate a response from this document only, if the option is turned on
        if generate_by_document:
            generated = detailed_llm.run(doc=doc,query=query)
            doc.metadata['generated_response'] = generated
    
        if compress:
            # Add markings to highlight the compressed section of the document in the UI
            compressed_content = [c_doc.page_content for c_doc in compressed_docs if c_doc.metadata['doc_id'] == doc.metadata['doc_id']]
            if len(compressed_content) > 0: 
                compressed_content = compressed_content[0]
                doc.page_content = highlight_compressed_sections(doc.page_content, compressed_content)

    format_docs_for_display(docs)
    format_docs_for_display(removed_docs)
    
    if len(ignored_keys) > 0:
        alerts.append(f"Did not find answer specific to {', '.join([program_info[key] for key in ignored_keys])}")
    
    return docs, main_response, alerts, removed_docs

backoff_retrieval(retriever,{'faculty': 'The Faculty of Science', 'program': 'Bachelor of Science','specialization':'Major Computer Science'},'','Can I take math 120 instead of math 100?',do_filter=True)