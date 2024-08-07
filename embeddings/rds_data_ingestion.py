import os
import boto3
import pandas as pd
import numpy as np
import json
import psycopg2
import ast
import math
from psycopg2.extras import execute_values
from psycopg2 import sql
from pgvector.psycopg2 import register_vector
import sys
import shutil
import logging
sys.path.append('..')
from aws_helpers.param_manager import get_param_manager
from aws_helpers.s3_tools import download_s3_directory, upload_directory_to_s3, upload_file_to_s3
from aws_helpers.ssh_forwarder import start_ssh_forwarder

# /mnt/data is where ECS Tasks have writing privileges due to EBS from Inference Stack

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

### CONFIGURATION
# AWS Secrets Manager config for the RDS secret
secret_name = "credentials/RDSCredentials"
user_secret_name = "credentials/dbUserCredentials"
param_manager = get_param_manager()

### CONSTANTS
VECTOR_DIMENSION = 1024

### DOCUMENT LOADING
# Load the csv of documents from s3
docs_dir = 'documents'
download_s3_directory(docs_dir, ecs_task=True)
extracts_df = pd.read_csv(os.path.join('/mnt/data', docs_dir, "website_extracts.csv"))
# Print first 5 rows of CSV
logger.info(f"First 5 rows of the CSV:\n{extracts_df.head()}")

### METHOD TO CONVERT DATA TO EMBEDDINGS
def get_bedrock_embeddings(input_text, model_id="amazon.titan-embed-text-v2:0", region_name="us-west-2"):
    # Initialize the boto3 client for Bedrock
    bedrock = boto3.client(
        service_name='bedrock-runtime',
        region_name=region_name
    )

    # Prepare the prompt and request body
    body = json.dumps({
        "inputText": input_text,
        "dimensions": VECTOR_DIMENSION,
        "normalize": True
    })

    # Set the model ID and content type
    accept = "*/*"
    content_type = "application/json"

    # Invoke the Bedrock model to get embeddings
    response = bedrock.invoke_model(
        body=body,
        modelId=model_id,
        accept=accept,
        contentType=content_type
    )

    # Read and parse the response
    response_body = json.loads(response['body'].read())
    embedding = response_body.get('embedding')

    return embedding

### CREATING moded.csv and moded_with_embeddings.csv
# Select only the columns we want
selected_columns_df = extracts_df[['doc_id', 'url', 'parent_titles', 'titles', 'text', 'links']]

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

# Modify the titles column to include parent_titles followed by titles
def combine_titles(row):
    try:
        # Parse parent_titles if it is not NaN
        parent_titles = ast.literal_eval(row['parent_titles']) if pd.notna(row['parent_titles']) else []

        # Parse titles if it is not NaN
        titles = ast.literal_eval(row['titles']) if pd.notna(row['titles']) else []

        # Remove the first element if it's an empty string
        if titles and titles[0] == '':
            titles = titles[1:]

        # Combine parent_titles and titles, ensuring no duplication if the last of parent_titles is the first of titles
        if parent_titles and titles:
            combined_titles = parent_titles + titles if parent_titles[-1] != titles[0] else parent_titles + titles[1:]
        else:
            combined_titles = parent_titles + titles

        return combined_titles
    except (SyntaxError, ValueError):
        # Return the original titles if there's an error
        return row['titles']

# Apply the combine_titles function to the 'titles' column
selected_columns_df['titles'] = selected_columns_df.apply(combine_titles, axis=1)

# Define the path for the new CSV file
file_path = '/mnt/data/moded.csv'

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

    # Initialize lists to store the embeddings
    text_embeddings_list = []
    title_embeddings_list = []

    # Iterate over each row in the DataFrame
    for index, row in data.iterrows():
        # Get text and titles
        text = row['text']

        titles = " ".join(ast.literal_eval(row['titles']))  # Convert titles list to a single string

        # Generate the embedding for text if it's not empty
        if text.strip():
            text_embedding = get_bedrock_embeddings(text)
        else:
            text_embedding = []  # Or some default value
        text_embeddings_list.append(text_embedding)

        # Generate the embedding for titles if it's not empty
        if titles.strip():
            title_embedding = get_bedrock_embeddings(titles)
        else:
            title_embedding = []  # Or some default value
        title_embeddings_list.append(title_embedding)
        if (index + 1) % 500 == 0:
            logger.info(f"Processed {index + 1}/{len(data)} rows")

    # Add the embeddings to the DataFrame
    data['text_embedding'] = text_embeddings_list
    data['title_embedding'] = title_embeddings_list

    # Save the updated DataFrame to a new CSV file
    embeddings_file_path = '/mnt/data/moded_with_embeddings.csv'
    data.to_csv(embeddings_file_path, index=False)
    logger.info(f"moded_with_embeddings.csv created successfully.")
