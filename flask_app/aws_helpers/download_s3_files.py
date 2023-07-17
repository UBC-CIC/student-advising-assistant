import os
from .get_session import get_session
from .param_manager import get_param_manager

bucket_name = get_param_manager().get_parameter(['documents','S3_BUCKET_NAME'])
    
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
        out_path = os.path.join(output_prefix,*directory.split('/'),*directory_list)
        dirpath =  os.path.dirname(out_path)
        if os.path.exists(out_path):
            if os.path.getmtime(out_path) >= obj['LastModified'].timestamp():
                print(f"Skipping '{obj['Key']}', no changes since last download to '{out_path}'")
                continue
        if not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        print(f"Downloading '{obj['Key']}' to '{out_path}'")
        s3_client.download_file(bucket_name, obj['Key'], out_path)

def download_all_dirs(retriever: str):
    """
    Downloads the directories from s3 necessary for the app
    - retriever: Specify the retriever so the appropriate documents can be downloaded
                 Choices are 'faiss', 'pinecone'
    """
    # Login to s3
    session = get_session()
    s3 = session.client('s3')
    
    # Specify directories to download
    dirs = ['documents']
    if retriever == 'faiss':
        dirs.append('indexes/faiss')
    else:
        dirs.append('indexes/pinecone')
    
    for dir in dirs:
        download_s3_directory(s3, dir, 'data')
    s3.close()
        
if __name__ == '__main__':
    download_all_dirs('pinecone')