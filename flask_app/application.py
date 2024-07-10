
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
from flask import Flask, request, render_template, Response, redirect, url_for, session
import json
import os
import numpy as np
import ast
from typing import List
from importlib import reload
from aws_helpers.rds_tools import execute_and_fetch
from langchain_community.embeddings.bedrock import BedrockEmbeddings
from langchain_aws import BedrockLLM
from flask_session import Session
from aws_helpers.param_manager import get_param_manager

### LOAD AWS CONFIG
param_manager = get_param_manager()

# Additional Constants for Authentication
VALID_USERNAME = param_manager.get_parameter("USERNAME")
VALID_PASSWORD = param_manager.get_parameter("PASSWORD")
SESSION_TYPE = 'filesystem'

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

# Session Configuration
application.config["SESSION_PERMANENT"] = False
application.config["SESSION_TYPE"] = SESSION_TYPE
Session(application)

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
    except Exception as e:
        print(f"Error: {str(e)}")
        return []
    
    top_docs = []
    try:
        cur = conn.cursor()
        # Get the top N most similar documents using the KNN <=> operator
        cur.execute(f"""
                        SELECT doc_id, url, titles, text, links
                        FROM phase_2_embeddings
                        ORDER BY embedding <=> %s
                        LIMIT {number}
                    """, (embedding_array,))
        results = cur.fetchall()
        # Each item in list will be a dictionary with key values 'url' and 'text'
        for result in results:
            doc_dict = doc_dict = {"doc_id": result[0],
                        "url": result[1],
                        "titles": result[2],
                        "text": result[3],
                        "links": ast.literal_eval(result[4])}
            top_docs.append(doc_dict)
        cur.close()
    except Exception as e:
        print(f"Error when retrieving! {str(e)}")
        conn.rollback()
    finally:
        cur.close()
    return top_docs

# Split documents based on character limit, 8,000 tokens is roughly 32,000 characters, set max characters to 25,000
def split_docs(docs, max_chars=25000):
    total_length = len(format_docs(docs))
    print(total_length)
    removed_docs = []

    while total_length > max_chars and docs:
        removed_doc = docs.pop()
        removed_docs.append(removed_doc)
        total_length = len(format_docs(docs))
    return {"docs": docs, "removed_docs": removed_docs}

def check_if_documents_relates(docs, user_prompt, llm):

    system_prompt = "Provide a short explaination if the document is relevant to the question or not."

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
        response = llm.invoke(prompt).strip()

        doc_info = {"doc_id": doc['doc_id'],
                    "url": doc['url'],
                    "titles": doc['titles'],
                    "text": doc['text'],
                    "links": doc['links'],
                    "relate": response}
        doc_relates.append(doc_info)

    return doc_relates

def answer_prompt(user_prompt, number_of_docs):

    # Initialize the Bedrock Embeddings model
    embeddings = BedrockEmbeddings()

    docs = get_docs(embeddings.embed_query(user_prompt), number_of_docs)

    divided_docs = split_docs(docs)

    documents = format_docs(divided_docs["docs"])

    # Get the LLM we want to invoke
    llm = BedrockLLM(
                        model_id=LLAMA_3_8B
                    )

    system_prompt = "You are a helpful UBC student advising assistant who answers with kindness while being concise."

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

    check_docs = check_if_documents_relates(divided_docs["docs"], user_prompt, llm)
    check_removed_docs = check_if_documents_relates(divided_docs["removed_docs"], user_prompt, llm)

    return {"answer": answer, "docs": check_docs, "removed_docs": check_removed_docs}
        
# Authentication decorator
def login_required(f):
    def wrap(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@application.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username != VALID_USERNAME or password != VALID_PASSWORD:
            error = 'Invalid Credentials. Please try again.'
        else:
            session['logged_in'] = True
            return redirect(url_for('home'))
    return render_template('login.html', error=error)

@application.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@application.route('/', methods=['GET'])
@login_required
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

    # Get the answer returned by the LLM
    main_response = response["answer"]
    # Get the documents used to help generate the answer
    docs = response["docs"]

    # Log the question
    context_str = ' : '.join([value for value in list(program_info.values()) + [topic] if len(value) > 0])
    log_question(question, context_str, main_response, [doc['doc_id'] for doc in docs])
    
    # Render the results
    return render_template('ans.html',title=app_title,question=question,context=context_str,docs=docs,
                           form=request.form.to_dict(), main_response=main_response,
                           removed_docs=response["removed_docs"], last_updated=last_updated_time)

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
@login_required
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