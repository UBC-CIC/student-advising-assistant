
"""
Utility functions for loading LLMs and associated prompts
"""

from langchain import HuggingFaceHub, SagemakerEndpoint, Prompt
from langchain.llms import BaseLLM
from langchain.llms.sagemaker_endpoint import LLMContentHandler
from huggingface_qa import HuggingFaceQAEndpoint
import json
from typing import Tuple, Dict
import prompts.prompts as prompts
import os 
from fastchat_adapter import FastChatLLM

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
    
### LLM INPUT FUNCTIONS

def llm_program_str(program_info: Dict):
    """
    Generate a text string from a dict of program info, for 
    input to an LLM
    """
    context_str = ''
    if 'faculty' in program_info:
        context_str += f"I am in {program_info['faculty']}"
    if 'program' in program_info:
        context_str += f", {program_info['program']}"
    if 'specialization' in program_info:
        context_str += f", {program_info['specialization']}"
    if 'year' in program_info:
        context_str += f" in {program_info['year']}"
    return context_str if context_str == '' else context_str + '.'

def llm_query(program_info: Dict, topic: str, query: str):
    """
    Combine a context string with a query for use as input to LLM
    """
    return prompts.llm_query_prompt.format(program_info=llm_program_str(program_info), topic=topic, query=query)

### MODEL LOADING FUNCTIONS

fastchat_models = {
    'vicuna': 'vicuna_v1.1'
}

def load_fastchat_adapter(base_llm: BaseLLM, model_name: str, system_instruction: str) -> BaseLLM:
    """
    Loads a fastchat adapter for the given base model, with the provided system instruction
    """
    
    if model_name not in fastchat_models:
        raise Exception(f'{model_name} is not supported for FastChat')

    return FastChatLLM.from_base_llm(base_llm, fastchat_models[model_name], system_instruction=system_instruction)
    
def load_model_and_prompt(endpoint_type: str, endpoint_name: str, model_name: str) -> Tuple[BaseLLM,Prompt]:
    """
    Utility function loads a LLM of the given endpoint type and model name, and the QA Prompt
    - endpoint_type: 'sagemaker', 'huggingface', or 'huggingface_qa'
    - endpoint_name: huggingface model id, or sagemaker endpoint name
    - model_name: display name of the model
    """
    llm = None
    if endpoint_type == 'sagemaker':
        llm = load_sagemaker_endpoint(endpoint_name)
    elif endpoint_type == 'huggingface':
        llm = load_huggingface_endpoint(endpoint_name)
    elif endpoint_type == 'huggingface_qa':
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
    llm = SagemakerEndpoint(
            endpoint_name=endpoint_name,
            credentials_profile_name=os.environ.get('AWS_PROFILE_NAME'),
            region_name="us-west-2",
            model_kwargs={"do_sample": False, "temperature": 0.1, "max_new_tokens":200},
            content_handler=content_handler,
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