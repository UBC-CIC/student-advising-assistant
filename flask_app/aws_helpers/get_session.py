import os
import boto3

def get_session():
    """
    Gets a boto3 session
    If AWS_PROFILE_NAME is defined in environment variables, authenticates with this profile (allows for running locally)
    On AWS container, gets the session automatically
    """
    if "AWS_PROFILE_NAME" in  os.environ:
        return boto3.Session(profile_name=os.environ.get("AWS_PROFILE_NAME"))
    else:
        return boto3.Session()