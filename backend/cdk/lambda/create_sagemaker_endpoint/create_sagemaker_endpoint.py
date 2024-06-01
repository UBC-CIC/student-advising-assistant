import json
import os
import boto3
from botocore.exceptions import ClientError

SM_REGION = os.environ["SM_REGION"]
# Role to give SageMaker permission to deploy inference endpoint and access AWS services.
SM_ROLE_ARN = os.environ["SM_ROLE_ARN"]

sm_client = boto3.client("sagemaker", region_name=SM_REGION)

# Specify the URI for the SageMaker Llama 3 8B Instruct model container
image_uri = f"339712838191.dkr.ecr.us-west-2.amazonaws.com/sagemaker-llama3-8b-instruct:latest"

MODEL_NAME = os.environ["MODEL_NAME"]
INSTANCE_TYPE = os.environ["INSTANCE_TYPE"]
NUM_GPUS = os.environ["NUM_GPUS"]
SM_ENDPOINT_NAME = os.environ["SM_ENDPOINT_NAME"] # the name of the endpoint that we will create and make request to

# container's env variables (copy from the Jumpstart notebook)
hub = {
    'SM_NUM_GPUS': NUM_GPUS,
    'MAX_INPUT_LENGTH': json.dumps(1024),  # Max length of input text
    'MAX_TOTAL_TOKENS': json.dumps(2048),  # Max length of the generation (including input text)
    'SAGEMAKER_REGION': SM_REGION,
    'SAGEMAKER_CONTAINER_LOG_LEVEL': json.dumps(20)
}

model_name = f'{MODEL_NAME}-sagemaker' # identifier
endpoint_config_name = f'{MODEL_NAME}-endpoint-config' # identifier

def lambda_handler(event, context):
    # Create model
    try:
        print("Creating Model")
        create_model_response = sm_client.create_model(
            ModelName = model_name,
            ExecutionRoleArn = SM_ROLE_ARN,
            PrimaryContainer = {
                'Image': image_uri,
                'Environment': hub
            }
        )
        print("Model creation finished")
    except ClientError as e:
        print(e.response["Error"]["Message"])

    try:
        print("Creating Endpoint Configuration")
        endpoint_config_response = sm_client.create_endpoint_config(
            EndpointConfigName=endpoint_config_name,
            ProductionVariants=[
                {
                    "VariantName": "variant1", # The name of the production variant.
                    "ModelName": model_name,
                    "InstanceType": INSTANCE_TYPE, # Specify the compute instance type.
                    "InitialInstanceCount": 1 # Number of instances to launch initially.
                }
            ]
        )
        print("Finished creating Endpoint Configuration")
    except ClientError as e:
        print(e.response["Error"]["Message"])

    try:
        print("Creating Inference Endpoint")
        create_endpoint_response = sm_client.create_endpoint(
            EndpointName=SM_ENDPOINT_NAME,
            EndpointConfigName=endpoint_config_name
        )
    except ClientError as e:
        print(e.response["Error"]["Message"])
