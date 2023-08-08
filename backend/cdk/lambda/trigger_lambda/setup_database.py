import os
import json
import boto3
import psycopg2

# At least psycopg2-binary==2.9.6 to work with PostgreSQL v15.2
# pip install --platform manylinux2014_x86_64 --implementation cp --only-binary=:all: psycopg2-binary==2.9.6
print(psycopg2.__version__)

DB_SECRET_NAME = os.environ["DB_SECRET_NAME"]


def getDbSecret():
    
    # secretsmanager client to get db credentials
    sm_client = boto3.client("secretsmanager")
    response = sm_client.get_secret_value(
        SecretId=DB_SECRET_NAME)["SecretString"]
    secret = json.loads(response)
    return secret

def createConnection():
    
    connection = psycopg2.connect(
        user=dbSecret["username"],
        password=dbSecret["password"],
        host=dbSecret["host"],
        dbname=dbSecret["dbname"],
        # sslmode="require"
    )
    return connection

dbSecret = getDbSecret()
connection = createConnection()

def lambda_handler(event, context):

    global connection
    print(connection)
    if connection.closed:
        connection = createConnection()
    
    cursor = connection.cursor()

    sql = """
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
        CREATE EXTENSION IF NOT EXISTS "vector";
        
        CREATE TABLE IF NOT EXISTS feedback (
            "id" BIGSERIAL PRIMARY KEY,
        	"helpful_response" BOOLEAN NOT NULL,
        	"question" VARCHAR NOT NULL,
        	"context" VARCHAR,
        	"retrieved_doc_ids" VARCHAR,
        	"response" VARCHAR,
        	"most_relevant_doc" INT,
        	"comment" VARCHAR
        );
        
        CREATE TABLE IF NOT EXISTS logging (
            "id" BIGSERIAL PRIMARY KEY,
        	"question" VARCHAR NOT NULL,
        	"context" VARCHAR,
        	"retrieved_doc_ids" VARCHAR,
        	"response" VARCHAR
        );
        
        CREATE TABLE IF NOT EXISTS update_logs (
            "id" BIGSERIAL PRIMARY KEY,
            "datetime" TIMESTAMPTZ
        );
        
        SET timezone = 0;
    """

    cursor.execute(sql)
    connection.commit()
    
    sql = """
        SELECT * FROM feedback;
    """
    
    cursor.execute(sql)
    print(cursor.fetchall())
    
    sql = """
        SELECT * FROM logging;
    """
    cursor.execute(sql)
    print(cursor.fetchall())
    
    sql = """
        SELECT * FROM update_logs;
    """
    cursor.execute(sql)
    print(cursor.fetchall())
    
    cursor.close()
    
    print("Trigger Function scripts finished execution successfully!")