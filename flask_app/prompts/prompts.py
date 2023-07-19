
from langchain import PromptTemplate
from langchain.prompts.few_shot import FewShotPromptTemplate
from prompts.degree_requirements import few_shot_examples
import huggingface_qa

### GENERAL QUERY TRANSORMATIONS

retriever_context_template = "{program_info} : {topic}"

llm_query_template = "{program_info} On the topic of {topic}: {query}"
llm_query_prompt = PromptTemplate(template=llm_query_template, input_variables=["program_info","topic","query"])

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