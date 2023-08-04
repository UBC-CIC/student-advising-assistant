import psycopg2
import os
from sshtunnel import SSHTunnelForwarder
from .param_manager import get_param_manager

param_manager = get_param_manager()
db_secret = param_manager.get_secret("credentials/RDSCredentials")

def execute_and_commit(sql: str, dev_mode = False):
    """
    Execute and commit the sql on the RDS db
    - dev_mode: If true, connects via SSH Tunneler for local development
    """
    def callback(connection, cursor):
        cursor.execute(sql)
        connection.commit()
        
    connect_and_callback(callback, dev_mode)
    
def execute_and_fetch(sql: str, dev_mode = False):
    """
    Execute the sql and return fetch results on the RDS db
    - dev_mode: If true, connects via SSH Tunneler for local development
    """
    result = None
    def callback(connection, cursor):
        nonlocal result
        cursor.execute(sql)
        result = cursor.fetchall()
        
    connect_and_callback(callback, dev_mode)
    return result

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
    return server

def connect_and_callback(callback, dev_mode = False):
    """
    Connect to the db, perform the callback, then close the connection
    Callback fn takes the connection and cursors as parameters
    - dev_mode: If true, connects via SSH Tunneler for local development
    """
    params = {
        'database': db_secret["dbname"],
        'user': db_secret["username"],
        'password': db_secret["password"],
        'host': db_secret["host"],
        'port': db_secret["port"]
    }
    
    server = None
    if dev_mode:
        server = start_ssh_forwarder(params["host"],params["port"])
        params["host"] = "localhost"
        params["port"] = server.local_bind_port
        
    connection = psycopg2.connect(**params)
    cursor = connection.cursor()
    callback(connection, cursor)
    cursor.close()
    connection.close()
    
    if dev_mode:
        server.close()