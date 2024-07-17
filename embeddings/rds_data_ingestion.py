import os
import pandas as pd
import numpy as np
import json
import psycopg2
import ast
import math
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from langchain_community.embeddings.bedrock import BedrockEmbeddings
import sys
import shutil
import logging
sys.path.append('..')
from aws_helpers.param_manager import get_param_manager
from aws_helpers.s3_tools import download_s3_directory, upload_directory_to_s3, upload_file_to_s3
from aws_helpers.ssh_forwarder import start_ssh_forwarder

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

### CONFIGURATION
# AWS Secrets Manager config for the RDS secret
secret_name = "credentials/RDSCredentials"
param_manager = get_param_manager()

### DOCUMENT LOADING
# Load the csv of documents from s3
docs_dir = 'documents'
download_s3_directory(docs_dir)
extracts_df = pd.read_csv(os.path.join(docs_dir, "website_extracts.csv"))
# Print first 5 rows of CSV
logger.info(f"First 5 rows of the CSV:\n{extracts_df.head()}")

### CREATING moded.csv and moded_with_embeddings.csv
# Select only the columns we want
selected_columns_df = extracts_df[['doc_id', 'url', 'titles', 'text', 'links', 'context', 'program', 'faculty', 'specialization']]

# Remove rows where 'text' is null
selected_columns_df = selected_columns_df.dropna(subset=['text'])

# Function to transform links dictionary to list of URLs
def transform_links(links_str):
    try:
        links_dict = ast.literal_eval(links_str)
        urls_list = [url for url, _ in links_dict.values()]
        return urls_list
    except (SyntaxError, ValueError):
        return []

# Apply the transformation to the 'links' column
selected_columns_df['links'] = selected_columns_df['links'].apply(transform_links)

# Define the path for the new CSV file
file_path = 'moded.csv'

try:
    # Save the new CSV file
    selected_columns_df.to_csv(file_path, index=False)
    logger.info(f"New CSV file created at: {file_path}")
except Exception as e:
    logger.error(f"Error creating new CSV file at: {file_path}, {e}")

# Generate embeddings and save to moded_with_embeddings.csv
try:
    # Load the CSV file
    data = pd.read_csv(file_path)

    # Initialize the Bedrock Embeddings model
    embeddings = BedrockEmbeddings()

    # Initialize a list to store the embeddings
    embeddings_list = []

    # Iterate over each row in the DataFrame
    for index, row in data.iterrows():
        # Get text
        raw_text = row['text']
        text = "text: " + raw_text

        # Prepare a list of column names to be concatenated
        columns = ['context', 'program', 'faculty', 'specialization']
        data_to_be_embedded = text

        # Concatenate non-null columns to the data_to_be_embedded
        for col in columns:
            raw_value = row[col]
            if not pd.isna(raw_value):
                data_to_be_embedded += f" {col}: {raw_value}"

        # Generate the embedding
        embedding = embeddings.embed_query(data_to_be_embedded)
        embeddings_list.append(embedding)
        if (index + 1) % 500 == 0:
            logger.info(f"Processed {index + 1}/{len(data)} rows")

    # Add the embeddings to the DataFrame
    data['embedding'] = embeddings_list

    # Save the updated DataFrame to a new CSV file
    data.to_csv('moded_with_embeddings.csv', index=False)
    logger.info(f"moded_with_embeddings.csv created successfully.")
except Exception as e:
    logger.error(f"Error creating moded_with_embeddings: {e}")

### SANITY CHECKS
# Load the CSV file with embeddings
file_path_with_embeddings = 'moded_with_embeddings.csv'
data_with_embeddings = pd.read_csv(file_path_with_embeddings)

# Perform the sanity check to count the number of rows
number_of_rows = len(data_with_embeddings)
logger.info(f"The number of rows in the 'moded_with_embeddings.csv' file is: {number_of_rows}")

# Print the first row of the CSV file
first_row = data_with_embeddings.iloc[0]
logger.info(f"The first row in the 'moded_with_embeddings.csv' file is:\n{first_row.to_dict()}")

