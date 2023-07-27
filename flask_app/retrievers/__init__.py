from .base import Retriever
from .pinecone_retriever import PineconeRetriever
from .pgvector_retriever import PGVectorRetriever, PGVector
from aws_helpers.param_manager import get_param_manager

# Names of AWS secret manager secrets for each supported retriever type
RETRIEVER_SECRETS = { 
    'pinecone': 'retriever/PINECONE',
    'pgvector': 'credentials/RDSCredentials'
}

def load_retriever(retriever_name: str, **kwargs) -> Retriever:
    """
    Loads a supported retriever type
    Requires that the associated secrets are set in AWS secret manager
    - retriever_name: 'pinecone' or 'pgvector'
    """
    param_manager = get_param_manager()
    secret = param_manager.get_secret(RETRIEVER_SECRETS[retriever_name])
    
    if retriever_name == 'pinecone':
        return PineconeRetriever(secret['PINECONE_KEY'], secret['PINECONE_REGION'], **kwargs)
    elif retriever_name == 'pgvector':
        connection_string = PGVector.connection_string_from_db_params(
            driver="psycopg2",
            host=secret["host"],
            port=secret["port"],
            database=secret["dbname"],
            user=secret["username"],
            password=secret["password"],
        )
        return PGVectorRetriever(connection_string, **kwargs)
    
__all__ = ['Retriever','load_retriever']