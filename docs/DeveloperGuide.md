# Developer Guide

This guide contains some additional instructions for developing the system.

## Table of Contents
- [Requirements](#requirements)
- [Local App Development](#local-app-development)
- [Development of `document_scraping` and `embeddings`](#development-of-document_scraping-and-embeddings)
- [CDK](#cdk)

## Requirements

To develop the system, you must have the following installed on your device:

- [git](https://git-scm.com/downloads)
- [git lfs](https://git-lfs.com/)
- [AWS Account](https://aws.amazon.com/account/)
- [GitHub Account](https://github.com/)
- [AWS CLI](https://aws.amazon.com/cli/)
- [AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/cli.html)
- [Python 3+](https://www.python.org/downloads/)

If you are on a Windows device, it is recommended to install the [Windows Subsystem For Linux](https://docs.microsoft.com/en-us/windows/wsl/install), which lets you run a Linux terminal on your Windows computer natively. Some of the steps will require its use. [Windows Terminal](https://apps.microsoft.com/store/detail/windows-terminal/9N0DX20HK701) is also recommended for using WSL.


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
If using the RDS PGVector to store documents, some setup will be required to access the it while developing locally since the RDS db is hidden within a VPC.
- Modify the `.env` file in the root of `/flask_app`
    - Add these variables:
        ```
        EC2_PUBLIC_IP=<insert ip>
        EC2_USERNAME=<insert username>
        SSH_PRIV_KEY=bastion-host.pem
        ```
    - Also ensure that `MODE=dev` is in the `.env`
- Add the `bastion-host.pem` file in the root of `/flask_app`
    - *details about how to get the file*
- Connect to a VPN within the set of allowed IP addresses for your bastion host
    - *details about this*
- Restart the flask app, it should now be able to use the `pgvector` retriever with connection to RDS

### Docker Container

These instructions are to test the docker container that will run the Flask app on Elastic Beanstalk. If not developing the docker container, you can skip this step and move directly to "Uploading the app to beanstalk".

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

Repeat those step for the embedding script. Remember to use the `embedding.Dockerfile`` instead.

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
    --parameters DatabaseStack:dbUsername=<username> \
    --parameters InferenceStack:retrieverType=<retrieverType> \
    --profile <profile-name>
```