import json
from aws_helpers.get_session import get_session
import os

LAMBDA_FUNCTION_NAME = os.environ["FEEDBACK_LAMBDA"]
AWS_DEFAULT_REGION = os.environ["AWS_DEFAULT_REGION"]

def store_feedback(json_payload: str, logging_only: bool = False):
    """
    Invoke a Lambda Function to store the feedback into the PostgreSQL database
    Performing the operation through Lambda since the database is in a private subnet

    Arguments:
        json_payload: the json string of the payload, obtainable with json.dumps()
        logging_only: If true, stores the payload to a general logging table
                      otherwise, stores to the feedback table
    Return:
        A dictionary of the JSON response
    """

    session = get_session()
    # need region_name when running from EC2/ECS, or AWS_DEFAULT_REGION env variable
    lambda_client = session.client("lambda", region_name=AWS_DEFAULT_REGION) 

    input = json.dumps({
        'logging': logging_only,
        'payload': json_payload
    })
    
    print(input)
    
    # Invoke the Lambda function
    response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType='RequestResponse',  # Set to 'Event' for asynchronous invocation
        Payload=input
    )

    # Parse and return the response from the Lambda function
    return json.loads(response['Payload'].read())