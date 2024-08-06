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

CREATE TABLE "phase_2_embeddings" (
  "id" BIGSERIAL PRIMARY KEY,
  "doc_id" TEXT,
  "url" TEXT,
  "titles" JSONB,
  "text" TEXT,
  "links" JSONB,
  "text_embedding" VECTOR(1024),
  "title_embedding" VECTOR(1024)
);