
# Deployment walkthrough

## Table of Contents
- [Deployment walkthrough](#deployment-walkthrough)
  - [Table of Contents](#table-of-contents)
  - [Requirements](#requirements)
  - [Pre-Deployment](#pre-deployment)
    - [Customize Static Website Content](#customize-static-website-content)
    - [Set Up Pinecone Index **(Optional)**](#set-up-pinecone-index-optional)
  - [Deployment](#deployment)
    - [Step 1: Clone The Repository](#step-1-clone-the-repository)
    - [Step 2: CDK Deployment](#step-2-cdk-deployment)
      - [**Extra: Taking down the deployed stacks**](#extra-taking-down-the-deployed-stacks)
    - [Step 3: Uploading the configuration file](#step-3-uploading-the-configuration-file)

## Requirements

Before you deploy, you must have the following installed on your device:

- [git](https://git-scm.com/downloads)
- [git lfs](https://git-lfs.com/)
- [AWS Account](https://aws.amazon.com/account/)
- [GitHub Account](https://github.com/)
- [AWS CLI](https://aws.amazon.com/cli/)
- [AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/cli.html)
- [Docker Desktop](https://docs.docker.com/desktop/) (make sure to install the correct version for you machine's operating system).

If you are on a Windows device, it is recommended to install the [Windows Subsystem For Linux](https://docs.microsoft.com/en-us/windows/wsl/install), which lets you run a Linux terminal on your Windows computer natively. Some of the steps will require its use. [Windows Terminal](https://apps.microsoft.com/store/detail/windows-terminal/9N0DX20HK701) is also recommended for using WSL.

## Pre-Deployment

### Customize Static Website Content
![Static Files Homepage](./images/static_files_1.png)

Before deployment, customize the static content of the website.
The files under `/flask_app/static` are customizable:
1. `app_title.txt`: Defines the app title to be displayed on the web app
2. `about.md`: Markdown content is displayed in the 'About' dropdown on the web app homepage
3. `query_suggestions.md`: Markdown content is displayed in the 'Instructions and Suggestions' dropdown on the web app homepage
4. `defaults.json`: Specifies the defaults for the question form - if desired, the faculty and program fields can be autopopulated with a particular value. File has the following format:
```
{
    "faculty": "<enter the default value>",
    "program": "<enter the default value>
}
```
5. `backup_response.md`: Markdown content is displayed if the system finds no response for the question, or if the user indicates that the response was not helpful. Should contain links to other advising resources.
6. `data_source_annotations`: Contains annotations to offer for each of the data sources. When a reference is taken from a website, the corresponding annotation will be displayed with it.
- File format:
```
{
    "<enter root website url>": {
        "name": "<enter display name for the website>",
        "annotation": "<enter the annotation for the website>"
    },
    ... 
    <insert as many entries as needed>
}
```
- The root url should be a section of the url that is present for all pages in the intended data source, eg "university.website.ca"
- Different subsections of the same site could have different annotations by specifying a subdirectory in the root url, eg "university.website.ca/undergrad" and "university.website.ca/graduate"
- The website urls should align with the websites chosen for download, see [User Guide](UserGuide#data-pipeline) for more details

### Set Up Pinecone Index **(Optional)**
This step is only necessary if you choose to use the Pinecone retriever instead of PGVector.

1. Sign up for a [Pinecone.io](https://www.pinecone.io/) account
2. From the Pinecone console, click 'API Keys', and either create a new key or take note of the environment and value of the 'default' key
![Pinecone API Key](./images/pinecone_api_key.png)
3. Run the following command, replacing the values between '<>'

```bash
aws secretsmanager create-secret \
    --name student-advising/retriever/PINECONE \
    --description "API key and region for Pinecone.io account" \
    --secret-string "{\"PINECONE-KEY\":\"<api key>\",\"PINECONE-REGION\":\"<region>\"}" \
    --profile <profile-name>
```
- You should replace `<api key>` with the Pinecone api key value from step 2, and `<region>` with the environment from step 2
- For example, with the api key `1000`, region `us`, and profile name `profile`:
```bash
aws secretsmanager create-secret \
    --name student-advising/retriever/PINECONE \
    --description "API key and region for Pinecone.io account" \
    --secret-string "{\"PINECONE-KEY\":\"1000\",\"PINECONE-REGION\":\"us\"}" \
    --profile profile
``` 

## Deployment 

### Step 1: Clone The Repository

First, clone the GitHub repository onto your machine. To do this:

1. Create a folder on your computer to contain the project code.
2. For an Apple computer, open Terminal. If on a Windows machine, open Command Prompt or Windows Terminal. Enter into the folder you made using the command `cd path/to/folder`. To find the path to a folder on a Mac, right click on the folder and press `Get Info`, then select the whole text found under `Where:` and copy with ⌘C. On Windows (not WSL), enter into the folder on File Explorer and click on the path box (located to the left of the search bar), then copy the whole text that shows up.
3. Clone the github repository by entering the following:

```bash
git clone https://github.com/UBC-CIC/student-advising-assistant
```

The code should now be in the folder you created. Navigate into the root folder containing the entire codebase by running the command:

```bash
cd student-advising-assistant
``` 

### Step 2: CDK Deployment

It's time to set up everything that goes on behind the scenes! For more information on how the backend works, feel free to refer to the Architecture Deep Dive, but an understanding of the backend is not necessary for deployment.

**IMPORTANT**: Before moving forward with the deployment, please make sure that your **Docker Desktop** software is running (and the Docker Daemon is running).

Note this CDK deployment was tested in `us-west-2` region only.

**Initialize the CDK stacks**
(required only if you have not deployed any resources with CDK in this region before)

```bash
cdk synth --profile your-profile-name
cdk bootstrap aws://YOUR_AWS_ACCOUNT_ID/YOUR_ACCOUNT_REGION --profile your-profile-name
```

**Deploy the CDK stacks**

You may  run the following command to deploy the stacks all at once. Please replace `<profile-name>` with the appropriate AWS profile used earlier. 

If using pgvector retriever, replace <retriever-type> with pgvector, or omit the retrieverType parameter. If using pinecone retriever, replace <retriever-type> with pinecone.

If you would prefer not to deploy the LLM (eg. for cost reasons), replace `llmMode=true` with `llmMode=false`. The system will not deploy a LLM endpoint, and it will return references from the information sources only, without generated responses.

```bash
cdk deploy --all \
    --parameters InferenceStack:retrieverType=<retriever-type> \
    --parameters InferenceStack:llmMode=true \
    --profile <profile-name>
```

#### **Extra: Taking down the deployed stacks**

To take down the deployed stack for a fresh redeployment in the future, navigate to AWS Cloudformation, click on the stack(s) and hit Delete. Please wait for the stacks in each step to be properly deleted before deleting the stack downstream. The deletion order is as followed:

1. HostingStack
2. InferenceStack
3. student-advising-DatabaseStack
4. student-advising-VpcStack

### Step 3: Uploading the configuration file

To complete the deployment, you will need to upload a configuration file specifying the websites to scrape for information. Continue with the [User Guide](./UserGuide.md#updating-the-configuration-file) for this step.