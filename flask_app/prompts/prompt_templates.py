
from langchain import PromptTemplate
from typing import Dict, Optional
from langchain.output_parsers import BooleanOutputParser
from llms import query_context_split

### GENERAL QUERY TRANSORMATIONS

llm_query_template = "{program_info} {query}"
llm_query_prompt = PromptTemplate(template=llm_query_template, input_variables=["program_info","query"])

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
    if len(topic) > 0:
        query = f'On the topic of {topic}: {query}'
    return llm_query_prompt.format(program_info=llm_program_str(program_info), query=query)

### FASTCHAT SYSTEM PROMPT
# These are prompts to tell the system 'who it is' when using fastchat adapter

fastchat_system_concise = """
A chat between a user and an artificial intelligence assistant.
The assistant is for the University of British Columbia (UBC). 
The assistant follows instructions precisely and gives concise answers."""

fastchat_system_detailed = """
A chat between a University of British Columbia (UBC) student and an artificial intelligence assistant. 
The assistant gives helpful, detailed, and polite answers to the user's questions."""

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
    Generate a context string for input to the title_filter_context_template
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

def basic_filter_question_str(program_info: Dict, topic: str, query: str) -> str:
    """
    Generate a filter question string
    """
    return llm_query(program_info, topic, query)

default_filter_template = """
Given the following question and document, return YES if the document contains the answer to the question, and NO otherwise.
If the question and the document refer to different programs or year levels, answer NO.
> Question: {question}
> Document: {context}
"""
default_filter_prompt = PromptTemplate(template=default_filter_template, input_variables=["question","context"], 
                               output_parser=VerboseFlexibleBooleanOutputParser(default_val=False))

def vicuna_filter_question_str(program_info: Dict, topic: str, query: str) -> str:
    """
    Generate a filter question string for Vicuna filter template
    """
    question_str = ''
    context_str = filter_context_str(program_info, topic)
    
    if context_str:
        question_str += f'If the context is not about {context_str}, then say no and explain why the context is not relevant.'
        
    question_str += f'\n> Question: {query}\n'
    return question_str

vicuna_filter_template = """
Does the text below contain information that answers the following question?
Say 'yes, because...' or 'no, because...', then explain why you answered yes or no.
{question}
> text: {context}
"""
vicuna_filter_prompt = PromptTemplate(template=vicuna_filter_template, input_variables=["question","context"], 
                                      output_parser=VerboseFlexibleBooleanOutputParser(default_val=False))

### QA PROMPTS

# Default question answering template
default_qa_template = "Context: {context}\n\nQuestion: {question} If you don't know the answer, just say 'I don't know'. \n\nAnswer:"
default_qa_prompt = PromptTemplate(template=default_qa_template, input_variables=["context","question"])

# Template for Vicuna question answering
vicuna_qa_template = """
    Please answer the question based on the context below.
    Use only the context provided to answer the question, and no other information.
    If the context doesn't have enough information to answer, explain what information is missing.\n
    Context:{context}\n
    Question:{question}""".strip()
vicuna_qa_prompt = PromptTemplate(template=vicuna_qa_template, input_variables=["context","question"])

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

falcon_spelling_correction_template = """
You are a spell correction tool. Correct any spelling and grammar mistakes in the following text:
{text}
Corrected version:
"""
falcon_spelling_correction_prompt = PromptTemplate(template=falcon_spelling_correction_template, input_variables=["text"])