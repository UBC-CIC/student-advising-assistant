import os
import boto3
from dotenv import load_dotenv, find_dotenv

def get_session():

    """
    Gets a boto3 session
    If AWS_PROFILE_NAME is defined in environment variables, authenticates with this profile (allows for running locally)
    On AWS container, gets the session automatically
    """

    load_dotenv(find_dotenv())

    if "AWS_PROFILE_NAME" in  os.environ:
        print(f"Named profile found, running custom session: {os.environ.get('AWS_PROFILE_NAME')}")
        return boto3.Session(profile_name=os.environ.get("AWS_PROFILE_NAME"))
    else:
        print("No named profile found, running default session")
        return boto3.Session()