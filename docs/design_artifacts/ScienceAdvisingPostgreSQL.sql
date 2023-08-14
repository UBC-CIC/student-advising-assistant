CREATE TABLE "feedback" (
  "id" BIGSERIAL PRIMARY KEY,
  "helpful_response" BOOLEAN NOT NULL,
  "question" VARCHAR NOT NULL,
  "context" VARCHAR,
  "retrieved_doc_ids" VARCHAR,
  "response" VARCHAR,
  "most_relevant_doc" INT,
  "comment" VARCHAR
);

CREATE TABLE "logging" (
  "id" BIGSERIAL PRIMARY KEY,
  "question" VARCHAR NOT NULL,
  "context" VARCHAR,
  "retrieved_doc_ids" VARCHAR,
  "response" VARCHAR
);

CREATE TABLE "update_logs" (
  "id" BIGSERIAL PRIMARY KEY,
  "datetime" timestamptz
);
