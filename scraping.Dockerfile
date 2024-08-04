# THIS DOCKERFILE IS USED TO BUILD THE DOCUMENT SCRAPING CONTAINER
# FROM --platform=linux/amd64 public.ecr.aws/docker/library/python:3
# NOTE: python:slim do not have wget, thus either use full python:3 or download wget
FROM --platform=linux/amd64 python:3

WORKDIR /usr/src/app

COPY document_scraping/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm

COPY aws_helpers/ ./aws_helpers/
COPY document_scraping/ ./document_scraping/

# Change ownership of the working directory
RUN chown -R 1001:1001 /usr/src/app

# Switch to the user 1001:1001
USER 1001:1001

WORKDIR /usr/src/app/document_scraping

CMD [ "python", "data_pipeline.py" ]