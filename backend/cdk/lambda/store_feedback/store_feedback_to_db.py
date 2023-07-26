import os
import json
import boto3
import psycopg2

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
    
    # the connection object that were cached outside of the lambda_ha
    global connection
    # print(connection)
    if connection.closed:
        connection = createConnection()
    
    cursor = connection.cursor()
    
    sql = """
        INSERT INTO feedback (helpful_response, question, context, retrieved_doc_ids, response, most_relevant_doc, comment) 
        VALUES (%s, %s, %s, %s, %s, %s,%s);
    """
    
    data = []
    for key in event.keys():

        if key == "feedback-hidden-helpful":
            data.append(True if event[key] == "yes" else False)
        elif key == "feedback-reference-select":
            data.append(int(event[key]))
        else:
            data.append(event[key])
            
    print(data)
    
    cursor.execute(sql, tuple(data))
    
    sql = """
        SELECT * FROM feedback;
    """
    res = cursor.fetchall()
    print(res)
    
    cursor.close()
    
    return {
        "statusCode": 200,
        "msg": "Successfuly connected to db",
        "body": json.dumps(res),
        # "orig_event": event
    }
