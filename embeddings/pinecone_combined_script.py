from langchain.embeddings import HuggingFaceEmbeddings
import pinecone
from pinecone_text.sparse import BM25Encoder
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import json
import pickle
import os
import shutil
import pathlib
import ast
from s3_helpers import download_s3_directory, upload_s3_directory
import doc_loader
import batcher
from combined_embeddings import concat_embeddings

### CONFIGURATION

# AWS Secrets Manager config for the Pinecone secret API key and region
secret_name = "dev/PineconeIndex"
region_name = "us-west-2"
    
# If true, loads previously computed embeddings from s3 rather than computing new embeddings
embeddings_precomputed = False

# If true, recreates the pinecone index from scratch before inserting vectors
should_clear_index = True

# If true, tries to use GPU for embeddings
gpu_available = True

# Config for the pinecone index
index_config = {
    "name": "langchain-hybrid-index",
    "namespace": "all-mpnet-base-v2",
    #"namespace": "multi-qa-mpnet-base-dot-v1",
    "pod-type": "p1",
    #"base_embedding_model": "sentence-transformers/multi-qa-mpnet-base-dot-v1", # can be changed to any huggingface model name
    "base_embedding_model": "sentence-transformers/all-mpnet-base-v2", # can be changed to any huggingface model name
    "sparse_vector_model": "bm25", # changing this value not change the sparse model used
    "base_embedding_dimension": 768, # depends on the base embedding model
    "embeddings": [
        "parent_title_embeddings",
        "title_embeddings",
        "document_embeddings"
    ]
}

### DOCUMENT LOADING 

# Load the csv of documents from s3
docs_dir = 'documents' 
download_s3_directory(docs_dir)
docs = doc_loader.load_docs(os.path.join(docs_dir, "website_extracts.csv"), eval_strings=False)
metadatas = [doc.metadata for doc in docs]
ids = [doc.metadata['doc_id'] for doc in docs]

# Load precomputed embeddings
embed_dir = f"embeddings-{index_config['namespace']}"
if embeddings_precomputed: 
    download_s3_directory(embed_dir)

# Create the different lists of texts for embedding
title_sep = ' : ' # separator to use to join titles into strings
parent_titles = [title_sep.join(doc.metadata['parent_titles']) for doc in docs]
titles = [title_sep.join(doc.metadata['titles']) for doc in docs]
combined_titles = [f"{parent_title}{title_sep}{title}" for (title,parent_title) in zip(titles,parent_titles)]
texts = [doc.page_content for doc in docs]

### CREATE EMBEDDINGS (DENSE VECTORS)

index_dir = 'indexes'

# Load the base embedding model from huggingface
device = 'cuda' if gpu_available else 'cpu'
base_embeddings = HuggingFaceEmbeddings(model_name=index_config['base_embedding_model'], model_kwargs={'device': device})

# Lists of embeddings to compute
embedding_names = ['parent_title_embeddings', 'title_embeddings', 'combined_title_embeddings', 'document_embeddings']
embedding_texts = [parent_titles,titles,combined_titles,texts]

# For each embedding, compute the embedding and save to pickle file
embeddings = {}
if embeddings_precomputed:
    for file in pathlib.Path(embed_dir).glob('*.pkl'):
        with open(file, "rb") as f:
            data = pickle.load(f)
            embeddings[file.stem] = data['embeddings']
            print(f'Loaded embeddings {file.stem}')
