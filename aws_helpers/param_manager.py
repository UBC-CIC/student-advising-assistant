from botocore.exceptions import ClientError
import ast
import os
from dotenv import load_dotenv, find_dotenv
from .ssm_parameter_store import SSMParameterStore
from .get_session import get_session

class ParamManager():
    # Prefix for this app
    prefix: str = 'student-advising'
    region: str = ''
    
    """
    Convenience class to access secret keys from AWS Secrets Manager and 
    configuration from AWS Systems Manager Parameter Store
    """
    
    def __init__(self):
        """
        Init the ParamManager
        If the environment variable MODE = 'dev', 
        uses the dev version of the secrets and parameters
        """
        load_dotenv(find_dotenv())
        dev_mode = 'MODE' in os.environ and os.environ.get('MODE') == 'dev'
        self.region = os.environ.get("AWS_DEFAULT_REGION")
        
        # Debug: Print environment variables
        print("AWS_ACCESS_KEY_ID:", os.environ.get("AWS_ACCESS_KEY_ID"))
        print("AWS_SECRET_ACCESS_KEY:", os.environ.get("AWS_SECRET_ACCESS_KEY"))
        print("AWS_SESSION_TOKEN:", os.environ.get("AWS_SESSION_TOKEN"))
        print("AWS_DEFAULT_REGION:", self.region)
        
        if dev_mode:
            self.prefix += '/dev'
        
        try:
            session = get_session()
            self.param_store = SSMParameterStore(prefix='/' + self.prefix, ssm_client=session.client('ssm', region_name=self.region))
            self.secret_client = session.client(service_name='secretsmanager', region_name=self.region)
            print("AWS session and clients initialized successfully.")
        except Exception as e:
            print(f"Error initializing AWS session and clients: {e}")
            raise e
    
    def get_secret(self, name: str):
        """
        Get a secret from the AWS Secret Manager
        - name: Name of the secret
        """
        secret_id = self.prefix + '/' + name
        try:
            get_secret_value_response = self.secret_client.get_secret_value(SecretId=secret_id)
        except ClientError as e:
            print(f"Error getting secret '{secret_id}': {e}")
            raise e
        
        # Decrypts secret using the associated KMS key.
        secret = ast.literal_eval(get_secret_value_response['SecretString'])
        return secret

    def get_parameter(self, name):
        """
        Get a parameter from the SSM Parameter Store
        - name: Name of a parameter, or list of directories and name of the parameter
                eg. for the parameter '/student-advising/X', name = 'X'
                    for the parameter '/student-advising/X/Y', name = ['X','Y']
        """
        try:
            if type(name) == str:
                return self.param_store[name]
            else:
                current = self.param_store
                for section in name:
                    current = current[section]
                return current
        except Exception as e:
            print(f"Error getting parameter '{name}': {e}")
            raise e

manager: ParamManager = None

def get_param_manager() -> ParamManager:
    """
    Return a singleton ParamManager
    """
    global manager
    if not manager:
        manager = ParamManager()
    print(f"Got param manager for region: {manager.region}")
    return manager