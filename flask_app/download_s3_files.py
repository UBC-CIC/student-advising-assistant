import boto3
from dotenv import load_dotenv
import os
import json

# Load session and settings
def load_json_file(file: str):
    with open(file,'r') as f: 
        return json.load(f)
    
load_dotenv()
s3_config = load_json_file('s3_config.json')
bucket_name = s3_config['bucket-name']
    
def download_s3_directory(s3_client, directory: str, output_prefix: str, bucket_name: str = bucket_name):
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
        out_path = os.path.join(output_prefix,directory,*directory_list)
        dirpath =  os.path.dirname(out_path)
        if os.path.exists(out_path):
            if os.path.getmtime(out_path) >= obj['LastModified'].timestamp():
                print(f"Skipping '{obj['Key']}', no changes since last download to '{out_path}'")
                continue
        if not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        print(f"Downloading '{obj['Key']}' to '{out_path}'")
        s3_client.download_file(bucket_name, obj['Key'], out_path)

def download_all_dirs():
    """
    Downloads the directories from s3 necessary for the app
    """

    # check if the environment variable AWS_PROFILE_NAME exists and its value is not an empty string
    if "AWS_PROFILE_NAME" in os.environ and os.environ["AWS_PROFILE_NAME"]:
        session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE_NAME"))
    else:
        session = boto3.Session()
    s3_client = session.client('s3')
    dirs = ['indexes','documents']
    for dir in dirs:
        download_s3_directory(s3_client, s3_config['directories'][dir],'data')
    s3_client.close()
        
if __name__ == '__main__':
    download_all_dirs()