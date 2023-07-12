import sagemaker
from sagemaker.s3 import S3Uploader
from sagemaker.s3 import S3Downloader
import json
import os

sagemaker_session = sagemaker.Session()
aws_role = sagemaker_session.get_caller_identity_arn()
aws_region = sagemaker_session.boto_session.region_name
default_bucket = sagemaker_session.default_bucket()
s3 = sagemaker_session.boto_session.resource("s3")
s3_config = None

def load_config():
    global s3_config
    with open ('s3_config.json','r') as f: s3_config = json.load(f)

load_config()
bucket = s3_config['bucket-name']

def upload_s3_directory(directory: str, bucket: str = bucket, session = sagemaker_session):
    """
    Recursively upload a directory to s3
    - directory: the path of directory to upload
    - bucket: the bucket name to use
    """
    for root, dirs, files in os.walk(directory):
        for file in files:
            local_path = os.path.join(root, file)
            s3_prefix = root
            upload_to_s3(local_path, s3_prefix, bucket)
    
def download_s3_directory(directory: str, bucket: str = bucket, session = sagemaker_session):
    """
    Recursively download a directory from s3
    - directory: the path of directory to upload
    - bucket: the bucket name to use
    """
    base_uri = f"s3://{bucket}/{directory}"
    
    for uri in S3Downloader.list(base_uri, sagemaker_session=session):
        if os.path.splitext(uri)[1] != '': # Check URI is for a file, not a directory
            local_path = os.path.join(directory, os.path.relpath(uri, base_uri))
            local_dirpath = os.path.dirname(local_path)
            os.makedirs(local_dirpath, exist_ok=True)
            print(f"Downloading from {uri} to {local_path}")
            S3Downloader.download(uri, local_dirpath, sagemaker_session = session)
            
def upload_to_s3(local_filepath: str, prefix: str = None, bucket: str = bucket, session = sagemaker_session):
    """
    Upload a file / directory (non recursively) to s3
    - local_filepath: the path of file / directory to upload
    - prefix: path to upload to in s3
    - bucket: the bucket name to use
    """
    uri = ''
    if prefix:
        uri = f"s3://{bucket}/{prefix}"
    else:
        uri = f"s3://{bucket}"
    print(f"Uploading {local_filepath} to {uri}")
    return S3Uploader.upload(local_filepath, uri, sagemaker_session=session)

def download_from_s3(s3_filepath: str, local_filepath: str, bucket: str = bucket, session = sagemaker_session):
    """
    Download a file / directory (non recursively) from s3
    - s3_filepath: the path of the s3 file / directory
    - local_filepath: the path to save the object to locally
    - bucket: the bucket name to use
    """
    uri = f"s3://{bucket}/{s3_filepath}"
    print(f"Downloading from {uri} to {local_filepath}")
    os.makedirs(local_filepath, exist_ok=True)
    S3Downloader.download(uri, local_filepath, sagemaker_session = session)