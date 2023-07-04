
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
        context_str += f"in {program_info['year']}"
    return context_str if context_str is '' else context_str + '.'

def llm_query(program_info: Dict, topic: str, query: str):
    """
    Combine a context string with a query for use as input to LLM
    """
    return prompts.llm_query_prompt.format(program_info=llm_program_str(program_info), topic=topic, query=query)

### MODEL LOADING FUNCTIONS
def load_sagemaker_endpoint(endpoint_name) -> Tuple[BaseLLM,Prompt]:
    """
    Loads the LLM and prompt for a sagemaker inference endpoint
    """
    content_handler = ContentHandler()
    llm = SagemakerEndpoint(
            endpoint_name=endpoint_name,
            credentials_profile_name="admin",
            region_name="us-west-2",
            model_kwargs={"temperature": 0.8, "max_new_tokens":200},
            content_handler=content_handler,
        )
    return llm, prompts.default_qa_prompt

def load_huggingface_endpoint(name: str) -> Tuple[BaseLLM,Prompt]:
    """
    Loads the LLM and prompt for a huggingface text generation inference endpoint
    Requires that the HUGGINGFACEHUB_API_TOKEN environment variable is set
    """
    llm = HuggingFaceHub(repo_id=name, model_kwargs={"temperature":0.01, "max_new_tokens":200})
    return llm, prompts.default_qa_prompt

def load_huggingface_qa_endpoint(name: str) -> Tuple[BaseLLM,Prompt]:
    """
    Loads the LLM and prompt for a huggingface question answering inference endpoint
    eg. name = deepset/deberta-v3-large-squad2
    """
    llm = HuggingFaceQAEndpoint(repo_id=name)
    return llm, prompts.huggingface_qa_prompt