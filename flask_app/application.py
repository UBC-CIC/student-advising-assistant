
"""
Simple flask application to demo model inference
"""

from flask import Flask, request, render_template
import json
from langchain_inference import run_chain
from feedback import store_feedback
import os 
import csv

### Constants
FACULTIES_PATH = os.path.join('data','documents','faculties.txt')
FEEDBACK_CSV_PATH = os.path.join('data','feedback.csv')

### Globals (set upon load)
application = Flask(__name__)
faculties = {}
instructions = ''

def read_text(filename: str, as_json = False):
    result = ''
    with open(filename) as f:
        if as_json: result = json.load(f)
        else: result = f.read()
    return result

@application.route('/', methods=['GET'])
def home():
    # Render the form template
    return render_template('index.html', faculties=faculties)

@application.route('/answer', methods=['POST'])
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
    docs, main_response, alerts, removed_docs = await run_chain(program_info,topic,question,start_doc=start_doc)

    # Render the results
    context_str = ' : '.join(list(program_info.values()) + [topic])
    return render_template('ans.html',question=question,context=context_str,docs=docs,
                           form=request.form.to_dict(), main_response=main_response, alerts=alerts,
                           removed_docs=removed_docs)

@application.route('/feedback', methods=['POST'])
async def feedback():
    # Save submitted feedback
    fields = ['feedback-hidden-helpful','feedback-hidden-question','feedback-hidden-context',
              'feedback-hidden-reference-ids','feedback-hidden-response','feedback-reference-select','feedback-comments']
    data = [request.form[field] for field in fields]

    payload = json.dumps(dict(zip(fields, data)))

    try:
        response = store_feedback(json_payload=payload)
        print(response)
    except Exception as e:
        # Handle any exceptions that occur during the Lambda invocation
        print(f"ERROR occurs when submitting the feedback to the database: {e}")
    
    # with open(FEEDBACK_CSV_PATH, "w") as csv_file:
    #     writer = csv.writer(csv_file, delimiter=',')
    #     writer.writerow(data)
            
    # Render the results
    return render_template('feedback.html')
    
def setup():
    # Upon loading, load the available settings for the form
    global faculties, instructions
    faculties = read_text(FACULTIES_PATH,as_json=True)

setup()

# Run the application
# must be like this to run from container
if __name__ == "__main__":
    application.run(host="0.0.0.0")