
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
from flask import Flask, request, render_template, Response, jsonify
import json
import os
import logging
from typing import List
from importlib import reload 
from aws_helpers.rds_tools import execute_and_fetch
from aws_helpers.logging import set_boto_log_levels
import boto3

# Initialize Amazon Bedrock client
# bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-west-2')

### Constants
FACULTIES_PATH = os.path.join('data','documents','faculties.json')
TITLE_PATH = os.path.join('static','app_title.txt')
DEFAULTS_PATH = os.path.join('static','defaults.json')
DEV_MODE = 'MODE' in os.environ and os.environ.get('MODE') == 'dev'

### Globals (set upon load)
application = Flask(__name__)
app_title = None
faculties = {}
last_updated_time = None
langchain_inference_module = None
store_feedback_module = None

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
set_boto_log_levels(logging.WARNING)

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
        logger.info(f"SUCCESS: feedback stored when logging question: {response}")
        print(response)
    except Exception as e:
        # Handle any exceptions that occur during the Lambda invocation
        logger.error(f"ERROR: submitting feedback to the database when logging question did not work: {e}")
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

# For debugging to see the content inside a doc
def document_to_dict(doc):
    return {
        'page_content': doc.page_content,
        'metadata': doc.metadata
    }

# For debugging to see all the doc items in docs
def convert_docs_to_json(docs):
    return [document_to_dict(doc) for doc in docs]
        
@application.route('/', methods=['GET'])
def home():
    if not langchain_inference_module:
        # App is not yet initialized
        return render_template('not_initialized.html')
    
    # Render the form template
    return render_template('index.html',title=app_title,faculties=faculties,last_updated=last_updated_time,defaults=defaults)

@application.route('/answer', methods=['POST'])
async def answer():
    if not langchain_inference_module:
        # App is not yet initialized
        return render_template('not_initialized.html',title=app_title)
    
    # Submission from the form template
    topic = request.form['topic']
    question = request.form['question']
    filter_elems = ['faculty','program','specialization','year']
    program_info = {filter_elem: request.form[filter_elem] for filter_elem in filter_elems}
    
    # Checks if the form was submitted with a starting document id
    start_doc = request.args.get('doc')
    if start_doc:
        start_doc = int(start_doc)

    # Run the model inference
    config = {
        'start_doc': start_doc
    }
    docs, main_response, alerts, removed_docs = await langchain_inference_module.run_chain(program_info,topic,question,config)
    context = "\n".join([doc.page_content for doc in docs])

    # Log the question
    context_str = ' : '.join([value for value in list(program_info.values()) + [topic] if len(value) > 0])
    log_question(question, context_str, main_response, [doc.metadata['doc_id'] for doc in docs])
    
    # For debugging to print what is passed to render_template
    docs_json = convert_docs_to_json(docs)
    logger.info(f"docs_json from application.py: {docs_json}")
    logger.info(f"context_str from application.py: {context_str}")
    logger.info(f"main_response from application.py: {main_response}")
    logger.info(f"question from application.py: {question}")
    logger.info(f"context from application.py: {context}")

    # Render the results
    return render_template('ans.html',title=app_title,question=question,context=context_str,docs=docs,
                           form=request.form.to_dict(), main_response=main_response, alerts=alerts,
                           removed_docs=removed_docs, last_updated=last_updated_time)
    # return jsonify({
    #     "docs": docs_json,
    #     "context_str": context_str,
    #     "main_response": main_response,
    #     "question": question
    # })
    
    # kwargs = {
    #     "modelId": "meta.llama3-8b-instruct-v1:0",
    #     "contentType": "application/json",
    #     "accept": "application/json",
    #     "body": json.dumps({
    #         "prompt": f"{question}",
    #         "max_gen_len": 512,
    #         "temperature": 0.5,
    #         "top_p": 0.9
    #     })
    # }
    # response = bedrock_runtime.invoke_model(**kwargs)
    # bedrock_response = json.loads(response['body'].read())
    # generated_text = bedrock_response['generation']

    # # return render_template('ans.html', title=app_title, question=question, context=context_str, docs=docs,
    # #                        form=request.form.to_dict(), main_response=generated_text, alerts=alerts,
    # #                        removed_docs=removed_docs, last_updated=last_updated_time)
    # return jsonify({"generated_response": generated_text,
    #                 "context_str": context_str,
    #                 "main_response": main_response,
    #                 "question": question})

@application.route('/feedback', methods=['POST'])
async def feedback():
    # Save submitted feedback
    fields = ['feedback-hidden-helpful','feedback-hidden-question','feedback-hidden-context',
              'feedback-hidden-reference-ids','feedback-hidden-response','feedback-reference-select','feedback-comments']
    data = [request.form[field] for field in fields]

    payload = json.dumps(dict(zip(fields, data)))

    try:
        response = feedback_module.store_feedback(json_payload=payload)
        logger.info(f"SUCCESS: feedback stored successfully: {response}")
        print(response)
    except Exception as e:
        # Handle any exceptions that occur during the Lambda invocation
        logger.error(f"ERROR: submitting feedback to the database did not work: {e}")
        print(f"ERROR occurs when submitting the feedback to the database: {e}")
            
    # Render the results
    return render_template('feedback.html',title=app_title)

@application.route('/initialize', methods=['GET'])
def initialize():
    """
    Imports files and runs all initial setup of the app
    Exists as an endpoint so that configuration can be reloaded on demand
    """
    logger.info("Initializing...")
    global langchain_inference_module, feedback_module
    
    try:
        if not langchain_inference_module:
            import langchain_inference as langchain_inference_module
            import feedback as feedback_module
            logger.info("SUCCESS: modules imported")
        else:
            reload(langchain_inference_module)
            reload(feedback_module)
            logger.info("SUCCESS: modules reloaded")
        
        # Upon loading, load the available settings for the form
        global faculties, last_updated_time
        faculties = read_text(FACULTIES_PATH,as_json=True)
        last_updated_time = get_last_updated_time()
        logger.info("SUCCESS: system initialized with updates")
        
        return "Successfully initialized the system"
    except Exception as e:
        logger.error(f"ERROR: initialization failed: {str(e)}")
        return Response("Initialization failed", status=500)

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