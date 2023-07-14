from typing import List 
from botocore.exceptions import ClientError
import ast
from .ssm_parameter_store import SSMParameterStore
from .get_session import get_session
    
class ParamManager():
    # Prefix for this app
    prefix: str = 'student-advising'
    region: str = 'ca-central-1'
    
    """
    Convenience class to access secret keys from AWS Secrets Manager and 
    configuration from AWS Systems Manager Parameter Store
    """
    
    def __init__(self):
        session = get_session()
        self.param_store = SSMParameterStore(prefix='/' + self.prefix, ssm_client=session.client('ssm', region_name=self.region))
        self.secret_client = session.client(service_name='secretsmanager', region_name=self.region)
    
    def get_secret(self, name: str):
        """
        Get a secret from the AWS Secret Manager
        - name: Name of the secret
        """
        secret_id = self.prefix + '/' + name
        try:
            get_secret_value_response = self.secret_client.get_secret_value(SecretId=secret_id)
        except ClientError as e:
            raise e
        
        # Decrypts secret using the associated KMS key.
        secret = ast.literal_eval(get_secret_value_response['SecretString'])
        return secret

    def get_parameter(self, name: str | List[str]):
        """
        Get a parameter from the SSM Parameter Store
        - name: Name of a parameter, or list of directories and name of the parameter
                eg. for the parameter '/student-advising/X', name = 'X'
                    for the parameter '/student-advising/X/Y', name = ['X','Y']
        """
        if type(name) == str:
            return self.param_store[name]
        else:
            current = self.param_store
            for section in name:
                current = current[section]
            return current
        
manager: ParamManager = None

def get_param_manager() -> ParamManager:
    """
    Return a singleton ParamManager
    """
    global manager
    if not manager:
        manager = ParamManager()
    return manager