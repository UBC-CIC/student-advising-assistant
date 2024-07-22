import os
import psycopg2
from pgvector.psycopg2 import register_vector
from aws_helpers.param_manager import get_param_manager
from aws_helpers.s3_tools import download_s3_directory
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# If process is running locally, activate dev mode
DEV_MODE = 'MODE' in os.environ and os.environ.get('MODE') == 'dev'

logger.info("DEV_MODE: %s", DEV_MODE)

### LOAD AWS CONFIG
try:
    param_manager = get_param_manager()
    logger.info("AWS session and parameter manager initialized.")
except Exception as e:
    logger.error("Error initializing parameter manager: %s", e)
    raise e

# Set variable to represent connection to RDS
connection = None

def download_all_dirs():
    """
    Downloads the directories from s3 necessary for the flask app
    """
    # Specify directories to download
    dirs = ['documents']
        
    for dir in dirs:
        try:
            download_s3_directory(dir, output_prefix='data')
            logger.info("Downloaded directory %s from S3.", dir)
        except Exception as e:
            logger.error("Error downloading directory %s: %s", dir, e)
        
download_all_dirs()

# Get RDS secrets to get connection parameters
try:
    db_secret = param_manager.get_secret("credentials/RDSCredentials")
    logger.info("Fetched RDS credentials from Secrets Manager.")
except Exception as e:
    logger.error("Error fetching RDS credentials: %s", e)
    raise e

try:
    db_user_secret = param_manager.get_secret("credentials/dbUserCredentials")
    logger.info("Fetched dbUser credentials from Secrets Manager.")
except Exception as e:
    logger.error("Error fetching dbUser credentials: %s", e)
    raise e

# Define the connection parameters
connection_params = {
    'dbname': db_secret["dbname"],
    'user': db_user_secret["username"],
    'password': db_user_secret["password"],
    'host': db_secret["host"],
    'port': db_secret["port"]
}

# Create the connection string
connection_string = " ".join([f"{key}={value}" for key, value in connection_params.items()])

try:
    # Connect to PostgreSQL database using connection string
    connection = psycopg2.connect(connection_string)
    cur = connection.cursor()
    logger.info("Connected to RDS instance!")

    # Register pgvector extension
    register_vector(connection)
    logger.info("Registered pgvector extension.")
except Exception as e:
    logger.error("Error connecting to RDS instance: %s", e)
    connection.rollback()
finally:
    if cur:
        cur.close()
    if connection:
        connection.close()
    logger.info("Connection closed.")

def return_connection():
    global connection
    if connection is None or connection.closed:
        try:
            connection = psycopg2.connect(connection_string)
            register_vector(connection)
            logger.info("Reconnected to RDS instance and registered pgvector extension.")
        except Exception as e:
            logger.error("Error reconnecting to RDS instance: %s", e)
            connection = None
    return connection