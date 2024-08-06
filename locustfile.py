from locust import HttpUser, task, between
import sys
import os
# sys.path.append(os.path.join('..','..'))
from aws_helpers.param_manager import get_param_manager
for p in sys.path:
    print(p)

param_manager = get_param_manager()
HOST = param_manager.get_parameter("BEANSTALK_URL")
        
class QuickstartUser(HttpUser):
    host = f"http://{HOST}"  
    wait_time = between(1, 5)
        
    @task
    def view_index(self):
        self.client.get("/")

    @task
    def get_answer_verify(self):
        self.client.post("/answer", catch_response=False, data={
            "faculty":"The Faculty of Science", 
            "program":"Bachelor of Science",
            "specialization" : "",
            "year" : "",
            "topic" : "",
            "question" : "how do I aply to honours cs"})