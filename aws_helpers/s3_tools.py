import os
import logging 
from botocore.exceptions import ClientError
from .get_session import get_session
from .param_manager import get_param_manager

log = logging.getLogger(__name__)
default_bucket_name = get_param_manager().get_parameter(['documents','S3_BUCKET_NAME'])
default_client = get_session().client('s3')

def download_single_file(s3_key:str, local_path:str, bucket_name=default_bucket_name,  s3_client=default_client):
    """
    Downloads a file from an S3 bucket and saves it to the specified local path.

    Arguments:
        bucket_name: Name of the S3 bucket.
        s3_key: S3 object key (path) of the file.
        local_path: Local path where the file will be saved.
        s3_client: the boto3 S3 client
    """
    try:
        s3_client.download_file(bucket_name, s3_key, local_path)
        log.info(f"File s3://{bucket_name}/{s3_key} downloaded successfully to {local_path}")
    except Exception as e:
        log.error(f"Error downloading file: {e}")

def download_s3_directory(directory: str, ecs_task: bool = False, s3_client = default_client, output_prefix: str = './', bucket_name: str = default_bucket_name):
    """
    Download a folder from s3
    - s3_client: s3 client to use
    - directory: the path of the s3 directory 
    - output_prefix: the path to save the directory in
    - bucket_name: the bucket name to use
    - ecs_task: boolean indicating if the download is being performed by an ECS task
    """
    if ecs_task:
        output_prefix = '/app/data'

    if not os.path.exists(output_prefix):
        os.mkdir(output_prefix)

    continuation_token = None
    while True:

        list_kwargs = {
                'Bucket': bucket_name,
                'StartAfter': f"{directory}/",
                'Prefix': f"{directory}/",
            }
        
        if continuation_token:
            list_kwargs['ContinuationToken'] = continuation_token
                
        response = s3_client.list_objects_v2(**list_kwargs)
        
        for obj in response['Contents']:
            directory_list = obj['Key'].split(f"{directory}/")[-1].split('/')
            out_path = os.path.join(output_prefix,*directory.split('/'),*directory_list)
            dirpath =  os.path.dirname(out_path)
            if os.path.exists(out_path):
                if os.path.getmtime(out_path) >= obj['LastModified'].timestamp():
                    log.info(f"Skipping '{obj['Key']}', no changes since last download to '{out_path}'")
                    continue
            if not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            log.info(f"Downloading '{obj['Key']}' to '{out_path}'")
            s3_client.download_file(bucket_name, obj['Key'], out_path)
        
        if 'NextContinuationToken' not in response:
            break

        continuation_token = response['NextContinuationToken']
        
def upload_directory_to_s3(directory: str, s3_client = default_client, bucket_name: str = default_bucket_name):

    """
    Arguments:
        directory: the directory that will be recursively uploaded
        s3_client: the S3 client generated with boto3.client("s3")
        bucket_name: the name of the s3 bucket to upload
    """
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, directory)
            s3_key = os.path.join(directory, os.path.dirname(relative_path), file)
            s3_client.upload_file(local_path, bucket_name, s3_key)
            log.info(f"Uploaded {local_path} to S3 bucket {bucket_name} with key {s3_key}")

def upload_file_to_s3(file_path: str, s3_file_path: str, s3_client = default_client, bucket_name: str = default_bucket_name):

    """
    Uploads a file to S3.

    Arguments:
        file_path: the file's local path.
        s3_file_path: the path (key) of the file that will be created on S3.
        s3_client: the S3 client generated with boto3.client("s3")
        bucket_name: the name of the s3 bucket to upload
    """
    try:
        s3_client.upload_file(file_path, bucket_name, s3_file_path)
        log.info(f"Successfully uploaded file to S3 at {s3_file_path}")
    except FileNotFoundError as e:
        log.error("The file you want to upload does not exist in your local directory.")
        log.error("Make sure you are inside the document_scraping directory.")
    except ClientError as e:
        log.error(f"There was an error uploading the file to S3: {str(e)}")