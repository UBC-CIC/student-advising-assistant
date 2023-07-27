import os
import json
import boto3
import psycopg2

DB_SECRET_NAME = os.environ["DB_SECRET_NAME"]
LOGGING_KEY = 'logging' 
# ^ name of the key in the event that specifies whether to
# store the feedback to a logging table (otherwise feedback table)
PAYLOAD_KEY = 'payload'
# ^ name of the key in the event that includes the json
# payload for inserting into the table

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
    
    # the connection object that were cached outside of the lambda_ha
    global connection
    # print(connection)
    if connection.closed:
        connection = createConnection()
    
    cursor = connection.cursor()
    
    sql = None
    if event[LOGGING_KEY]:
        sql = """
            INSERT INTO logging (question, context, retrieved_doc_ids, response) 
            VALUES (%s, %s, %s, %s);
        """
    else:
        sql = """
            INSERT INTO feedback (helpful_response, question, context, retrieved_doc_ids, response, most_relevant_doc, comment) 
            VALUES (%s, %s, %s, %s, %s, %s,%s);
        """
    
    data = []
    for key, val in json.loads(event[PAYLOAD_KEY]).items():
        if key == "feedback-hidden-helpful":
            data.append(True if val == "yes" else False)
        elif key == "feedback-reference-select":
            data.append(int(val))
        else:
            data.append(val)
    
    print(data)

    try:
        cursor.execute(sql, tuple(data))
        connection.commit()
        return {
            "statusCode": 200,
            "msg": "Successfuly stored feedback"
        }
    except Exception as e:
        return {
            "statusCode": 400,
            "msg": "Failed to store feedback",
            "body": str(e)
        }
    finally:
        cursor.close()
