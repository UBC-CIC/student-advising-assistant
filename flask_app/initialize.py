import os
import psycopg2
from pgvector.psycopg2 import register_vector
from aws_helpers.param_manager import get_param_manager
from aws_helpers.s3_tools import download_single_file

# If process is running locally, activate dev mode
DEV_MODE = 'MODE' in os.environ and os.environ.get('MODE') == 'dev'

### LOAD AWS CONFIG
param_manager = get_param_manager()

# Set variable to represent connection to RDS
connection = None

def download_faculties_json():
    """
    Downloads the faculties.json file from the documents directory in S3.
    """
    s3_key = 'documents/faculties.json'
    local_path = 'data/documents/faculties.json'
    download_single_file(s3_key, local_path)

# Download the 'faculties.json' file from S3
download_faculties_json()

# Get RDS secrets to get connection parameters
db_secret = param_manager.get_secret("credentials/RDSCredentials")

# Define the connection parameters
connection_params = {
    'dbname': db_secret["dbname"],
    'user': db_secret["username"],
    'password': db_secret["password"],
    'host': db_secret["host"],
    'port': db_secret["port"]
}

# Create the connection string
connection_string = " ".join([f"{key}={value}" for key, value in connection_params.items()])

try:
    # Connect to PostgreSQL database using connection string
    connection = psycopg2.connect(connection_string)
    cur = connection.cursor()
    print("Connected to RDS instance!")

    # Register pgvector extension
    register_vector(connection)
except:
    print("Error connecting to RDS instance!")
    connection.rollback()
finally:
    cur.close()
    connection.close()

def return_connection():
    global connection
    if connection is None or connection.closed:
        try:
            connection = psycopg2.connect(connection_string)
            register_vector(connection)
        except Exception as e:
            print(f"Error reconnecting to RDS instance: {e}")
            connection = None
    return connection