# Developer Guide

### Local Flask app deployment
Some additional steps are required to deploy the web app locally for development

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