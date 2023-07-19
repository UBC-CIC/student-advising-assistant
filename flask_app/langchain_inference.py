from langchain.docstore.document import Document
from langchain import LLMChain
from langchain.retrievers.document_compressors import LLMChainFilter, LLMChainExtractor
import regex as re
from typing import List, Dict
from dotenv import load_dotenv
import os
import llm_utils
import doc_graph_utils
from comparator import Comparator
from numpy import isnan
from retrievers import PineconeRetriever, Retriever
import copy 
import json
from langchain.chains.question_answering import load_qa_chain
import sys
sys.path.append('..')
from aws_helpers.param_manager import get_param_manager
from aws_helpers.download_s3_files import download_all_dirs

VERBOSE_LLMS = True

load_dotenv()
GRAPH_FILEPATH = os.path.join('data','documents','website_graph.txt')

### LOAD AWS CONFIG
param_manager = get_param_manager()
os.environ["HUGGINGFACEHUB_API_TOKEN"] = param_manager.get_secret('generator/HUGGINGFACE_API')['API_TOKEN']
retriever_config = param_manager.get_parameter('retriever')
generator_config = param_manager.get_parameter('generator')

### LOAD MODELS 
#llm, prompt = llm_utils.load_model_and_prompt(generator_config['ENDPOINT_TYPE'], generator_config['ENDPOINT_NAME'], generator_config['MODEL_NAME'])
llm, prompt = llm_utils.load_model_and_prompt('huggingface', 'google/flan-t5-xxl', 'flan-t5')

llm_chain = LLMChain(prompt=prompt, llm=llm, verbose=VERBOSE_LLMS)
filter = LLMChainFilter.from_llm(llm)
compressor = LLMChainExtractor.from_llm(llm)

if retriever_config['RETRIEVER_NAME'] == 'pinecone':
    pinecone_auth = param_manager.get_secret('retriever/PINECONE')
    retriever = PineconeRetriever(pinecone_auth['PINECONE_KEY'], pinecone_auth['PINECONE_REGION'], filter_params=['faculty','program'])
    
### LOAD FILES
def read_text(filename: str, as_json = False):
    result = ''
    with open(filename) as f:
        if as_json: result = json.load(f)
        else: result = f.read()
    return result
    
graph = doc_graph_utils.read_graph(GRAPH_FILEPATH)
download_all_dirs(retriever_config['RETRIEVER_NAME'])
data_source_annotations = read_text(os.path.join('static','data_source_annotations.json'), as_json=True)

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
        content = ' -> '.join(doc.metadata['parent_titles'][:-1] + doc.metadata['titles'])
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
        
        # Render links in markdown
        for title,(link,_) in doc.metadata['links'].items():
            if len(title) < 4: continue # Don't display links of only a few characters
            doc.page_content = doc.page_content.replace(title, f'[{title}]({link})')
            
        # Add data source annotation
        for key, data in data_source_annotations.items():
            if len(key) < 4: continue 
            if key in doc.metadata['url']: 
                doc.metadata['source'] = f"{data['name']}: {data['annotation']}"

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
        print('filtered')
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
            print('filtered')
            result = filter.compress_documents(result, llm_query)
            
        # Ensure we don't include the same document twice
        current_ids = [doc.metadata['doc_id'] for doc in docs]
        for doc in result:
            if doc.metadata['doc_id'] not in current_ids: docs.append(doc)
            
    return docs[:min(len(docs),k)] 
    
async def run_chain(program_info: Dict, topic: str, query:str, start_doc:int=None,
                    combine_with_sibs:bool=False, do_filter:bool=False, compress:bool=True, 
                    generate_by_document:bool=False,
                    generate_combined:bool=True, k:int=2):

    """
    Run the question answering chain with the given context and query
    - program_info: Dict of values describe the faculty, program, specialization, and/or year
    - topic: Topic of the question
    - query: The text query
    - start_doc: If provided, will start searching with the provided document index rather than performing similarity search
    - combine_with_sibs: If true, combines all documents with their immediate sibling documents
    - do_filter: If true, applies a LLM filter step to the retrieved documents to remove irrelevant documents
    - compress: If true, applies a LLM compres step to compress documents, extracting relevant sections
    - generate_by_document: If true, generates a response for each final document
    - generate_combined: If true, generates a reponse using the combined documents
    """

    llm_query = llm_utils.llm_query(program_info, topic, query)
    main_response: str = None
    
    docs = []
    if start_doc:
        # If given a document id to start with, retrieve that document
        docs += retriever.docs_from_ids([start_doc])
    else:
        # Peform retrieval
        docs += backoff_retrieval(retriever, program_info, topic, query, k=k, do_filter=do_filter)

    # Prepare the documents for input to LLMs
    docs_for_llms(docs)

    if combine_with_sibs: combine_sib_docs(retriever, docs)

    # Perform compression step if the option is turned on
    compressed_docs = None
    if compress: 
        compressed_docs = compressor.compress_documents(docs, llm_query)
        get_related_links_from_compressed(docs, compressed_docs)

    # Perform a combined generation if the option is turned on
    if generate_combined:
        combine_documents_chain = load_qa_chain(llm=llm, chain_type="refine")
        input_docs = compressed_docs if compressed_docs else docs
        combined_answer = combine_documents_chain.run(input_documents=input_docs, question=llm_query)
        main_response = combined_answer
    
    for doc in docs:    
        # Generate a response from this document only, if the option is turned on
        if generate_by_document:
            generated = generate_answer(doc, llm_query)
            doc.metadata['generated_response'] = generated
    
        if compress:
            # Add markings to highlight the compressed section of the document in the UI
            compressed_content = [c_doc.page_content for c_doc in compressed_docs if c_doc.metadata['doc_id'] == doc.metadata['doc_id']]
            if len(compressed_content) > 0: 
                compressed_content = compressed_content[0]
                doc.page_content = highlight_compressed_sections(doc.page_content, compressed_content)

    format_docs_for_display(docs)
        
    return docs, main_response