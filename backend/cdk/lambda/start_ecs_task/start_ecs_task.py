import json
import boto3
from botocore.exceptions import NoCredentialsError, BotoCoreError, ClientError
import os

def start_ecs_task(cluster_name, task_definition, count=1):
    try:
        ecs = boto3.client('ecs')
        response = ecs.run_task(
            cluster=cluster_name,
            taskDefinition=task_definition,
            count=count,
            launchType="FARGATE",
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': [
                        os.environ["PRIV_SUBNET"],
                    ],
                    'securityGroups': [
                        os.environ["SGR"],
                    ],
                    'assignPublicIp': 'DISABLED'
                }
            }
        )
        tasks = response.get('tasks', [])
        if tasks:
            print(f"{len(tasks)} task(s) started successfully.")
        else:
            print("No tasks were started.")
    except (NoCredentialsError, BotoCoreError, ClientError) as e:
        print("Error occurred while starting ECS task:", str(e))


def lambda_handler(event, context):
    # Example usage
    cluster_name = os.environ["ECS_CLUSTER_NAME"]
    task_definition = os.environ["ECS_TASK_ARN"]
    count = 1  # Number of task instances to start (optional, defaults to 1)
    start_ecs_task(cluster_name, task_definition, count)

