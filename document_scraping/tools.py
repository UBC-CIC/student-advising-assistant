from typing import Callable
import os
import botocore

"""
Tools used by various document scraping scripts
"""

def write_file(writer: Callable):
    """
    Calls a file writing callback, and upon an error, gives
    the user the opportunity to try saving again.
    """
    response = 'y'
    while(response == 'y'):
        try:
           writer()
           return
        except Exception as e:
            print(f"Unable to write to file: {str(e)}")
            print("Could not save the files. Make sure the files to write are not open.")
            response = input("Try saving files again? <y,n> ")

"""
Arguments:
    directory: the directory that will be recursively upload
    bucketname: the name of the s3 bucket to upload
    s3_client: the S3 client generated with boto3.client("s3")
"""

def upload_files(directory: str, bucket_name: str, s3_client: botocore.client.BaseClient):
    for root, dirs, files in os.walk(directory):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, directory)
            s3_key = os.path.join(directory, os.path.dirname(relative_path), file)
            s3_client.upload_file(local_path, bucket_name, s3_key)
            print(f"Uploaded {local_path} to S3 bucket {bucket_name} with key {s3_key}")