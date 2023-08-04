Notes to include:

Choosing the retriever:
- RDS with pgvector:
    - The CDK deploys with the pgvector retriever by default, and no additional steps are required
- Pinecone:
    1. Create a Pinecone.io account and a starter index with the embedding dimension `2304` and metric `dotproduct` 
        - **-> More details <-**
    2. Obtain a [Pinecone API Key](https://docs.pinecone.io/docs/quickstart#:~:text=To%20find%20your%20API%20key,API%20key%20and%20your%20environment.&text=If%20you%20don't%20receive,your%20API%20key%20is%20valid.) from the Pinecone console, and take note of the region and API Key
    3. In AWS Console navigate to Secret Manager, ensure the region is correct, and create a new secret ![AWS Secret Manager new secret](./images/secret_manager_new.png)
    4. Fill in the fields for the Pinecone secret
    ![AWS Secret Manager Pinecone keys](./images/secret_manager_pinecone_keys.png)
        - Select secret type: 'Other type of secret'
        - Enter the Key/Value pairs:
            - Key: PINECONE_KEY, Value: Insert the API key from step 2
            - Key: PINECONE_REGION, Value: Insert the region from step 2
    5. Click 'next', then enter secret name = "student-advising/retriever/PINECONE"
     ![AWS Secret Manager Pinecone name](./images/secret_manager_pinecone_name.png)
    6. Click 'next' twice more, then 'store'
    6. When deploying the CDK, include the parameter: `--parameters InferenceStack:retriever=pinecone`