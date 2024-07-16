from .base import Retriever
from .pgvector_retriever import PGVectorRetriever, PGVector
from aws_helpers.param_manager import get_param_manager
from aws_helpers.rds_tools import start_ssh_forwarder

# Names of AWS secret manager secrets for each supported retriever type
RETRIEVER_SECRETS = {
    'pgvector': 'credentials/RDSCredentials'
}
    
def load_retriever(retriever_name: str, dev_mode: bool = False, **kwargs) -> Retriever:
    """
    Loads a supported retriever type
    Requires that the associated secrets are set in AWS secret manager
    - retriever_name: 'pgvector'
    - dev_mode: if true, tries to use a workaround for local development
                when connecting to a rds database (for pgvector)
    """
    param_manager = get_param_manager()
    secret = param_manager.get_secret(RETRIEVER_SECRETS[retriever_name])
    
    if retriever_name == 'pgvector':
        print('Using pgvector retriever')
        forwarder_port = None
        if dev_mode:
            # Use an SSH forwarder so that we can connect to the pgvector RDS in a private subnet
            try:
                server = start_ssh_forwarder(secret["host"],secret["port"])
                forwarder_port = server.local_bind_port
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