
"""
Simple flask application to demo model inference
"""

# Loads env variable when running locally
from dotenv import load_dotenv
load_dotenv()

## Add parent directory to path for aws_helpers
import sys
sys.path.append('..')

# Imports
from flask import Flask, request, render_template, Response
import json
import os 
import numpy as np
from typing import List
from importlib import reload 
from aws_helpers.rds_tools import execute_and_fetch
from langchain_community.embeddings.bedrock import BedrockEmbeddings
from langchain_aws import BedrockLLM

### Constants
FACULTIES_PATH = os.path.join('data','documents','faculties.json')
TITLE_PATH = os.path.join('static','app_title.txt')
DEFAULTS_PATH = os.path.join('static','defaults.json')
DEV_MODE = 'MODE' in os.environ and os.environ.get('MODE') == 'dev'

# Defining Constants for LLMs
LLAMA_3_8B = "meta.llama3-8b-instruct-v1:0"
LLAMA_3_70B = "meta.llama3-70b-instruct-v1:0"
MISTRAL_7B = "mistral.mistral-7b-instruct-v0:2"
MISTRAL_LARGE = "mistral.mistral-large-2402-v1:0"

### Globals (set upon load)
application = Flask(__name__)
app_title = None
faculties = {}
last_updated_time = None
initialize_module = None
store_feedback_module = None

# Helper functions
def read_text(filename: str, as_json = False):
    result = ''
    with open(filename) as f:
        if as_json: result = json.load(f)
        else: result = f.read()
    return result

def log_question(question: str, context: str, answer: str, reference_ids: List[int]):
    # Save submitted question and answer
    fields = ['question','context','answer','reference_ids']
    data = [question, context, answer, reference_ids]

    payload = json.dumps(dict(zip(fields, data)))
    
    try:
        response = feedback_module.store_feedback(json_payload=payload, logging_only=True)
        print(response)
    except Exception as e:
        # Handle any exceptions that occur during the Lambda invocation
        print(f"ERROR occurs when submitting the feedback to the database: {e}")

def get_last_updated_time():
    """
    Get the last time documents were updated from the RDS table
    Return as a formatted datetime
    """
    sql = """
        SELECT datetime
        FROM update_logs 
        ORDER BY id DESC 
        LIMIT 1"""
    result = execute_and_fetch(sql, dev_mode=DEV_MODE)
    return result[0][0].strftime("%m/%d/%Y, %H:%M:%S (UTC)")

# Format all texts in the doc as one string when we pass prompt to LLM
def format_docs(docs):
    formatted_docs = "\n".join([f"Document {idx}:\n{doc['text']}" for idx, doc in enumerate(docs, 1)])
    return formatted_docs

# Get most similar documents from the database
def get_docs(query_embedding, number):
    embedding_array = np.array(query_embedding)

    # Get RDS connection
    try:
        conn = initialize_module.return_connection()
        curr = conn.cursor()
    except Exception as e:
        print(f"Error: {str(e)}")
        return []
    
    top_docs = []
    try:
        cur = conn.cursor()
        # Get the top N most similar documents using the KNN <=> operator
        cur.execute(f"SELECT url, text FROM test_embeddings ORDER BY embedding <=> %s LIMIT {number}", (embedding_array,))
        results = cur.fetchall()
        # Each item in list will be a dictionary with key values 'url' and 'text'
        for result in results:
            doc_dict = {"url": result[0], "text": result[1]}
            top_docs.append(doc_dict)
        cur.close()
    except Exception as e:
        print(f"Error when retrieving! {str(e)}")
        conn.rollback()
    finally:
        cur.close()
    return top_docs

def check_if_documents_relates(docs, user_prompt, llm):

    system_prompt = """You are tasked with determining if the document helps answer the question. 
                        Either provide an answer saying "Yes, ..." with a short explaination 
                        or "No, ..." with a short explaination based on your analysis.
                        Avoid any unrelated information or questions."""

    doc_relates = []
    for doc in docs:
        if llm.model_id == LLAMA_3_8B or llm.model_id == LLAMA_3_70B:
            prompt = f"""
                <|begin_of_text|>
                <|start_header_id|>system<|end_header_id|>
                {system_prompt}
                <|eot_id|>
                <|start_header_id|>question<|end_header_id|>
                {user_prompt}
                <|eot_id|>
                <|start_header_id|>document<|end_header_id|>
                {doc['text']}
                <|eot_id|>
                <|start_header_id|>assistant<|end_header_id|>
                """
        else:
            prompt = f"""Here is a queston that a user asked: {user_prompt}.
                Here is the text from a document: {doc['text']}.
                {system_prompt}
                """
        response = llm.invoke(prompt)
        doc_relates_dict = {"url": doc['url'], "text": doc['text'], "relate": response}
        doc_relates.append(doc_relates_dict)

    return doc_relates

