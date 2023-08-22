
from langchain import PromptTemplate
from typing import Dict, Optional
from langchain.output_parsers import BooleanOutputParser
from llms import query_context_split
from langchain.prompts.pipeline import PipelinePromptTemplate

### GENERAL QUERY TRANSORMATIONS

llm_query_template = "{program_info} {query}"
llm_query_prompt = PromptTemplate(template=llm_query_template, input_variables=["program_info","query"])

def llm_program_str(program_info: Dict):
    """
    Generate a text string from a dict of program info, for 
    input to an LLM
    """
    context_str = ''
    if 'faculty' in program_info and len(program_info['faculty']) > 0:
        context_str += f"I am in {program_info['faculty']}"
    if 'program' in program_info and len(program_info['program']) > 0:
        context_str += f", {program_info['program']}"
    if 'specialization' in program_info and len(program_info['specialization']) > 0:
        context_str += f", {program_info['specialization']}"
    if 'year' in program_info and len(program_info['year']) > 0:
        context_str += f" in {program_info['year']}"
    return context_str if context_str == '' else context_str + '.'

def llm_query(program_info: Dict, topic: str, query: str):
    """
    Combine a context string with a query for use as input to LLM
    """
    if topic and len(topic) > 0:
        query = f'On the topic of {topic}: {query}'
    return llm_query_prompt.format(program_info=llm_program_str(program_info), query=query)

### GENERAL PROMPT TEMPLATES
# Some models prefer to receive inputs in a particular format

vicuna_template = """{system}\n\nUSER:\n{input}\n\nASSISTANT:\n"""
vicuna_full_prompt = PromptTemplate(template=vicuna_template, input_variables=["system","input"])

### SYSTEM PROMPTS
# These are prompts to tell the system 'who it is' when using fastchat adapter

system_concise = PromptTemplate(template="""
A chat between a user and an artificial intelligence assistant.
The assistant is for the University of British Columbia (UBC). 
The assistant follows instructions precisely and gives concise answers.""",
input_variables=[])

system_detailed = PromptTemplate(template="""
A chat between a University of British Columbia (UBC) student and an artificial intelligence assistant. 
The assistant gives helpful, detailed, and polite answers to the user's questions.""",
input_variables=[])

### FILTER PROMPTS

class FlexibleBooleanOutputParser(BooleanOutputParser):
    """
    Boolean output parser that only requires the output to contain
    the boolean value, not to exactly match.
    Preferences towards the first mentioned value.
    If a default value is defined, then returns this if no boolean value found.
    """
    default_val: Optional[bool] = None
    
    def parse(self, text: str) -> bool:
        """Parse the output of an LLM call to a boolean.

        Args:
            text: output of a language model

        Returns:
            boolean

        """
        true_val = self.true_val.upper()
        false_val = self.false_val.upper()
        cleaned_text = text.strip().upper()
        if true_val in cleaned_text:
            if false_val in cleaned_text:
                # Both vals are in the text, return the first occurence
                return cleaned_text.index(true_val) < cleaned_text.index(false_val)
            return True
        elif false_val in cleaned_text.upper():
            return False
        elif self.default_val is not None:
            return self.default_val
        else:
            raise ValueError(
                f"BooleanOutputParser expected output value to either be "
                f"{self.true_val} or {self.false_val}. Received {cleaned_text}."
            )
            
class VerboseFlexibleBooleanOutputParser(FlexibleBooleanOutputParser):
    """
    Boolean output parser that only requires the output to contain
    the boolean value, not to exactly match.
    Preferences towards the first mentioned value.
    """
    def parse(self, text: str) -> bool:
        """Parse the output of an LLM call to a boolean.

        Args:
            text: output of a language model

        Returns:
            Tuple of boolean, and the original text (boolean)
        """
        
        return super(self.__class__,self).parse(text), text

