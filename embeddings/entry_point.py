"""
Entry point script for document embedding and upload to index
Depending on the value of the SSM Parameter '/student-advising/dev/retriever/RETRIEVER_NAME',
will upload embedded documents to RDS

Requires that the associated secret credentials are supplied in secrets manager:
- RDS: student-advising/credentials/RDSCredentials

Note: If using for RDS, this must be run within the same VPC
"""
import subprocess
import torch
import sys
import requests
sys.path.append('..')
from aws_helpers.param_manager import get_param_manager
from aws_helpers.rds_tools import execute_and_commit

RETRIEVER_CONFIG_SSM_KEY = "retriever"
RETRIEVER_NAME_SSM_KEY = "RETRIEVER_NAME"

param_manager = get_param_manager()
retriever_config = param_manager.get_parameter('retriever')
retriever_name = retriever_config[RETRIEVER_NAME_SSM_KEY]
ENDPOINT_TYPE = param_manager.get_parameter(['generator','ENDPOINT_TYPE'])


args = ["--compute_embeddings", "--clear_index"]
if torch.cuda.is_available() or torch.backends.mps.is_available():
    args.append("--gpu_available")
else:
    args.append("--no-gpu_available")

try:
    if retriever_name == "pgvector":
        command = ["python", "rds_data_ingestion.py"] + args if ENDPOINT_TYPE == "bedrock" else ["python", "rds_combined_script.py"] + args
        # Ensure that the arguments are sanitized and valid
        safe_args = [str(arg) for arg in args]
        subprocess.run(command + safe_args, check=True)
    else:
        raise ValueError(f"Unsupported retriever type '{retriever_name}', supported type is 'pgvector'.")
except Exception as e:
    raise e

# Update the embedding log table
sql = """
    INSERT into update_logs (datetime) 
    VALUES (current_timestamp);
    """
    
execute_and_commit(sql)

# Ping the Flask app to initialize
app_url = param_manager.get_parameter('BEANSTALK_URL')
# Without SSL Certificate, this ping will fail but do not worry!
# If you only have an HTTP URL, manually add '/initialize' at the end of URL
# to initialize app after embedding task is complete.
initialize_url = app_url + '/initialize'

print(f"Formatted URL: {initialize_url}")

try:
    response = requests.get(url = initialize_url, timeout = 300)
except Exception as e:
    print(str(e))
    raise Exception("Failed to initialize the Flask app after uploading embeddings")

if response.status_code != 200:
    print(f"Received status code {response.status_code} while initializing the Flask app at {initialize_url}")
    print(f"Response text: {response.text}")
    raise Exception("Failed to initialize the Flask app after uploading embeddings")