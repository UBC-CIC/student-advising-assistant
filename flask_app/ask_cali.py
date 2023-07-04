
"""
Simple flask app to demo model inference
"""

from flask import Flask, request, render_template
import json
from langchain_inference import run_chain
import os 

app = Flask(__name__)
faculties = {}
FACULTIES_PATH = os.path.join('data','documents','faculties.txt')

@app.route('/', methods=['GET'])
def home():
    # Render the form template
    return render_template('index.html',faculties = faculties)

@app.route('/answer', methods=['POST'])
async def answer():
    # Submission from the form template
    topic = request.form['topic']
    question = request.form['question']
    filter_elems = ['faculty','program','specialization','year']
    program_info = {filter_elem: request.form[filter_elem] for filter_elem in filter_elems if request.form[filter_elem] != ''}
    
    # Checks if the form was submitted with a starting document id
    start_doc = request.args.get('doc')
    if start_doc:
        start_doc = int(start_doc)

    # Run the model inference
    docs = await run_chain(program_info,topic,question,start_doc=start_doc)

    # Render the results
    context_str = ' : '.join(list(program_info.values()) + [topic])
    return render_template('ans.html',question=question,context=context_str,answers=docs,
                           form=request.form.to_dict())

def setup():
    # Upon loading, load the available settings for the form
    global faculties
    with open(FACULTIES_PATH) as f:
        faculties = json.load(f)

setup()