def answer_prompt(user_prompt, number_of_docs):

    # Initialize the Bedrock Embeddings model
    embeddings = BedrockEmbeddings()

    docs = get_docs(embeddings.embed_query(user_prompt), number_of_docs)

    documents = format_docs(docs)

    # Get the LLM we want to invoke
    llm = BedrockLLM(
                        model_id=LLAMA_3_8B
                    )

    system_prompt = "You are a helpful UBC student advising assistant who answers with kindness while being concise. Only generate one human readable answer"

    if llm.model_id == LLAMA_3_8B or llm.model_id == LLAMA_3_70B:
        prompt = f"""
            <|begin_of_text|>
            <|start_header_id|>system<|end_header_id|>
            {system_prompt}
            <|eot_id|>
            <|start_header_id|>user<|end_header_id|>
            {user_prompt}
            <|eot_id|>
            <|start_header_id|>documents<|end_header_id|>
            {documents}
            <|eot_id|>
            <|start_header_id|>assistant<|end_header_id|>
            """
    else:
        prompt = f"""{system_prompt}.
            Here is the question: {user_prompt}.
            Here are the source documents: {documents}
            """

    answer = llm.invoke(prompt)

    check_docs = check_if_documents_relates(docs, user_prompt, llm)

    return {"answer": answer, "check_docs": check_docs}
        
@application.route('/', methods=['GET'])
def home():
    if not initialize_module:
        # App is not yet initialized
        return render_template('not_initialized.html')
    
    # Render the form template
    return render_template('index.html',title=app_title,faculties=faculties,last_updated=last_updated_time,defaults=defaults)

@application.route('/answer', methods=['POST'])
async def answer():
    if not initialize_module:
        # App is not yet initialized
        return render_template('not_initialized.html',title=app_title)
    
    # Submission from the form template
    topic = request.form['topic']
    question = request.form['question']
    filter_elems = ['faculty','program','specialization','year']
    program_info = {filter_elem: request.form[filter_elem] for filter_elem in filter_elems}
    
    formatted_question = ""
    if program_info['faculty']:
        formatted_question += f"I am in {program_info['faculty']}. "
    
    if program_info['program']:
        formatted_question += f"I am in the {program_info['program']} program. "
    
    if program_info['specialization']:
        formatted_question += f"I am in the {program_info['specialization']} specialization. "
    
    if program_info['year']:
        formatted_question += f"I am in my {program_info['year']}. "
    
    if topic:
        formatted_question += f"The topic of the question is {topic}. "
    
    formatted_question += question

    response = answer_prompt(formatted_question, 5)
        
    # Neatly format the response
    formatted_response = {
        "answer": response["answer"],
        "related_documents": []
    }

    for doc in response["check_docs"]:
        formatted_response["related_documents"].append({
            "url": doc["url"],
            "text": doc["text"],
            "related": doc["relate"]
        })

    return json.dumps(formatted_response, indent=4)

@application.route('/feedback', methods=['POST'])
async def feedback():
    # Save submitted feedback
    fields = ['feedback-hidden-helpful','feedback-hidden-question','feedback-hidden-context',
              'feedback-hidden-reference-ids','feedback-hidden-response','feedback-reference-select','feedback-comments']
    data = [request.form[field] for field in fields]

    payload = json.dumps(dict(zip(fields, data)))

    try:
        response = feedback_module.store_feedback(json_payload=payload)
        print(response)
    except Exception as e:
        # Handle any exceptions that occur during the Lambda invocation
        print(f"ERROR occurs when submitting the feedback to the database: {e}")
            
    # Render the results
    return render_template('feedback.html',title=app_title)

@application.route('/initialize', methods=['GET'])
def initialize():
    """
    Imports files and runs all initial setup of the app
    Exists as an endpoint so that configuration can be reloaded on demand
    """
    global initialize_module, feedback_module
    
    if not initialize_module:
        import initialize as initialize_module
        import feedback as feedback_module
    else:
        reload(initialize_module)
        reload(feedback_module)
    
    # Upon loading, load the available settings for the form
    global faculties, last_updated_time
    faculties = read_text(FACULTIES_PATH,as_json=True)
    last_updated_time = get_last_updated_time()
    
    return "Successfully initialized the system"

@application.route('/health')
def health():
    return Response("OK", status=200)

def setup():
    """
    Setup to perform on load, before initialization
    """
    global app_title, defaults
    app_title = read_text(TITLE_PATH, as_json=False)
    defaults = read_text(DEFAULTS_PATH, as_json=True)

setup()
if DEV_MODE:
    # In dev mode, run initialization automatically for convenience
    initialize()

# Run the application
# must be like this to run from container
if __name__ == "__main__":
    application.run(host="0.0.0.0")