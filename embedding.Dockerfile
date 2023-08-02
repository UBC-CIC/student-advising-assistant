# THIS DOCKERFILE IS USED TO BUILD THE DOCUMENT EMBEDDING CONTAINER
FROM --platform=linux/amd64 pytorch/pytorch:latest

WORKDIR /usr/src/app

COPY embeddings/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY aws_helpers/ ./aws_helpers/
COPY embeddings/ ./embeddings/

WORKDIR /usr/src/app/embeddings

CMD [ "python", "entry_point.py" ]