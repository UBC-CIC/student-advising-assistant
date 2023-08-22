import os
from sshtunnel import SSHTunnelForwarder

"""
SSH Forwarder is needed when using Bastion Host to connect to AWS resources
from a local dev environment.

Requires that the following environment variables are set:
EC2_PUBLIC_IP = public ipv4 addr of the ec2 bastion host
EC2_USERNAME = ec2 username for the bastion host
SSH_PRIV_KEY = path to the .pem file for the bastion host's private key
"""

def start_ssh_forwarder(host: str, port: int):
    """
    Starts an SSH forwarder for local connection to AWS Service
    though bastion host.
    - host: the private AWS service host name
    - port: the private AWS service port
    
    Requires that the AWS Service is in the same VPC as the Bastion Host,
    and that it accepts incoming requests on the port.

    Returns: the ssh tunnel forwarder server
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