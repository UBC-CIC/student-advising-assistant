from langchain_aws import BedrockLLM

# Initialize the Bedrock LLM
llm = BedrockLLM(
    model_id="meta.llama3-8b-instruct-v1:0"
)

# Invoke the llm
response = llm.invoke("What is RAG in AI?")
print(response)