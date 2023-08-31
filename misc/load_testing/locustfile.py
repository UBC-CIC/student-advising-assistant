from locust import HttpUser, task, between

class QuickstartUser(HttpUser):
    host = "http://student-advising-demo.ca-central-1.elasticbeanstalk.com/"  
    wait_time = between(1, 5)

    @task
    def view_index(self):
        self.client.get("")

    @task
    def get_answer_verify(self):
        self.client.post("answer", catch_response=False, data={
            "faculty":"The Faculty of Science", 
            "program":"Bachelor of Science",
            "specialization" : "",
            "year" : "",
            "topic" : "",
            "question" : "how do I aply to honours cs"})