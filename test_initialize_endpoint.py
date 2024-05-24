import sys
import os
import requests

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.append(project_root)

aws_helpers_path = os.path.abspath(os.path.join(project_root, 'aws_helpers'))
sys.path.append(aws_helpers_path)

print("Current Python Path:")
for p in sys.path:
    print(p)

print("\nContents of the project directory:")
print(os.listdir(project_root))

print("\nContents of the aws_helpers directory:")
print(os.listdir(aws_helpers_path))

try:
    from aws_helpers.param_manager import get_param_manager
    print("Successfully imported get_param_manager from aws_helpers.param_manager")
except ImportError as e:
    print("Failed to import get_param_manager from aws_helpers.param_manager")
    print(e)

param_manager = get_param_manager()

app_url = param_manager.get_parameter('BEANSTALK_URL')

initialize_url = 'http://' + app_url + '/initialize'
print(f"Formatted URL: {initialize_url}")

try:
    response = requests.get(url=initialize_url, timeout=300)
    if response.status_code == 200:
        print("Successfully initialized the Flask app")
    else:
        print(f"Received status code {response.status_code}")
        print(f"Response text: {response.text}")
except Exception as e:
    print(f"Error: {str(e)}")
