# Document Embedding Scripts

These files are intended for use in AWS SageMaker Studio, to convert the processed documents from the scripts in `document_scraping` into a ready-to-use document index for document retrieval.

## AWS RDS with PGVector
The rds_combined_script.py will load the processed documents, convert them to sparse and dense embeddings, and upload the results to an AWS RDS DB. The accompanying jupyter notebook is for convenience, it can be used to download requirements and run the script.

Prerequisites:
- Requires an API key and region name for Pinecone.io in AWS Secrets Manager. The secret name and region name can be changed in the configuration section at the top of `rds_combined_script.py`
- Requires an s3 bucket with the processed documents from document_scraping under a documents folder.

## Pinecone.io
The pinecone_combined_script.py will load the processed documents, convert them to sparse and dense embeddings, and upload the results to a hybrid pinecone index. The accompanying jupyter notebook is for convenience, it can be used to download requirements and run the script.

Prerequisites:
- Requires an API key and region name for Pinecone.io in AWS Secrets Manager. The secret name and region name can be changed in the configuration section at the top of `pinecone_combined_script.py`
- Requires an s3 bucket with the processed documents from document_scraping under a documents folder.