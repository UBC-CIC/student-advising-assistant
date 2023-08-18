# Developer Guide

This guide contains some additional instructions for developing the system.

## Table of Contents
- [Requirements](#requirements)
- [Development Considerations](#development-considerations)
- [Local App Development](#local-app-development)
- [Development of `document_scraping` and `embeddings`](#development-of-document_scraping-and-embeddings)
- [CDK](#cdk)
- [Architecture Diagram and Database Schema](#architecture-diagram-and-database-schema)
- [Miscellaneous Scripts](#miscellaneous-scripts)

## Requirements

To develop the system, you must have the following installed on your device:

- [git](https://git-scm.com/downloads)
- [git lfs](https://git-lfs.com/)
- [AWS Account](https://aws.amazon.com/account/)
- [GitHub Account](https://github.com/)
- [AWS CLI](https://aws.amazon.com/cli/)
- [AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/cli.html)
- [Python 3+](https://www.python.org/downloads/)
- [Docker Desktop](https://docs.docker.com/desktop/) (make sure to install the correct version for you machine's operating system).

If you are on a Windows device, it is recommended to install the [Windows Subsystem For Linux](https://docs.microsoft.com/en-us/windows/wsl/install), which lets you run a Linux terminal on your Windows computer natively. Some of the steps will require its use. [Windows Terminal](https://apps.microsoft.com/store/detail/windows-terminal/9N0DX20HK701) is also recommended for using WSL.

## Development Considerations

This section includes aspects that should by considered when setting up this system for a particular University / Faculty. Ideally, these should be modified by a developer, hence including them in the Developer Guide rather than the User Guide.

**Zoom-out Retrieval**
By default, during the document retrieval step, the system performs a ‘zoom-out’ retrieval. The code for this is in `flask_app/langchain_inference.py`. If the system fails to find any relevant documents with the full user-provided context, it will successively remove parts of the context to see if the relevant documents are in a more general section of the information sources. This way, it will check faculty-specific policies first, then zoom out to University-wide policies if it does not find the answer there.
If a University or faculty has a different policy hierarchy, they will need to change this behaviour.

**Faculty & Program Titles**
By default, the data processing script identifies the faculty, program, and specialization titles using a regular expression matching on the titles of scraped webpages. You may need to modify the regex in `./document_scraping/processing_functions.py` to better suit 
This step may have some false positives (eg. identifies ‘Major Programs’ as the name of a major), and these positives need to be pruned from the list of programs (see the [User Guide](./UserGuide.md#pruning-the-faculties-and-programs-list)).
This step could be improved if the University has an index of all faculties, programs, and specializations which can be used instead. However, you will have to ensure that the names of faculties and programs aligns with the names of faculties and programs in the extract metadata, in order for the metadata filtering to work during document retrieval.

## Local App Development
To develop the Flask app locally, some additional steps are required.

### Local Flask deployment
1. Clone the git repo
2. Create a `.env` file under `/flask_app`
    - File contents:
    ```
    AWS_PROFILE_NAME=<insert AWS SSO profile name>
    MODE=dev
    ```
    - `MODE=dev` activates verbose LLMs and uses the `/dev` versions of secrets and SSM parameters
    - Using dev mode requires creating the dev versions of secrets and SSM parameters, eg `student-advising/generator/ENDPOINT-TYPE` -> `student-advising/dev/generator/ENDPOINT-TYPE`
2. In `/flask_app`, create a conda environment with the command `conda env create -f environment.yml`
3. Activate the environment with `conda activate flaskenv` (or whichever name you chose for the environment)
4. Ensure your AWS profile is logged in via `aws sso login --profile <profile name>` using the same profile name as specified in the `.env` file
5. Run `flask --app application --debug run` to run the app in debug mode (Optionally, specify the port with `-p <port num>`)

### Using PGVector locally

If using the RDS PGVector to store documents, some setup will be required to access the it while developing locally since the DB is within a VPC. Follow this [guide](https://reflectoring.io/connect-rds-byjumphost/) here to create the bastion host only. At the step where you create the keypair, name your key-pair `bastion-host` so that a file called `bastion-host.pem` can be downloaded to your local machine. Make sure you create the ec2 bastion host in a public subnet, with public ipv4 address enabled. In the bastion host's security group, only allow inbound connection from your local device's public ipv4 address. To do that, type "What's my ip" in google search and you will see the ip address. Then in the security group, specify `<your-ip>/32` as Source. If you change your location, or your ip address is not static, you would have to update that value with the correct value.

- Modify the `.env` file in the root of `/flask_app`
    - Add these variables:
        ```
        EC2_PUBLIC_IP=<public-ipv4-of-the-bastion-host>
        EC2_USERNAME=ec2-user # default ec2 username
        SSH_PRIV_KEY=bastion-host.pem
        ```
    - Also ensure that `MODE=dev` is in the `.env`
- Add the `bastion-host.pem` file in the root of `/flask_app`
- Restart the flask app, it should now be able to use the `pgvector` retriever with connection to RDS

### Docker Container

These instructions are to test the docker container that will run the Flask app on Elastic Beanstalk. If not developing the docker container, you can skip this step and move directly to "Uploading the app to beanstalk".

The default platform intended for the container is `--platform=linux/amd64`. Might be able to run on MacOS. For Windows,
you probably have to get rid of the flag inside the Dockerfile before building.

Make sure you're in the root directory (`student-advising-assistant/`)and have Docker running on your computer

To build the container, replace `image-name` with the image name of your choice:

```bash
docker build -t <image-name>:latest .
```

Run the container: 

Here we're mounting the aws credentials directory so that the container have access to the aws cli profiles

```bash
docker run -v ${HOME}/.aws/credentials:/root/.aws/credentials:ro --env-file .env -d -p <localhost-port>:5000 <image-name>:latest
```

The docker run command mount the directory which contains the aws cli credentials into the container, which is the only way make it run locally. On the cloud, every boto3 called will be called with the service's IAM role.

replace `localhost-port` with any port, usually 5000, but can use 5001 or other if 5000 is already used by other processes.

### Uploading the app to Beanstalk
To deploy the current version of the Flask app on Elastic Beanstalk, use the `deploy_beanstalk.sh` script in the root `student_advising_assistant`.

Linux:
1. Install the zip tool: `sudo apt install zip`

Windows:
1. Install [WSL](https://learn.microsoft.com/en-us/windows/wsl/install)
2. In WSL, install the zip tool: `sudo apt install zip`
3. In WSL, navigate to the `student_advising_assistant`

From the `student_advising_assistant` folder, call the script:
```
./deploy_beanstalk.sh \
	AWS_PROFILE_NAME=<enter profile name> \
	AWS_PROFILE_REGION=<enter region> \
	BUNDLE_NAME=student-advising-app \
	BUNDLE_VER=<enter unique version name> \
	BEANSTALK_BUCKET=<enter name of the beanstalk s3 bucket> \
	APP_NAME=student-advising-demo-app \
	APP_ENV_NAME=student-advising-demo-app-env
```
- When prompted to create the zip file, enter `Y` to zip the files
- When prompted to deploy the app, enter `1` to upload and deploy to Elastic Beanstalk

For future deployments of the app, make sure to update the BUNDLE_VER argument. The new version name must be unique.

If you simply want to create the app zip file, without uploading to beanstalk, make sure you are under `student-advising-assistant` folder and run:

``` bash
zip -r <file-name>.zip aws_helpers/ flask_app/ Dockerfile -x "*/.*" -x ".*" -x "*.env" -x "__pycache__*"
```

## Development of `document_scraping` and `embeddings`

### Dockerize the `document_scraping` and `embeddings` for the ECS and ECR

1. On Amazon ECR console, navigate to `Repositories` > `Create repository`. Create a Private repository and create a repository name. E.g `scraping-container-image`

2. On local bash shell, replace the detail in `<>` and run:

```bash
aws ecr get-login-password --profile <aws-profile-name> --region <aws-region> | docker login --username AWS --password-stdin <aws-account-number>.dkr.ecr.<aws-region>.amazonaws.com
```

3. Make sure that Docker desktop is running. Then run:

```bash
docker build -f scraping.Dockerfile -t scraping-container-image .
```

4. Tag the Docker image:

```bash
docker tag scraping-container-image:latest <aws-account-number>.dkr.ecr.<aws-region>.amazonaws.com/scraping-container-image:latest
```

5. Run:

```bash
docker push <aws-account-number>.dkr.ecr.<aws-region>.amazonaws.com/scraping-container-image:latest
```

Repeat those step for the embedding script. Remember to use the `embedding.Dockerfile` instead.

## CDK

### Bootstrap (only required once per AWS region)

```bash
cdk bootstrap aws://<account-number>/<region> --profile <profile-name>
```

### Synth (run before `cdk deploy`)

```bash
cdk synth --all --profile <profile-name>
```

### Deploy

```bash
cdk deploy --all \
    --parameters InferenceStack:retrieverType=<retriever-type> \
    --parameters InferenceStack:llmMode=true \
    --profile <profile-name>
```

#### **Extra: Taking down the deployed stacks**

To take down the deployed stack for a fresh redeployment in the future, navigate to AWS Cloudformation, click on the stack(s) and hit Delete. Please wait for the stacks in each step to be properly deleted before deleting the stack downstream. The deletion order is as followed:

1. HostingStack
2. InferenceStack
3. student-advising-DatabaseStack
4. student-advising-VpcStack

## Architecture Diagram and Database Schema

You can find the XML file for the [Draw.io](https://app.diagrams.net/) Architecture Diagram of this project [here](design_artifacts/ArchiectureDiagram.drawio.xml) to make modification. The [DbDiagram](https://dbdiagram.io/home) schema for our PostgreSQL database can also be found inside that folder, you can import into DbDiagram using the SQL file `ScienceAdvisingPostgreSQL.sql` or paste the raw text
`DbDiagramRawSchema.txt`.

## Miscellaneous Scripts

The `/misc` folder contains some additional scripts that may be useful for development. They are described below.

**Convert to Safetensors**
The `./misc/convert_to_safetensors` folder contains the pip `requirements.txt` and a script `to_safetensors.py` which will clone any public Huggingface Hub text generation model without [safetensors](https://huggingface.co/docs/safetensors/index), convert the model weights to safetensors, and upload the result to a new Huggingface Hub repo.

This allows a model without safetensors, like `lmsys/vicuna-7b-v1.5`, to be run on a smaller instance, thus saving cost. This is because the conversion from PyTorch weights to safetensors is performed when the model is loaded onto an instance, and requires twice as much memory as running the model normally. By precomputing the safetensors, we can run `lmsys/vicuna-7b-v1.5` on AWS EC2 with a `g5.xlarge` instance rather than a `g5.2xlarge` instance.

The script requires an environment variable `HF_API_KEY` to be set, containing a [Huggingface Access Token](https://huggingface.co/docs/hub/security-tokens) with write access to the repo you want to upload to (the `<new-repo-id>` below).
The `requirements.txt` assumes a CUDA-enabled system, and installs PyTorch for CUDA 11.7 - you may need to modify this for your system.
The script can be called by command line as follows, replacing `<original-repo-id>` and `<new-repo-id>` with the appropriate values.
```
pip install -r requirements.txt
python to_safetensors.py \
    --original_repo_id <original-repo-id> \
    --new_repo_id <new-repo-id>
```

If you own the original repo and wish to upload safetensors to it, then `<original-repo-id>` and `<new-repo-id>` can be the same value.

This will need to be run on an instance with sufficient memory; for `lmsys/vicuna-7b-v1.5`, a SageMaker Studio notebook running on a `ml.g4dn.2xlarge` instance was sufficient.

