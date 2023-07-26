import boto3
import json
import os
import sys
sys.path.append("../")
from aws_helpers.get_session import get_session

LAMBDA_FUNCTION_NAME = "store-feedback-to-db"
AWS_DEFAULT_REGION = "ca-central-1"

def store_feedback(json_payload: str):
    """
    Invoke a Lambda Function to store the feedback into the PostgreSQL database
    Performing the operation through Lambda since the database is in a private subnet

    Arguments:
        json_payload: the json string of the payload, obtainable with json.dumps()
    Return:
        A dictionary of the JSON response
    """

    session = get_session()
    # need region_name when running from EC2/ECS, or AWS_DEFAULT_REGION env variable
    lambda_client = session.client("lambda", region_name=AWS_DEFAULT_REGION) 

    # Invoke the Lambda function
    response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType='RequestResponse',  # Set to 'Event' for asynchronous invocation
        Payload=json_payload
    )

    # Parse and return the response from the Lambda function
    return json.loads(response['Payload'].read())


if __name__ == "__main__":
    response = store_feedback(json.dumps({"key": "Hello from localhost"}))
    print(response)