
"""
Utility functions for loading LLMs and associated prompts
"""

from langchain import HuggingFaceHub, Prompt, LLMChain
from langchain.llms import BaseLLM
from langchain.llms.sagemaker_endpoint import LLMContentHandler
from langchain.retrievers.document_compressors import LLMChainFilter
import json
from typing import Tuple, Dict, Callable
import os 
import prompts
from filters import VerboseFilter, FilterWithContext
from .huggingface_qa import HuggingFaceQAEndpoint
from .sagemaker_endpoint import MySagemakerEndpoint
from aws_helpers.param_manager import get_param_manager

### HELPER CLASSES
class ContentHandler(LLMContentHandler):
    """
    Content handler for sagemaker endpoints
    """
    content_type = "application/json"
    accepts = "application/json"

    def transform_input(self, prompt: str, model_kwargs: Dict) -> bytes:
        input_str = json.dumps({'inputs': prompt, 'parameters': model_kwargs})
        print(input_str)
        return input_str.encode("utf-8")

    def transform_output(self, output: bytes) -> str:
        response_json = json.loads(output.read().decode("utf-8"))
        print(response_json)
        return response_json[0]["generated_text"]
    
### MODEL LOADING FUNCTIONS
    
def load_model_and_prompt(endpoint_type: str, endpoint_name: str, model_name: str) -> Tuple[BaseLLM,Prompt]:
    """
    Utility function loads a LLM of the given endpoint type and model name, and the QA Prompt
    - endpoint_type: 'sagemaker', 'huggingface', or 'huggingface_qa'
        - sagemaker: an AWS sagemaker endpoint
        - huggingface: a huggingface api endpoint for the 'text generation' task
        - huggingface_qa: a huggingface api endpoint for the 'question answering' task
                          (eg. a BERT-type model)
    - endpoint_name: huggingface model id, or sagemaker endpoint name
    - model_name: display name of the model
    """
    llm = None
    if endpoint_type == 'sagemaker':
        llm = load_sagemaker_endpoint(endpoint_name)
    elif endpoint_type == 'huggingface':
        os.environ["HUGGINGFACEHUB_API_TOKEN"] = get_param_manager().get_secret('generator/HUGGINGFACE_API')['API_TOKEN']
        llm = load_huggingface_endpoint(endpoint_name)
    elif endpoint_type == 'huggingface_qa':
        param_manager = get_param_manager()
        os.environ["HUGGINGFACEHUB_API_TOKEN"] = param_manager.get_secret('generator/HUGGINGFACE_API')['API_TOKEN']
        llm = load_huggingface_qa_endpoint(endpoint_name)
        
    return llm, load_prompt(endpoint_type, model_name)
    
def load_prompt(endpoint_type: str, model_name: str):
    """
    Utility function loads a prompt for the given endpoint type and model name
    - endpoint_type: 'sagemaker', 'huggingface', or 'huggingface_qa'
    - model_name: requires that the name is defined for the appropriate endpoint
                  in the dicts above
    """
    if endpoint_type == 'huggingface_qa':
        return prompts.huggingface_qa_prompt
    if model_name == 'vicuna':
        return prompts.vicuna_qa_prompt
    else:
        return prompts.default_qa_prompt
    
def load_sagemaker_endpoint(endpoint_name: str) -> BaseLLM:
    """
    Loads the LLM for a sagemaker inference endpoint
    """
    content_handler = ContentHandler()
    credentials_profile = os.environ["AWS_PROFILE_NAME"] if "AWS_PROFILE_NAME" in os.environ else None
    llm = MySagemakerEndpoint(
        endpoint_name=endpoint_name,
        credentials_profile_name=credentials_profile,
        region_name="us-west-2", 
        model_kwargs={"do_sample": False, "temperature": 0.1, "max_new_tokens":200},
        content_handler=content_handler
    )

    return llm

def load_huggingface_endpoint(name: str) -> BaseLLM:
    """
    Loads the LLM for a huggingface text generation inference endpoint
    Requires that the HUGGINGFACEHUB_API_TOKEN environment variable is set
    """
    llm = HuggingFaceHub(repo_id=name, model_kwargs={"temperature":0.1, "max_new_tokens":200})
    return llm

def load_huggingface_qa_endpoint(name: str) -> BaseLLM:
    """
    Loads the LLM and prompt for a huggingface question answering inference endpoint
    eg. name = deepset/deberta-v3-large-squad2
    """
    llm = HuggingFaceQAEndpoint(repo_id=name)
    return llm

def load_chain_filter(base_llm: BaseLLM, model_name: str, verbose: bool = False) -> FilterWithContext:
    """
    Loads a chain filter using the given base llm for the given model name
    Returns: FilterWithContext, wrapping a chain filter. 
             Expects the following inputs to the compress_documents function: docs, query, program_info, topic
    """
    if model_name == 'vicuna':
        return FilterWithContext(VerboseFilter.from_llm(base_llm,prompt=prompts.vicuna_filter_prompt,verbose=verbose), prompts.filter_context_str)
    else:
        return FilterWithContext(VerboseFilter.from_llm(base_llm,prompt=prompts.default_filter_prompt,verbose=verbose), prompts.filter_context_str)
    
def load_spell_chain(base_llm: BaseLLM, model_name: str, verbose: bool = False) -> LLMChain:
    """
    Loads a spelling correction chain using the given base llm
    Chooses a prompts based on the model name
    Returns: A LLMChain for spelling correction
    """
    prompt = prompts.default_spelling_correction_prompt
    return LLMChain(llm=base_llm,prompt=prompt,verbose=verbose)