### CONNECT TO RDS
try:
    # Get RDS secrets to get connection parameters
    db_secret = param_manager.get_secret(secret_name)

    forwarder_port = None
    if "MODE" in os.environ and os.environ["MODE"] == "dev":
        # Use an SSH forwarder so that we can connect to the pgvector RDS in a private subnet
        try:
            server = start_ssh_forwarder(db_secret["host"], db_secret["port"])
            forwarder_port = server.local_bind_port
        except Exception as e:
            logger.error(f'Could not set up ssh forwarder for local connection to rds: {str(e)}')

    # Define the connection parameters
    connection_params = {
        'dbname': db_secret["dbname"],
        'user': db_secret["username"],
        'password': db_secret["password"],
        'host': 'localhost' if forwarder_port else db_secret["host"],
        'port': forwarder_port if forwarder_port else db_secret["port"]
    }

    # Create the connection string
    connection_string = " ".join([f"{key}={value}" for key, value in connection_params.items()])

    # Connect to PostgreSQL database using connection string
    connection = psycopg2.connect(connection_string)
    cur = connection.cursor()

    # Install pgvector extension
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        connection.commit()
    except psycopg2.Error as e:
        logger.error(f"Error when installing pgvector extension: {e}")
        connection.rollback()

    # Register the vector type with psycopg2
    register_vector(connection)

    ### CREATE EMBEDDINGS TABLE
    # Create table to store embeddings and metadata
    table_create_command = """
    CREATE TABLE IF NOT EXISTS phase_2_embeddings (
                id bigserial primary key,
                doc_id text,
                url text,
                titles jsonb,
                text text,
                links jsonb,
                embedding vector(1536)
                );
                """

    try:
        cur.execute(table_create_command)
        connection.commit()
        logger.info("Table created!")
    except psycopg2.Error as e:
        logger.error(f"Error creating embeddings table: {e}")
        connection.rollback()

    ### POPULATE EMBEDDINGS TABLE
    # Load the CSV file with embeddings
    logger.info("Loading the CSV file...")
    data_with_embeddings = pd.read_csv(file_path_with_embeddings)

    # Check the type of the embedding column
    embedding_type = type(first_row['embedding'])
    logger.info(f"The type of the embedding column is: {embedding_type}")

    # Function to convert string representation of list to numpy array
    def parse_embedding(embedding_str):
        return np.array(eval(embedding_str))

    # Apply the function to the embedding column if it's a string
    if isinstance(first_row['embedding'], str):
        logger.info("Converting the embedding column to numpy arrays...")
        data_with_embeddings['embedding'] = data_with_embeddings['embedding'].apply(parse_embedding)
        logger.info("Conversion complete.")
    else:
        logger.info("Embeddings are not strings, they are a list of floats")

    # Verify the conversion
    first_row_converted = data_with_embeddings.iloc[0]
    logger.info(f"The first row after converting the 'embedding' column:\n{first_row_converted.to_dict()}")

    # Convert 'titles' and 'links' columns to JSON format
    data_with_embeddings['titles'] = data_with_embeddings['titles'].apply(json.dumps)
    data_with_embeddings['links'] = data_with_embeddings['links'].apply(json.dumps)

    # Prepare the list of tuples to insert
    logger.info("Preparing the list of tuples for insertion...")
    data_list = [(row['doc_id'],
                  row['url'],
                  row['titles'],
                  row['text'],
                  row['links'],
                  row['embedding']) for index, row in data_with_embeddings.iterrows()]
    logger.info("Preparation complete.")

    # Use execute_values to perform batch insertion
    logger.info("Performing batch insertion...")
    execute_values(cur, "INSERT INTO phase_2_embeddings (doc_id, url, titles, text, links, embedding) VALUES %s", data_list)

    # Commit after we insert all embeddings
    logger.info("Committing the transaction...")
    connection.commit()

    logger.info("Batch insertion complete!")

    ### SANITY CHECKS ON EMBEDDINGS TABLE
    num_records = 0
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM phase_2_embeddings;")
        num_records = cur.fetchone()[0]
        logger.info(f"Number of vector records in table: {num_records}\n")
    except psycopg2.Error as e:
        logger.error(f"Error when counting number of rows in embeddings table: {e}")
        connection.rollback()

    try:
        # Print the first record in the table, for sanity-checking
        cur.execute("SELECT * FROM phase_2_embeddings LIMIT 1;")
        records = cur.fetchall()
        logger.info(f"First record in table: {records}")
    except psycopg2.Error as e:
        logger.error(f"Error when printing first row in embeddings table: {e}")
        connection.rollback()

    ### APPLY INDEXING
    # Drops existing indexes on the embedding column
    def drop_existing_indexes():
        try:
            cur.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'phase_2_embeddings' 
                AND indexdef LIKE '%embedding%' 
                AND indexdef NOT LIKE '%pkey%';
            """)
            indexes = cur.fetchall()
            for index in indexes:
                cur.execute(f"DROP INDEX IF EXISTS {index[0]};")
            connection.commit()
            logger.info("Dropped existing indexes on embedding column!")
        except psycopg2.Error as e:
            logger.error(f"Error dropping existing indexes: {e}")
            connection.rollback()

    # Create an index on the data for faster retrieval
    def create_index(index_method, distance_measure):
        drop_existing_indexes()
        try:
            if index_method == 'hnsw':
                cur.execute(f'CREATE INDEX ON phase_2_embeddings USING hnsw (embedding {distance_measure})')
            elif index_method == 'ivfflat':
                num_lists = num_records / 1000
                if num_lists < 10:
                    num_lists = 10
                if num_records > 1000000:
                    num_lists = math.sqrt(num_records)

                cur.execute(f'CREATE INDEX ON phase_2_embeddings USING ivfflat (embedding {distance_measure}) WITH (lists = {num_lists});')

            connection.commit()
            logger.info("Created Index!")
        except psycopg2.Error as e:
            logger.error(f"Error when indexing embeddings table: {e}")
            connection.rollback()

    create_index('hnsw', 'vector_l2_ops')

    ### SANITY CHECKS ON INDEX IN EMBEDDINGS TABLE
    # Perform sanity check to print all indexes on phase_2_embeddings
    try:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'phase_2_embeddings';")
        indexes = cur.fetchall()
        logger.info("Indexes on phase_2_embeddings table:")
        for index in indexes:
            logger.info(index[0])
    except psycopg2.Error as e:
        logger.error(f"Error during sanity check: {e}")
        connection.rollback()

    # Function to get details of an index
    def get_index_details(index_name):
        index_details_query = f"""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE indexname = '{index_name}';
        """

        try:
            cur.execute(index_details_query)
            index_details = cur.fetchone()
            if index_details:
                logger.info(f"Details of index '{index_name}':")
                logger.info(f"Index Name: {index_details[0]}")
                logger.info(f"Index Definition: {index_details[1]}")
            else:
                logger.info(f"No details found for index '{index_name}'.")
        except psycopg2.Error as e:
            logger.error(f"Error when checking indexing details: {e}")
            connection.rollback()

    # Verify details of the created index
    get_index_details('phase_2_embeddings_embedding_idx')
finally:
    cur.close()
    connection.close()

### UPLOAD TO S3 & CLEANUP

# Upload documents to s3
upload_directory_to_s3(docs_dir)
upload_file_to_s3('moded.csv', 'embeddings-amazon-titan/moded.csv')
upload_file_to_s3('moded_with_embeddings.csv', 'embeddings-amazon-titan/moded_with_embeddings.csv')

# Delete directories from disk
shutil.rmtree(docs_dir)
# Remove CSV files
try:
    os.remove('moded.csv')
    os.remove('moded_with_embeddings.csv')
    logger.info("Successfully removed 'moded.csv' and 'moded_with_embeddings.csv' from disk.")
except OSError as e:
    logger.error(f"Error removing file: {e}")