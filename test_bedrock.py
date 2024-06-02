import boto3
import json

bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-west-2')

prompt = "What is RAG in AI?"

kwargs = {
    "modelId": "meta.llama3-8b-instruct-v1:0",
    "contentType": "application/json",
    "accept": "application/json",
    "body": json.dumps({
        "prompt": prompt,
        "max_gen_len": 512,
        "temperature": 0.5,
        "top_p": 0.9
    })
}

response = bedrock_runtime.invoke_model(**kwargs)
# body = json.loads(response['body'].read())
# generated_text = body['generation']
print(json.loads(response['body'].read())['generation'])