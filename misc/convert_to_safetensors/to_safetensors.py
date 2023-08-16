import argparse
from huggingface_hub import login, snapshot_download, HfApi, create_repo
import os
import shutil
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

"""
Script to clone a Huggingface Hub repo, create safetensor versions
of the model weights, and upload to a new repo.

Tested only with the following model: lmsys/vicuna-7b-v1.5

Requires that the HF_API_KEY environment variable is set,
and that the key has write permissions on the repo to push to.

Usage:
python to_safetensors.py --original_repo_id org/model_name --new_repo_id your_org/model_name
"""

### ARG CONFIG
parser = argparse.ArgumentParser()
parser.add_argument('--original_repo_id',required=True,help="Huggingface Hub id of the original model")
parser.add_argument('--new_repo_id',required=True,help="Id of the new Huggingface Hub repo to push the safetensor vesion")

args = parser.parse_args()

### HF Login
login(token=os.environ.get('HF_API_KEY'),write_permission=True)

### DOWNLOAD THE REPO
model_dir = 'temp-model'
snapshot_download(repo_id=args.original_repo_id, 
	local_dir=model_dir,
	local_dir_use_symlinks=False,
	cache_dir=model_dir)

### LOAD THE MODEL
max_shard_size = "10GB"
model = AutoModelForCausalLM.from_pretrained(model_dir,
                                             cache_dir=None,
                                             device_map="auto",
                                             offload_folder="offload",
                                             low_cpu_mem_usage=True,
                                             torch_dtype=torch.bfloat16)

### SAVE SAFETENSORS
model.save_pretrained(model_dir, max_shard_size, safe_serialization=True)

### UPLOAD TO HF
create_repo(args.new_repo_id)

api = HfApi()
api.upload_folder(
    folder_path=model_dir,
    repo_id=args.new_repo_id,
    repo_type="model",
)

### REMOVE MODEL FOLDER
shutil.rmtree(model_dir)