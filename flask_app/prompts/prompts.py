
from langchain import PromptTemplate
from langchain.prompts.few_shot import FewShotPromptTemplate
from prompts.degree_requirements import few_shot_examples
import huggingface_qa
from typing import Dict
from langchain.output_parsers import BooleanOutputParser

### GENERAL QUERY TRANSORMATIONS

retriever_context_template = "{program_info} : {topic}"

llm_query_template = "{program_info} On the topic of {topic}: {query}"
llm_query_prompt = PromptTemplate(template=llm_query_template, input_variables=["program_info","topic","query"])

### FASTCHAT SYSTEM PROMPT
# These are prompts to tell the system 'who it is' when using fastchat adapter

fastchat_system_concise = """
A chat between a user and an artificial intelligence assistant. 
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
    """
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
        else:
            raise ValueError(
                f"BooleanOutputParser expected output value to either be "
                f"{self.true_val} or {self.false_val}. Received {cleaned_text}."
            )

def title_filter_context_str(program_info: Dict, topic: str) -> str:
    """
    Generate a context string for input to the title_filter_template
    """
    context_str = ''
    if topic:
        context_str = topic
    if 'specialization' in program_info:
        if context_str != '': context_str += ' for '
        context_str += program_info['specialization']
    if 'year' in program_info:
        if context_str != '': context_str += ' in '
        context_str += program_info['year']
    return context_str if context_str != '' else None

title_filter_template_2 = """
Given the following question and document title, return YES if the document is relevant to the question and NO if it isn't.
> Question: {question}
> Title: {title}
> Relevant (YES / NO):"""

title_filter_template = """
Is the following document title about {context}? Return YES or NO.
> Title: {title}
"""
title_filter_prompt = PromptTemplate(template=title_filter_template, input_variables=["context","title"], output_parser=FlexibleBooleanOutputParser)

### QA PROMPTS

# Default question answering template
default_qa_template = "Context: {doc}\n\nQuestion: {query} If you don't know the answer, just say 'I don't know'. \n\nAnswer:"
default_qa_prompt = PromptTemplate(template=default_qa_template, input_variables=["doc","query"])

# Template for Vicuna question answering
vicuna_qa_template = """
    Please answer the question based on the context below. Only use information present in the context. If you don't have
    enough information to answer, say 'There is not enough information to answer'.\n
    Context:{doc}\n
    Question:{query}""".strip()
vicuna_qa_prompt = PromptTemplate(template=default_qa_template, input_variables=["doc","query"])

# Template for question answering with Falcon-Instruct model
falcon_qa_template = """
    Answer the question based on the context below. Explain your answer. Respond "Unsure about answer" if not sure about the answer.
    Context:{doc}\n
    Question:{query}\n
    Answer:""".strip()

# Template for huggingface endpoints of the 'question answering' type (eg BERT, not text generation)
huggingface_qa_template = "{query}" + huggingface_qa.query_context_split + "{doc}"
huggingface_qa_prompt = PromptTemplate(template=huggingface_qa_template, input_variables=["doc","query"])

### FEW-SHOT PROMPTS

few_shot_example_prompt = PromptTemplate(input_variables=["doc", "query", "answer"], template="Evidence:{doc}\nQuestion:{query}\nAnswer:{answer}")

few_shot_prompt = FewShotPromptTemplate(
    examples=few_shot_examples, 
    example_prompt=few_shot_example_prompt, 
    suffix="Evidence:{doc}\nQuestion:{query}\nAnswer:", 
    input_variables=["doc","query"]
)