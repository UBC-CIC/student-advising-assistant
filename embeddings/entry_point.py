"""
Entry point script for document embedding and upload to index
Depending on the value of the SSM Parameter '/student-advising/dev/retriever/RETRIEVER_NAME',
will upload embedded documents either to Pinecone or RDS

Requires that the associated secret credentials are supplied in secrets manager:
- Pinecone: student-advising/dev/retriever/PINECONE
    - keys: PINECONE_KEY, PINECONE_REGION
- RDS: student-advising/credentials/RDSCredentials

Note: If using for RDS, this must be run within the same VPC
"""
import subprocess
import torch
import sys
sys.path.append('..')
from aws_helpers.param_manager import get_param_manager

RETRIEVER_CONFIG_SSM_KEY = "retriever"
RETRIEVER_NAME_SSM_KEY = "RETRIEVER_NAME"

param_manager = get_param_manager()
retriever_config = param_manager.get_parameter('retriever')
retriever_name = retriever_config[RETRIEVER_NAME_SSM_KEY]

args = ["--compute_embeddings", "--clear_index"]
if torch.cuda.is_available():
    args.append("--gpu_available")
else:
    args.append("--no-gpu_available")

if retriever_name == "pinecone":
    subprocess.run(["python", "pinecone_combined_script.py", *args])
elif retriever_name == "pgvector":
    subprocess.run(["python", "rds_combined_script.py", *args])
else:
    raise ValueError(f"Unsupported retriever type '{retriever_name}', supported types are 'pinecone' and 'pgvector'.")