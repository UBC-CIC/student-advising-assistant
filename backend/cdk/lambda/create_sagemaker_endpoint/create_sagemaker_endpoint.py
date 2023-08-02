import json
import os
import boto3
from botocore.exceptions import ClientError

SM_REGION = os.environ["SM_REGION"]
# Role to give SageMaker permission to deploy inference endpoint and access AWS services.
SM_ROLE_ARN = os.environ["SM_ROLE_ARN"]

sm_client = boto3.client("sagemaker", region_name=SM_REGION)

# copy directly from the jumpstart notebook / Model tab on Sagemaker console
# HuggingFace Text Generation Inference Containers
# Framework: PyTorch 2.0.0 with HuggingFace TGI, Python v3.9
# see: https://github.com/aws/deep-learning-containers/blob/master/available_images.md
image_uri = f"763104351884.dkr.ecr.{SM_REGION}.amazonaws.com/huggingface-pytorch-tgi-inference:2.0.0-tgi0.8.2-gpu-py39-cu118-ubuntu20.04"

HF_MODEL_ID = os.environ["HF_MODEL_ID"]
MODEL_NAME = os.environ["MODEL_NAME"] 
INSTANCE_TYPE = os.environ["INSTANCE_TYPE"]
NUM_GPUS = os.environ["NUM_GPUS"]
SM_ENDPOINT_NAME = os.environ["SM_ENDPOINT_NAME"] # the name of the endpoint that we will create and make request to

# container's env variables (copy from the Jumpstart notebook)
hub = {
    'HF_MODEL_ID': HF_MODEL_ID,
	'SM_NUM_GPUS': json.dumps(NUM_GPUS),
    'HF_TASK':'text-generation',
    'MAX_INPUT_LENGTH': json.dumps(1024),  # Max length of input text
    'MAX_TOTAL_TOKENS': json.dumps(2048),  # Max length of the generation (including input text)
    'SAGEMAKER_REGION': SM_REGION,
    'SAGEMAKER_CONTAINER_LOG_LEVEL': json.dumps(20)
}

if "HF_API_TOKEN" in os.environ:
    hub["HF_API_TOKEN"] = os.environ["HF_API_TOKEN"]

model_name = f'{MODEL_NAME}-huggingface' # just an identifier, not the actual full huggingface model card name
endpoint_config_name = f'{MODEL_NAME}-endpoint-config' # also just an identifier

def lambda_handler(event, context):
    
    #Create model
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
    
    # return {
    #     'statusCode': 200,
    #     'body': f"Successfully started inference endpoint creation for endpoint: {SM_ENDPOINT_NAME}"
    # }
