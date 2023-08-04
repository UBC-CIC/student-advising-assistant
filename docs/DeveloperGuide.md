## Demo App

The repo includes a demo flask app under flask_app, which runs the model for inference.

Prerequisites:

- Requires an S3 bucket containing the processed documents in a 'documents' folder and the document indexes in a 'indexes' folder

### Running the Demo App Locally
Some setup will be required if you want to run the app locally for development.
- Create a `.env` file under `/flask_app`
    - File contents:
    ```
    AWS_PROFILE_NAME=<insert AWS SSO profile name>
    MODE=dev
    ```
    - 'MODE=dev' activates verbose LLMs and uses the /dev versions of secrets and SSM parameters
- Create a conda env with the command `conda env create -f environment.yml` from the flask_app directory
- Activate the environment with `conda activate flaskenv` (or whichever name you chose for the environment)
- Ensure your AWS profile is logged in via `aws sso login --profile <profile name>`
- Run `flask --app application --debug run` to run the app in debug mode (specify the port with `-p <port num>`)

### Using PGVector locally
If using the RDS PGVector to store documents, some setup will be required to access the it while developing locally since the DB is within a VPC.
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