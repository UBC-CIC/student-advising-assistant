# Student Advising Assistant

This is a prototype question answering system for the purpose of student advising at higher education institutions. It performs [retrieval augmented generation](https://docs.aws.amazon.com/sagemaker/latest/dg/jumpstart-foundation-models-customize-rag.html) using university websites as information sources. 
For more information visit the [CIC Website](https://cic.ubc.ca/).

| Index                                               | Description                                             |
| :-------------------------------------------------- | :------------------------------------------------------ |
| [High Level Architecture](#high-level-architecture) | High level overview illustrating component interactions |
| [Deployment](#deployment-guide)                     | How to deploy the project                               |
| [User Guide](#user-guide)                           | The working solution                                    |
| [Developer Guide](#user-guide)                      | Information for further developers                      |
| [Changelog](#changelog)                             | Any changes post publish                                |
| [Credits](#credits)                                 | Meet the team behind the solution                       |
| [License](#license)                                 | License details                                         |

## High Level Architecture

The following architecture diagram illustrates the various AWS components utilized to deliver the solution. For an in-depth explanation of the frontend and backend stacks, refer to the [Architecture Design](docs/ArchitectureDesign.md).

![Alt text](docs/images/ArchiectureDiagram-EC2-tgi-inference.drawio.png)

## Deployment Guide

To deploy this solution, please follow the steps laid out in the [Deployment Guide](docs/DeploymentGuide.md)

## User Guide

For instructions on how to navigate the web app interface, refer to the [Web App User Guide](docs/UserGuide.md).

## Developer Guide

For instructions on how to develop the application, refer to the [Developer Guide](docs/DeveloperGuide.md).

## Directories

```
├───aws_helpers
├───backend
│   └───cdk
│       ├───bin
│       ├───lambda
│       │   ├───start_ecs
│       │   ├───store_feedback
│       │   └───trigger_lambda
│       ├───layers
│       ├───lib
│       └───test
├───document_scraping
├───embeddings
├───flask_app
│   ├───documents
│   ├───embeddings
│   ├───filters
│   ├───llms
│   ├───prompts
│   ├───retrievers
│   ├───static
│   └───templates
└───misc
```

1. `/aws_helpers`: Contains utilities classes / functions for connecting to AWS Services, used across the other portions of the app
2. `/backend/cdk`: Contains the deployment code for the app's AWS infrastructure
    - `/lambda`: Contains the scripts for all lambda functions
    - `/lib`: Contains the deployment code for all 4 stacks of the infrastructre
3. `/document_scraping`: Contains the scripts that run to scrape text from the information source websites
4. `/embeddings`: Contains the scripts that convert the scraped texts to embeddings, then uploads them to the vectorstore
5. `/flask_app`: Contains the inference and user interface code for the prototype question answering system
    - `/documents`: Functions relating to document loading
    - `/embeddings`: Classes relating to embeddings
    - `/filters`: Classes relating to document filters
    - `/llms`: Classes relating to LLMs, adapters to connect to LLMs, and helpers to load LLMs
    - `/prompts`: Prompt template definitions
    - `/retrievers`: Retriever classes for PGVector and Pinecone
    - `/static`: Static web content as .md or .json
    - `/templates`: HTML files with Jinja2 templates for the web app's pages
6. `/misc`: Contains various other useful scripts, contents described in the [Developer Guide](./docs/DeveloperGuide.md)

## Changelog
N/A

## Credits

This application was architected and developed by Arya Stevinson and Tien Nguyen, with project assistance by Victoria Li. A special thanks to the UBC Cloud Innovation Centre Technical and Project Management teams for their guidance and support.

## License

This project is distributed under the [MIT License](LICENSE).

Licenses of libraries and tools used by the system are listed below:

[PostgreSQL license](https://www.postgresql.org/about/licence/)
- For PostgreSQL and pgvector
- "a liberal Open Source license, similar to the BSD or MIT licenses."

[BSD 3-clause](https://opensource.org/license/bsd-3-clause/)
- For Networkx, Flask, and Pytorch

[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- For Transformers, Sentence-transformers, and Fschat

[GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.en.html)
- For wget
	
[GNU Lesser General Public License](https://www.gnu.org/licenses/lgpl-3.0.en.html)
- For Psycopg2-binary

[MIT License](LICENSE)
- For Spacy and Dictdiffer

[HFOIL 1.0](https://github.com/huggingface/text-generation-inference/blob/bde25e62b33b05113519e5dbf75abda06a03328e/LICENSE)
- For Huggingface text-generation-inference, used by the DLC container for the sagemaker inference endpoint
- "HFOIL is not a true open source license because we added a restriction: to sell a hosted or managed service built on top of TGI, we now require a separate agreement."

[LLaMa 2 Community License Agreement](https://github.com/facebookresearch/llama/blob/main/LICENSE)
- For Vicuna 1.5, tuned off Llama 2
- Not true open source due to some restrictions regarding inappropriate use
- "Your use of the Llama Materials must comply with applicable laws and regulations"
- Also includes restrictions on solutions that have "700 million monthly active users"
