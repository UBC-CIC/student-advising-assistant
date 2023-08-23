#!/bin/bash
container=ghcr.io/huggingface/text-generation-inference:1.0.1
model=arya555/vicuna-7b-v1.5-hf
input_length=1024
total_tokens=2048
volume=/opt/dlami/nvme/data
mkdir -p $volume
docker run --detach --name vicuna --gpus all --shm-size 1g -p 8080:80 --mount type=bind,source=$volume,target=/data $container --model-id $model --revision main --max-input-length $input_length --max-total-tokens $total_tokens --max-batch-prefill-tokens $total_tokens
--//--