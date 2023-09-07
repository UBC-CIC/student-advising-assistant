import os
import json
import boto3
import psycopg2
from datetime import datetime
from io import StringIO
import csv

"""
This is a lambda function to fetch all logging and feedback entries from the DB
and store to CSV files in the default S3 bucket.
"""

DB_SECRET_NAME = os.environ["DB_SECRET_NAME"]
S3_BUCKET_PARAM_NAME = os.environ["BUCKET_PARAM_NAME"]
# ^ name of the key in the event that specifies the name of the S3 bucket

def getDbSecret():
    # secretsmanager client to get db credentials
    sm_client = boto3.client("secretsmanager")
    response = sm_client.get_secret_value(
        SecretId=DB_SECRET_NAME)["SecretString"]
    secret = json.loads(response)
    return secret

def getBucketName():
    # ssm parameters client to get the default bucket name
    ssm_client = boto3.client('ssm')
    response = ssm_client.get_parameter(Name=S3_BUCKET_PARAM_NAME)
    secret = response["Parameter"]["Value"]
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
s3 = boto3.resource('s3')
bucketName = getBucketName()

def lambda_handler(event, context):
    
    # the connection object that were cached outside of the lambda_handler
    global connection
    if connection.closed:
        connection = createConnection()
    
    logging_sql = "select * from logging"
    feedback_sql = "select * from feedback"
    datestring = datetime.now().strftime("%d-%m-%Y-%H-%M-%S")
    
    # Convert logging result to csv string
    cursor = connection.cursor()
    cursor.execute(logging_sql)
    logging_result = cursor.fetchall()
    logging_str = StringIO()
    writer = csv.writer(logging_str)
    writer.writerows(logging_result)
    cursor.close()
    print("Got logging results")
    
    # Convert feedback result to csv string
    cursor = connection.cursor()
    cursor.execute(feedback_sql)
    feedback_result = cursor.fetchall()
    feedback_str = StringIO()
    writer = csv.writer(feedback_str)
    writer.writerows(feedback_result)
    cursor.close()
    print("Got feedback results")

    try:
        s3.Object(bucketName, f'logs/question-log-{datestring}.csv').put(Body=logging_str.getvalue())
        s3.Object(bucketName, f'logs/feedback-log-{datestring}.csv').put(Body=feedback_str.getvalue())
        return {
            "statusCode": 200,
            "msg": f"Successfully stored feedback and logging files to {bucketName}/logs"
        }
    except Exception as e:
        return {
            "statusCode": 400,
            "msg": "Failed to fetch feedback",
            "body": str(e)
        }
    finally:
        cursor.close()
