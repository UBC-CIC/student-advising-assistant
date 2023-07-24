import os
import logging 
from botocore.exceptions import ClientError
from .get_session import get_session
from .param_manager import get_param_manager

log = logging.getLogger(__name__)
default_bucket_name = get_param_manager().get_parameter(['documents','S3_BUCKET_NAME'])
default_client = get_session().client('s3')
    
def download_s3_directory(directory: str, s3_client = default_client, output_prefix: str = './', bucket_name: str = default_bucket_name):
    """
    Download a folder from s3
    - s3_client: s3 client to use
    - directory: the path of the s3 directory 
    - output_prefix: the path to save the directory in
    - bucket: the bucket name to use
    """
    if not os.path.exists(output_prefix):
        os.mkdir(output_prefix)
    
    for obj in s3_client.list_objects_v2(Bucket=bucket_name, StartAfter=f"{directory}/", Prefix=f"{directory}/")['Contents']:
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
    Upload a file to s3

    Arguments:
        file_path: the files' local path
        s3_file_path: the path (key) of the file that will be created on s3
        s3_client: the S3 client generated with boto3.client("s3")
        bucket_name: the name of the s3 bucket to upload
    """
    try:
        s3_client.upload_file(file_path, bucket_name, s3_file_path)
        log.info(f"Successfully upload file to S3")
    except FileNotFoundError as e:
        log.error("The file you want to upload does not exist on your local directory")
        log.error("Make sure you are inside the document_scraping directory")
    except ClientError as e:
        log.error(f"There was an error uploading the file to S3: {str(e)}")
        
def download_all_dirs(retriever: str, s3_client = default_client):
    """
    Downloads the directories from s3 necessary for the flask app
    - retriever: Specify the retriever so the appropriate documents can be downloaded
                 Choices are 'faiss', 'pinecone'
    """
    # Specify directories to download
    dirs = ['documents']
    if retriever == 'faiss':
        dirs.append('indexes/faiss')
    else:
        dirs.append('indexes/pinecone')
    
    for dir in dirs:
        download_s3_directory(s3_client, dir, 'data')
    s3_client.close()
        
if __name__ == '__main__':
    download_all_dirs('pinecone')