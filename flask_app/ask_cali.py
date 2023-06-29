
"""
Simple flask app to demo model inference
"""

from flask import Flask, request, render_template
import json
from langchain_inference import run_chain

app = Flask(__name__)
faculties = {}
BASE_FILEPATH = './'

@app.route('/', methods=['GET'])
def home():
    # Render the form template
    return render_template('index.html',faculties = faculties)

@app.route('/answer', methods=['POST'])
async def answer():
    # Submission from the form template
    context = ''
    question = request.form['question']
    if request.form['context']:
        context = request.form['context']
    else:
        filter_elems = ['faculty','program','specialization','year']
        context = {filter_elem: request.form[filter_elem] for filter_elem in filter_elems if request.form[filter_elem] != 'all'}

    # Checks if the form was submitted with a starting document id
    start_doc = request.args.get('doc')
    if start_doc:
        start_doc = int(start_doc)

    # Run the model inference
    docs = await run_chain(context,question,start_doc=start_doc)

    # Render the results
    context_str = context if type(context) == str else ' : '.join(context.values())
    return render_template('ans.html',question=question,context=context_str,answers=docs,
                           form=request.form.to_dict())

def setup():
    # Upon loading, load the available settings for the form
    global faculties
    with open(BASE_FILEPATH + 'data/faculties.txt','r') as f:
        faculties = json.load(f)

setup()