else:
    os.makedirs(embed_dir,exist_ok=True)
    
    ### Create dense vectors
    for name,content in zip(embedding_names,embedding_texts):
        print(f'Computing {name}')
        embeddings[name] = base_embeddings.embed_documents(content)

        print(f'Saving {name} to directory')
        with open(os.path.join(embed_dir, f'{name}.pkl'), "wb") as f:
            pickle.dump({'embeddings': embeddings[name]}, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    ### Create sparse vectors
    
    # Combine titles with texts for BM25
    bm25_texts = [combined_title + '\n\n' + text for (combined_title,text) in zip(combined_titles,texts)]

    # Initialize BM25 and fit the texts
    print('Fitting bm25 to the texts')
    bm25 = BM25Encoder()
    bm25.fit(bm25_texts)
    
    # Store BM25 params as json
    bm25.dump(os.path.join(pinecone_dir,"bm25_params.json"))

    # Encode the texts to sparse vectors
    print('Computing bm25 vectors')
    embeddings[index_config['sparse_vector_model']] = bm25.encode_documents(bm25_texts)

    print('Saving bm25 vectors to directory')
    with open(os.path.join(embed_dir, 'bm25.pkl'), "wb") as f:
        pickle.dump({'embeddings': embeddings[index_config['sparse_vector_model']]}, f, protocol=pickle.HIGHEST_PROTOCOL)

### CREATE PINECONE INDEX

# Save index config to json
pinecone_dir = os.path.join(index_dir,'pinecone')
os.makedirs(pinecone_dir,exist_ok=True)
with open(os.path.join(pinecone_dir,'index_config.json'),'w') as f:
    json.dump(index_config,f)

# Load the API key from AWS secrets
def get_pinecone_secret():
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    # Decrypts secret using the associated KMS key.
    secret = ast.literal_eval(get_secret_value_response['SecretString'])
    return secret

# Connect to pinecone API
secret = get_pinecone_secret()
pinecone.init(      
	api_key=secret['PINECONE_KEY'],      
	environment=secret['PINECONE_REGION']    
)

# Create new index if necessary
indexes = pinecone.list_indexes()

def create_index():
    """
    Creates new pinecone index
    """
    metadata_config = {
        "indexed": ["faculty","program"]
    }

    pinecone.create_index(
        name = index_config['name'],
        dimension = len(index_config['embeddings'])*index_config['base_embedding_dimension'],
        metric = "dotproduct",
        pod_type = index_config['pod-type'],
        metadata_config = metadata_config
    )
    print(f"Created Pinecone index {index_config['name']}")

def wait_on_index(index: str):
    """
    Takes the name of the index to wait for and blocks until it's available and ready.
    From https://support.pinecone.io/hc/en-us/articles/8747593242909-How-to-wait-for-index-creation-to-be-complete
    """
    ready = False
    while not ready: 
        try:
            desc = pinecone.describe_index(index)
            if desc[7]['ready']:
                return True
        except pinecone.core.client.exceptions.NotFoundException:
            # NotFoundException means the index is created yet.
            pass
    sleep(5)    
    
if index_config['name'] not in indexes:
    create_index()
    print(f"Waiting for new index to be ready")
    wait_on_index(index_config['name'])
else:
    print(f"Pinecone index {index_config['name']} already exists")
    if should_clear_index:
        index = pinecone.Index(index_config['name'])
        print(f"Clearing the existing pinecone index for namespace {index_config['namespace']}")
        index.delete(deleteAll=True, namespace=index_config['namespace'])

pinecone_index = pinecone.Index(index_config['name'])

# Create the vectors to upload to pinecone
bm25_vectors = embeddings[index_config['sparse_vector_model']]
embedding_list = [embeddings[name] for name in index_config['embeddings']]
embeddings = {} # Don't need to keep embeddings in memory

for bm25_vector in bm25_vectors:
    bm25_vector["values"] = [float(x) for x in bm25_vector["values"]]

# Batch upserts due to upsert limits:
# https://docs.pinecone.io/docs/limits

def concat_embeds_and_upsert(ids, sparse_vectors, metadatas, texts, *embedding_list):
    # Concat embeddings in batches to prevent running out of RAM on small instances
    combined_embeddings = concat_embeddings(embedding_list)
    pinecone_upsert_batch(ids, sparse_vectors, combined_embeddings, metadatas, texts)
    
def pinecone_upsert_batch(ids, sparse_vectors, dense_vectors, metadatas, texts):
    vectors = []
    for (_id, sparse, dense, metadata, content) in zip(ids, sparse_vectors, dense_vectors, metadatas, texts):
        if len(sparse['values']) == 0: continue # skip empty document
        
        vectors.append({
            'id': str(_id),
            'values': dense,
            'metadata': {"context": content, **metadata}, # Include plain text as metadata
            'sparse_values': sparse
        })
    
    # Upload the documents to the pinecone index
    pinecone_index.upsert(vectors=vectors, namespace=index_config['namespace'])

print('Beginning batches upsert to pinecone index')
batcher.perform_batches(concat_embeds_and_upsert, 32, [ids, bm25_vectors, metadatas, texts, *embedding_list], verbose=True)
print('Completed upsert to pinecone index')

### UPLOAD TO S3 & CLEANUP
    
# Upload documents to s3
upload_s3_directory(embed_dir)
upload_s3_directory(docs_dir)
upload_s3_directory(index_dir)

# Delete directories from disk
shutil.rmtree(docs_dir)
shutil.rmtree(embed_dir)
shutil.rmtree(index_dir)