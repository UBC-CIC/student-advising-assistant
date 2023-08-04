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

If using the RDS PGVector to store documents, some setup will be required to access the it while developing locally since the DB is within a VPC. Follow this [guide](https://reflectoring.io/connect-rds-byjumphost/) here to create the bastion host only. At the step where you create the keypair, name your key-pair `bastion-host` so that a file called `bastion-host.pem` can be downloaded to your local machine. Make sure you create the ec2 bastion host in a public subnet, with public ipv4 address enabled. In the bastion host's security group, only allow inbound connection from your local device's public ipv4 address. To do that, type "What's my ip" in google search and you will see the ip address. Then in the security group, specify `<your-ip>/32` as Source. If you change your location, or your ip address is not static, you would have to update that value with the correct value.

- Modify the `.env` file in the root of `/flask_app`
    - Add these variables:

        ```bash
        EC2_PUBLIC_IP=<public-ipv4-of-the-bastion-host>
        EC2_USERNAME=ec2-user # default ec2 username
        SSH_PRIV_KEY=bastion-host.pem
        ```

    - Also ensure that `MODE=dev` is in the `.env`
- Add the `bastion-host.pem` file in the root of `/flask_app`
- Restart the flask app, it should now be able to use the `pgvector` retriever with connection to RDS

### Building docker container and run locally for the flask app

The default platform intended for the container is `--platform=linux/amd64`. Might be able to run on MacOS. For Windows,
you probably have to get rid of the flag inside the Dockerfile before building.

Make sure you're in the root directory (`student-advising-assistant/`)and have Docker running on your computer

To build the container, replace `image-name` with the image name of your choice:

```docker
docker build . -t <image-name>:latest
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
zip -r <zip-file-name>.zip aws_helpers/ flask_app/ Dockerfile -x "*/.*" -x ".*"
```

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
