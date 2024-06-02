
"""
Utility functions for loading LLMs and associated prompts
"""

from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.llms import BaseLLM
from langchain.llms.sagemaker_endpoint import LLMContentHandler
import json
from typing import Tuple, Dict
import os
import prompts
from filters import VerboseFilter, FilterWithContext
from .sagemaker_endpoint import MySagemakerEndpoint
from aws_helpers.param_manager import get_param_manager
from aws_helpers.ssh_forwarder import start_ssh_forwarder
import boto3

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

hyperparams = {
    "temperature": 0.1,
    "max_new_tokens": 200,
}

# not used anymore at least for now - Aman
# def load_model_and_prompt(endpoint_type: str, endpoint_name: str, endpoint_region: str, model_name: str, dev_mode: bool = False) -> Tuple[BaseLLM, PromptTemplate]:
#     """
#     Utility function loads a LLM of the given endpoint type and model name, and the QA Prompt
#     - endpoint_type: 'sagemaker', 'huggingface_tgi', or 'bedrock'
#         - sagemaker: an AWS sagemaker endpoint
#         - huggingface_tgi: a huggingface text generation server
#         - bedrock: an AWS bedrock endpoint
#     - endpoint_name: sagemaker or bedrock endpoint name
#     - model_name: display name of the model
#     - dev_mode: if true, loads a model for local connection if applicable
#     """
#     llm = None
#     if endpoint_type == 'sagemaker':
#         llm = load_sagemaker_endpoint(endpoint_name, endpoint_region)
#     elif endpoint_type == 'huggingface_tgi':
#         llm = load_huggingface_tgi_endpoint(endpoint_name, dev_mode)
#     elif endpoint_type == 'bedrock':
#         llm = load_bedrock_llm(endpoint_region, model_name)
#     else:
#         raise Exception(f"Endpoint type {endpoint_type} is not supported.")
        
#     return llm, load_prompt(endpoint_type, model_name)

def load_prompt(endpoint_type: str, model_name: str) -> PromptTemplate:
    """
    Utility function loads a prompt for the given endpoint type and model name
    - endpoint_type: 'sagemaker', 'huggingface_tgi', or 'bedrock'
    - model_name: requires that the name is defined for the appropriate endpoint
                  in the dicts above
    """
    return PromptTemplate.from_template(prompts.default_qa_prompt)

def load_sagemaker_endpoint(endpoint_name: str, endpoint_region: str) -> BaseLLM:
    """
    Loads the LLM for a sagemaker inference endpoint
    """
    content_handler = ContentHandler()
    credentials_profile = os.environ["AWS_PROFILE_NAME"] if "AWS_PROFILE_NAME" in os.environ else None
    llm = MySagemakerEndpoint(
        endpoint_name=endpoint_name,
        credentials_profile_name=credentials_profile,
        region_name=endpoint_region, 
        model_kwargs={"do_sample": False, **hyperparams},
        content_handler=content_handler
    )

    return llm

def load_huggingface_tgi_endpoint(name: str, dev_mode: bool = False) -> BaseLLM:
    if dev_mode:
        # Start SSH forwarder through bastion host for local development
        remote_host, remote_port = name.split(':')
        server = start_ssh_forwarder(remote_host, int(remote_port))
        name = f"localhost:{server.local_bind_port}"

def load_chain_filter(base_llm: BaseLLM, model_name: str, verbose: bool = False) -> FilterWithContext:
    """
    Loads a chain filter using the given base llm for the given model name
    Returns: FilterWithContext, wrapping a chain filter. 
             Expects the following inputs to the compress_documents function: docs, query, program_info, topic
    """
    return FilterWithContext(VerboseFilter.from_llm(base_llm,prompt=prompts.default_filter_prompt,verbose=verbose), prompts.filter_context_str)

def load_spell_chain(base_llm: BaseLLM, model_name: str, verbose: bool = False) -> LLMChain:
    """
    Loads a spelling correction chain using the given base llm
    Chooses a prompts based on the model name
    Returns: A LLMChain for spelling correction
    """
    prompt = prompts.default_spelling_correction_prompt
    return LLMChain(llm=base_llm, prompt=prompt, verbose=verbose)