except Exception as e:
    logger.error(f"Error creating moded_with_embeddings: {e}")

### SANITY CHECKS
# Load the CSV file with embeddings
data_with_embeddings = pd.read_csv(embeddings_file_path)

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

    # Function to terminate process holding the lock
    def terminate_locking_process(table_name):
        get_pid_query = f"""
        SELECT pid
        FROM pg_locks l
        JOIN pg_class t ON l.relation = t.oid AND t.relkind = 'r'
        WHERE t.relname = '{table_name}';
        """
        cur.execute(get_pid_query)
        locking_process = cur.fetchone()
        if locking_process:
            pid = locking_process[0]
            terminate_query = f"SELECT pg_terminate_backend({pid});"
            cur.execute(terminate_query)
            connection.commit()
            print(f"Terminated process {pid} holding lock on {table_name}.")

    # Drop the table if it already exists
    drop_table_command = sql.SQL("DROP TABLE IF EXISTS phase_2_embeddings;")

    try:
        # Terminate the process holding the lock if any
        terminate_locking_process('phase_2_embeddings')

        # Drop the table if it exists
        cur.execute(drop_table_command)
        connection.commit()
        logger.info("Table dropped if it existed.")
    except psycopg2.Error as e:
        logger.error(f"Error dropping embeddings table: {e}")
        connection.rollback()

    ### CREATE EMBEDDINGS TABLE
    # Create table to store embeddings and metadata
    table_create_command = sql.SQL("""
    CREATE TABLE phase_2_embeddings (
                id bigserial primary key,
                doc_id text,
                url text,
                titles jsonb,
                text text,
                links jsonb,
                text_embedding vector({}),
                title_embedding vector({})
                );
                """).format(
        sql.Literal(VECTOR_DIMENSION),
        sql.Literal(VECTOR_DIMENSION)
    )

    try:
        # Create the new table
        cur.execute(table_create_command)
        connection.commit()
        logger.info("Table created!")
    except psycopg2.Error as e:
        logger.error(f"Error creating embeddings table: {e}")
        connection.rollback()

    ### GRANT PRIVILEGES TO db_user_secret['username']
    try:
        db_user_secret = param_manager.get_secret(user_secret_name)
        grant_privileges_command = sql.SQL("""
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE phase_2_embeddings TO {};
        """).format(sql.Identifier(db_user_secret['username']))
        cur.execute(grant_privileges_command)
        connection.commit()
        logger.info(f"Privileges granted!")
    except psycopg2.Error as e:
        logger.error(f"Error granting privileges: {e}")
        connection.rollback()

    ### POPULATE EMBEDDINGS TABLE
    # Load the CSV file with embeddings
    logger.info("Loading the CSV file...")
    data_with_embeddings = pd.read_csv(embeddings_file_path)

    # Check the type of the embedding columns
    text_embedding_type = type(first_row['text_embedding'])
    title_embedding_type = type(first_row['title_embedding'])
    logger.info(f"The type of the text_embedding column is: {text_embedding_type}")
    logger.info(f"The type of the title_embedding column is: {title_embedding_type}")

    # Function to convert string representation of list to numpy array
    def parse_embedding(embedding_str):
        return np.array(ast.literal_eval(embedding_str))

    # Apply the function to the text_embedding column if it's a string
    if isinstance(first_row['text_embedding'], str):
        logger.info("Converting the text_embedding column to numpy arrays...")
        data_with_embeddings['text_embedding'] = data_with_embeddings['text_embedding'].apply(parse_embedding)
        logger.info("Conversion complete.")
    else:
        logger.info("Text Embeddings are not strings, they are a list of floats")

    # Apply the function to the title_embedding column if it's a string
    if isinstance(first_row['title_embedding'], str):
        logger.info("Converting the title_embedding column to numpy arrays...")
        data_with_embeddings['title_embedding'] = data_with_embeddings['title_embedding'].apply(parse_embedding)
        logger.info("Conversion complete.")
    else:
        logger.info("Title Embeddings are not strings, they are a list of floats")

    # Verify the conversion
    first_row_converted = data_with_embeddings.iloc[0]
    logger.info(f"The first row after converting the 'text_embedding' and 'title_embedding' columns:\n{first_row_converted.to_dict()}")

    # Convert 'titles' and 'links' columns to JSON format
    data_with_embeddings['titles'] = data_with_embeddings['titles'].apply(json.dumps)
    data_with_embeddings['links'] = data_with_embeddings['links'].apply(json.dumps)

    # Function to ensure embeddings are lists, not empty, and pad with zeros to the correct dimensionality
    def ensure_list_and_pad_embedding(embedding, expected_dim=VECTOR_DIMENSION):
        if isinstance(embedding, np.ndarray):
            embedding = embedding.tolist()
        if not embedding:
            embedding = [0] * expected_dim  # Replace empty embeddings with a list of zeros of the correct dimensionality
        elif len(embedding) < expected_dim:
            embedding.extend([0] * (expected_dim - len(embedding)))  # Pad with zeros
        return embedding

    data_with_embeddings['text_embedding'] = data_with_embeddings['text_embedding'].apply(ensure_list_and_pad_embedding)
    data_with_embeddings['title_embedding'] = data_with_embeddings['title_embedding'].apply(ensure_list_and_pad_embedding)

    # Prepare the list of tuples for insertion in batches
    batch_size = 500  # Set a smaller batch size
    total_rows = len(data_with_embeddings)
    num_batches = (total_rows // batch_size) + 1

    logger.info(f"Total rows: {total_rows}, Batch size: {batch_size}, Number of batches: {num_batches}")

    # Use execute_values to perform batch insertion
    for batch in range(num_batches):
        start_idx = batch * batch_size
        end_idx = min(start_idx + batch_size, total_rows)
        batch_data = data_with_embeddings.iloc[start_idx:end_idx]

        data_list = [(row['doc_id'],
                    row['url'],
                    row['titles'],
                    row['text'],
                    row['links'],
                    row['text_embedding'],
                    row['title_embedding']) for index, row in batch_data.iterrows()]

        logger.info(f"Inserting batch {batch + 1}/{num_batches}...")

        try:
            execute_values(cur, "INSERT INTO phase_2_embeddings (doc_id, url, titles, text, links, text_embedding, title_embedding) VALUES %s", data_list)
        except Exception as e:
            logger.error(f"Error when populating table in batch {batch + 1}: {e}")
            connection.rollback()
        
        # Commit after each batch
        connection.commit()
        logger.info(f"Batch {batch + 1}/{num_batches} insertion complete!")
    
    logger.info("All batches inserted successfully!")

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
                cur.execute(f'CREATE INDEX ON phase_2_embeddings USING hnsw (text_embedding {distance_measure})')
                cur.execute(f'CREATE INDEX ON phase_2_embeddings USING hnsw (title_embedding {distance_measure})')
            elif index_method == 'ivfflat':
                num_lists = num_records / 1000
                if num_lists < 10:
                    num_lists = 10
                if num_records > 1000000:
                    num_lists = math.sqrt(num_records)

                cur.execute(f'CREATE INDEX ON phase_2_embeddings USING ivfflat (text_embedding {distance_measure}) WITH (lists = {num_lists});')
                cur.execute(f'CREATE INDEX ON phase_2_embeddings USING ivfflat (title_embedding {distance_measure}) WITH (lists = {num_lists});')

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
    get_index_details('phase_2_embeddings_text_embedding_idx')
    get_index_details('phase_2_embeddings_title_embedding_idx')
finally:
    cur.close()
    connection.close()

### UPLOAD TO S3 & CLEANUP

# Upload documents to s3
upload_directory_to_s3(docs_dir)
upload_file_to_s3('/mnt/data/moded.csv', 'embeddings-amazon-titan/moded.csv')
upload_file_to_s3('/mnt/data/moded_with_embeddings.csv', 'embeddings-amazon-titan/moded_with_embeddings.csv')

# Delete directories from disk
shutil.rmtree('/mnt/data/' + docs_dir)
# Remove CSV files
try:
    os.remove('/mnt/data/moded.csv')
    os.remove('/mnt/data/moded_with_embeddings.csv')
    logger.info("Successfully removed 'moded.csv' and 'moded_with_embeddings.csv' from disk.")
except OSError as e:
    logger.error(f"Error removing file: {e}")