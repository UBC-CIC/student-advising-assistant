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

To run the demo locally:
- Create a conda env with the command `conda env create -f environment.yml` from the flask_app directory
- Activate the environment with `conda activate flaskenv` (or whichever name you chose for the environment)
- Ensure your AWS profile is logged in via `aws sso login --profile <profile name>`
- Run `flask --app application --debug run` to run the app in debug mode (specify the port with `-p <port num>`)

**Note:** To run locally (not in AWS), the app will require a .env file under ./flask_app:
```
AWS_PROFILE_NAME=<insert AWS SSO profile name>
```

- Optionally, add 'MODE=dev' for verbose LLMs and to use the /dev versions of secrets and parameters

### Building docker container and run locally for the flask app

The default platform intended for the container is `--platform=linux/amd64`. Might be able to run on MacOS. For Windows,
you probably have to get rid of the flag inside the Dockerfile before building.

Make sure you're in the root directory (`student-advising-assistant/`)and have Docker running on your computer

To build the container, replace `image-name` with the image name of your choice:

```docker
docker build -t <image-name>:latest
```

Run the container: 

Here we're mounting the aws credentials directory so that the container have access to the aws cli profiles

```docker
docker run -v ${HOME}/.aws/credentials:/root/.aws/credentials:ro --env-file .env -d -p <localhost-port>:5000 <image-name>:latest
```

The docker run command mount the directory which contains the aws cli credentials into the container, which is the only way make it run locally. On the cloud, every boto3 called will be called with the service's IAM role.

replace `localhost-port` with any port, usually 5000, but can use 5001 or other if 5000 is already used by other processes.

### Zipping modules for Beanstalk

Run this command when you're in the root folder `student-advising-assistant`

```bash
zip -r demo-app-v2.zip aws_helpers/ flask_app/ Dockerfile -x "*/.*" -x ".*"
``````