def filter_context_str(program_info: Dict, topic: str) -> str:
    """
    Generate a context string for input to the filter template
    """
    context_str = ''
    if topic and topic != '':
        context_str = 'the topic ' + topic
    if 'specialization' in program_info and program_info['specialization'] != '':
        if context_str != '': context_str += ' for '
        context_str += program_info['specialization']
    if 'year' in program_info and program_info['year'] != '':
        if context_str != '': context_str += ' in '
        context_str += program_info['year']
    return context_str if context_str != '' else None

default_filter_template = """
Given the following question and document, return YES if the document contains the answer to the question, and NO otherwise.
If the document is not about {context}, answer NO.
> Question: {question}
> Document: {text}
"""
default_filter_prompt = PromptTemplate(template=default_filter_template, input_variables=["context","question","text"], 
                               output_parser=VerboseFlexibleBooleanOutputParser(default_val=False))

vicuna_filter_system_template = """
A chat between a UBC student and an artificial intelligence assistant.
The user wants to answer the question: {% if context and context != 'None' %} For {{ context }}, {% endif %} {{ question }}
{% if context and context != 'None' %}\nThe user doesn't want any information that is not specifically about {{context}}.
Note that combined majors, honours, and majors are all different programs.\n{% endif %}
"""

vicuna_filter_system_prompt = PromptTemplate(template=vicuna_filter_system_template, input_variables=["context","question"], template_format="jinja2")

vicuna_filter_input_template = """
{% if context and context != 'None' %}Is the text below about {{ context }} and contain information relevant to answer the question?{% else %}Does the text below contain information relevant to answer the question?{% endif %}
Say 'yes, because...' or 'no, because...', then explain why you answered yes or no.
{% if context and context != 'None' %}If the text is not about {{ context }}, say no because it is not relevant.\n{% endif %}
> Text: 
{{ text }}
"""
vicuna_filter_input_prompt = PromptTemplate(template=vicuna_filter_input_template, input_variables=["context","text"], template_format="jinja2")

vicuna_filter_prompt = PipelinePromptTemplate(
    final_prompt=vicuna_full_prompt, 
    pipeline_prompts=[
        ("system", vicuna_filter_system_prompt),
        ("input", vicuna_filter_input_prompt)
    ], 
    output_parser=VerboseFlexibleBooleanOutputParser(default_val=False))

### QA PROMPTS

default_qa_template = """
Please answer the question based on the context below.
Use only the context provided to answer the question, and no other information.
If the context doesn't have enough information to answer, explain what information is missing.\n
Context:\n{context}\n
Question:\n{question}""".strip()
default_qa_prompt = PromptTemplate(template=default_qa_template, input_variables=["context","question"])

vicuna_qa_system_template = """A chat between a University of British Columbia (UBC) student and an academic advising assistant.
The assistant is gives detailed and polite responses, but if it does not know the answer for sure, then it states that it cannot answer.
The assistant knows only the following information, and does not use any other information.
If the information it knows is not relevant for the question, then the assistant explains that it cannot answer.

Here is the information that the assistant knows:

{context}
"""
vicuna_qa_system_prompt = PromptTemplate(template=vicuna_qa_system_template, input_variables=["context"])

vicuna_qa_input_template = """{question} Don't say anything that you aren't absolutely sure about based on the information you have.""".strip()
vicuna_qa_input_prompt = PromptTemplate(template=vicuna_qa_input_template, input_variables=["question"])

vicuna_qa_prompt = PipelinePromptTemplate(
    final_prompt=vicuna_full_prompt, 
    pipeline_prompts=[
        ("system", vicuna_qa_system_prompt),
        ("input", vicuna_qa_input_prompt)
    ])

# Template for huggingface endpoints of the 'question answering' type (eg BERT, not text generation)
huggingface_qa_template = "{question}" + query_context_split + "{context}"
huggingface_qa_prompt = PromptTemplate(template=huggingface_qa_template, input_variables=["context","question"])

### OTHER PROMPTS

default_spelling_correction_template = """
Please correct the grammar and spelling errors in the following text. 
Return only the corrected version of the text, do not respond to the question and do not include any annotation.
>>> Input:
{text}
>>> Corrected:
"""
default_spelling_correction_prompt = PromptTemplate(template=default_spelling_correction_template, input_variables=["text"])