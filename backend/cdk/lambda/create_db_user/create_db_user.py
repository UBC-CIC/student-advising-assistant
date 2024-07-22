import os
import json
import boto3
import psycopg2

DB_SECRET_NAME = os.environ["DB_SECRET_NAME"]
DB_USER_SECRET_NAME = os.environ["DB_USER_SECRET_NAME"]

def get_secret(secret_name):
    # secretsmanager client to get db credentials
    sm_client = boto3.client("secretsmanager")
    response = sm_client.get_secret_value(SecretId=secret_name)["SecretString"]
    secret = json.loads(response)
    return secret

def create_connection(db_secret):
    connection = psycopg2.connect(
        user=db_secret["username"],
        password=db_secret["password"],
        host=db_secret["host"],
        dbname=db_secret["dbname"],
        port=db_secret["port"]
    )
    return connection

def lambda_handler(event, context):
    db_secret = get_secret(DB_SECRET_NAME)
    db_user_secret = get_secret(DB_USER_SECRET_NAME)

    connection = create_connection(db_secret)
    connection.autocommit = True
    
    cursor = connection.cursor()

    # Create the less privileged user and grant privileges
    cursor.execute(f"CREATE USER {db_user_secret["username"]} WITH PASSWORD '{db_user_secret["password"]}'")
    cursor.execute(f"GRANT CONNECT ON DATABASE {db_secret["dbname"]} TO {db_user_secret["username"]}")
    cursor.execute(f"GRANT USAGE ON SCHEMA public TO {db_user_secret["username"]}")
    cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {db_user_secret["username"]}")

    cursor.close()
    connection.close()

    return {
        'statusCode': 200,
        'body': json.dumps('User created and privileges granted successfully')
    }