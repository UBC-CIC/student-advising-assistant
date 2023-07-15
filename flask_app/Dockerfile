FROM --platform=linux/amd64 public.ecr.aws/docker/library/python:3

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 5000

# run the flask app entry point application.py
CMD [ "python3", "application.py" ]