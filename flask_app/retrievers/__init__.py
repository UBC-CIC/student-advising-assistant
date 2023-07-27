from sshtunnel import SSHTunnelForwarder
import os
from .base import Retriever
from .pinecone_retriever import PineconeRetriever
from .pgvector_retriever import PGVectorRetriever, PGVector
from aws_helpers.param_manager import get_param_manager

# Names of AWS secret manager secrets for each supported retriever type
RETRIEVER_SECRETS = { 
    'pinecone': 'retriever/PINECONE',
    'pgvector': 'credentials/RDSCredentials'
}

def start_ssh_forwarder(host: str, port: int):
    """
    Starts an SSH forwarder for local connection to RDS
    Requires that the environment variables are set
    - host: the rds host name
    - port: the rds port
    Returns: the server's local bind port
    """
    EC2_PUBLIC_IP = os.environ["EC2_PUBLIC_IP"] # public ipv4 addr of the ec2 bastion host, need this in a .env
    EC2_USERNAME = os.environ["EC2_USERNAME"] # ec2 username, need this in a .env
    SSH_PRIV_KEY = os.environ["SSH_PRIV_KEY"] # path to the .pem file, need this in a .env

    server = SSHTunnelForwarder(
        (EC2_PUBLIC_IP, 22),
        ssh_pkey=SSH_PRIV_KEY,
        ssh_username=EC2_USERNAME,
        remote_bind_address=(host, port),
    )
    server.start()
    return server.local_bind_port
    
def load_retriever(retriever_name: str, dev_mode: bool = False, **kwargs) -> Retriever:
    """
    Loads a supported retriever type
    Requires that the associated secrets are set in AWS secret manager
    - retriever_name: 'pinecone' or 'pgvector'
    - dev_mode: if true, tries to use a workaround for local development
                when connecting to a rds database (for pgvector)
    """
    param_manager = get_param_manager()
    secret = param_manager.get_secret(RETRIEVER_SECRETS[retriever_name])
    
    if retriever_name == 'pinecone':
        return PineconeRetriever(secret['PINECONE_KEY'], secret['PINECONE_REGION'], **kwargs)
    elif retriever_name == 'pgvector':
        forwarder_port = None
        if dev_mode:
            # Use an SSH forwarder so that we can connect to the pgvector RDS in a private subnet
            try:
                forwarder_port = start_ssh_forwarder(secret["host"],secret["port"])
            except Exception as e:
                print(f'Could not set up ssh forwarder for local connection to rds: {str(e)}')
            
        connection_string = PGVector.connection_string_from_db_params(
            driver="psycopg2",
            database=secret["dbname"],
            user=secret["username"],
            password=secret["password"],
            host='localhost' if forwarder_port else secret["host"],
            port=forwarder_port if forwarder_port else secret["port"],
        )
        return PGVectorRetriever(connection_string, **kwargs)
    
__all__ = ['Retriever','load_retriever']