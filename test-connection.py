import psycopg2
import os
import sys
import json
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv
from aws_helpers.param_manager import ParamManager

load_dotenv()

EC2_PUBLIC_IP = os.environ["EC2_PUBLIC_IP"] # public ipv4 addr of the ec2 bastion host, need this in a .env
EC2_USERNAME = os.environ["EC2_USERNAME"] # ec2 username, need this in a .env
SSH_PRIV_KEY = os.environ["SSH_PRIV_KEY"] # path to the .pem file, need this in a .env
POSTGRESQL_PORT = 5432

param_mng = ParamManager()
secrets = param_mng.get_secret("credentials/RDSCredentials")

# https://medium.com/@ridhi.j.shah/connecting-to-a-private-aws-rds-instance-in-python-18b0a27fcf61
# GOATED

# SSH Tunnelling
with SSHTunnelForwarder(
    (EC2_PUBLIC_IP, 22),
    ssh_pkey=SSH_PRIV_KEY,
    ssh_username=EC2_USERNAME,
    remote_bind_address=(secrets["host"], POSTGRESQL_PORT),
    
) as server:
    # wrap the TunnelForwarder object around the psycopg2 calls
    server.start()
    print("EC2 Bastion host connected")

    params = {
        'database': secrets["dbname"],
        'user': secrets["username"],
        'password': secrets["password"],
        'host': 'localhost',
        'port': server.local_bind_port
    }

    connection = psycopg2.connect(**params)
    cursor = connection.cursor()
    print("Database connected")

    cursor.execute("SELECT * FROM feedback")
    print(cursor.fetchall())

    cursor.close()
    connection.close()