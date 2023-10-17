# THIS DOCKERFILE IS USED TO BUILD THE FLASK APP
# FROM --platform=linux/amd64 public.ecr.aws/docker/library/python:3
FROM --platform=linux/amd64 python:3.10-slim

# Sets the working directory inside the container to /usr/src/app
WORKDIR /usr/src/app

# installing dependencies first before copying the app python codes and files
COPY flask_app/requirements.txt ./
RUN pip install --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt

# Copies the contents of the aws_helpers directory from the host machine into a aws_helpers/ directory 
# under the container's working directory (/usr/src/app)
COPY aws_helpers/ ./aws_helpers/
COPY flask_app/ ./flask_app/
WORKDIR /usr/src/app/flask_app

EXPOSE 8080

# run the flask app entry point application.py
# CMD [ "python3", "application.py" ]
# CMD ["gunicorn", "wsgi:application" , "--bind", "0.0.0.0:8080", "--timeout", "700", "--log-level=debug", "--workers=4", "--preload"]
 CMD ["gunicorn", "wsgi:application" , "--bind", "0.0.0.0:8080", "--timeout", "700", "--log-level=debug", "--workers=1", "--threads=4", "--preload"]