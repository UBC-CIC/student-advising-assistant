
"""
Utility functions for loading LLMs and associated prompts
"""

from langchain import HuggingFaceHub, SagemakerEndpoint, PromptTemplate, Prompt
from langchain.llms import BaseLLM
from langchain.llms.sagemaker_endpoint import LLMContentHandler
from huggingface_qa import HuggingFaceQAEndpoint, query_context_split
from langchain.prompts.few_shot import FewShotPromptTemplate
from prompts.degree_requirements import few_shot_examples
import json
from typing import Tuple, Dict

### PROMPTS AND PROMPT TEMPLATES 
default_template = "Context: {doc}\n\nQuestion: {query} If you don't know the answer, just say 'I don't know'. \n\nAnswer:"

falcon_template = """
    Answer the question based on the context below. Keep the answer short and concise. Respond "Unsure about answer" if not sure about the answer.
    Context:{doc}\n
    Question:{query}\n
    Answer:""".strip()

few_shot_example_prompt = PromptTemplate(input_variables=["doc", "query", "answer"], template="Evidence:{doc}\nQuestion:{query}\nAnswer:{answer}")

few_shot_prompt = FewShotPromptTemplate(
    examples=few_shot_examples, 
    example_prompt=few_shot_example_prompt, 
    suffix="Evidence:{doc}\nQuestion:{query}\nAnswer:", 
    input_variables=["doc","query"]
)

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
def llm_context_str(context: str | Dict):
    """
    Generate a text string from a context dict, for 
    input to an LLM
    """
    context_str = ''
    if type(context) == dict:
        context_str = ''
        if 'faculty' in context:
            context_str += f"I am in {context['faculty']}"
        if 'program' in context:
            context_str += f", {context['program']}"
        if 'specialization' in context:
            context_str += f", {context['specialization']}"
        if 'year' in context:
            context_str += f"in {context['year']}"
    else:
        context_str = context
    return context_str

def llm_combined_query(context,query):
    """
    Combine a context string with a query for use as input to LLM
    """
    return f"{llm_context_str(context)}. {query}"

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
    prompt = PromptTemplate(template=default_template, input_variables=["doc","query"])
    return llm,prompt

def load_huggingface_endpoint(name: str) -> Tuple[BaseLLM,Prompt]:
    """
    Loads the LLM and prompt for a huggingface text generation inference endpoint
    Requires that the HUGGINGFACEHUB_API_TOKEN environment variable is set
    """
    llm = HuggingFaceHub(repo_id=name, model_kwargs={"temperature":0.1, "max_new_tokens":200})
    prompt = PromptTemplate(template=default_template, input_variables=["doc","query"])
    return llm,prompt

def load_huggingface_qa_endpoint(name: str) -> Tuple[BaseLLM,Prompt]:
    """
    Loads the LLM and prompt for a huggingface question answering inference endpoint
    eg. name = deepset/deberta-v3-large-squad2
    """
    llm = HuggingFaceQAEndpoint(repo_id=name)
    template = "{query}" + query_context_split + "{doc}"
    prompt = PromptTemplate(template=template, input_variables=["doc","query"])
    return llm,prompt