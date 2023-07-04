# UBC Science Advising AI Assistant

## 1. Introduction
Objective: enhance the accessibility of the Academic Calendar, which is often difficult to parse systematically and confusing to read to students. Building a solution for Science Advising that leverages information from the Academic Calendar and other reliable UBC sources will give students a tool that responds to inquiries 24 hours a day. This will allow Science Advisors to redirect their focus from routine inquiries and provide better support to students. 


## 2. Overview of the Solution

### Preprocessing pipeline:
1. The solution pulls information from the following websites:
    1. UBC Academic Calendar: https://vancouver.calendar.ubc.ca/
    2. UBC Science Distillation Blog: https://science.ubc.ca/students/blog
2. Website pages are processed into document extracts
3. Document extracts are embedded into vector representation

### Query answering:
1. The query is embedded, and compared against all documents by cosine similarity
2. The most similar documents are returned
3. Additional pipeline steps involving generative LLMs will be introduced

## 3. Demo App
The repo includes a demo flask app under flask_app, which runs the model for inference.

Prerequisites:
- Requires an S3 bucket containing the processed documents in a 'documents' folder and the document indexes in a 'indexes' folder
- More details on the index creation process will be uploaded soon

To run the demo:
- Create a conda env with the command `conda env create -f environment.yml` from the flask_app directory
- Activate the environment with `conda activate flaskenv` (or whichever name you chose for the environment)
- Ensure your AWS profile is logged in via `aws sso login --profile <profile name>`
- Run `flask --app ask_cali --debug run` to run the app in debug mode

**Note:** To work properly, the app will require a .env file under ./flask_app:
```
# For huggingface token see https://huggingface.co/docs/hub/security-tokens
HUGGINGFACEHUB_API_TOKEN= <insert huggingface api token>
AWS_PROFILE_NAME=<insert AWS SSO profile name>
```
