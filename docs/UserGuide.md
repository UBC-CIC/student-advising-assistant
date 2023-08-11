# User Guide

**Before Continuing with this User Guide, please make sure you have deployed the stacks.**

- [Deployment Guides](./DeploymentGuide.md)

Once you have deployed the solution, the following user guide will help you navigate the functions available.

| Index                                        | Description                                           |
| :------------------------------------------  | :---------------------------------------------------- |
| [Data Pipeline](#data-pipeline)              | Rerun the pipeline to update information sources      |

## Data Pipeline

### Updating the Configuration File
The data pipeline needs a configuration file to specify which websites to pull information from.
1. In the [S3 Console](https://s3.console.aws.amazon.com/s3/home?region=us-west-2#), navigate to the bucket named `student-advising-s3bucket`, then to the `document_scraping` folder
![AWS S3 bucket](./images/s3_bucket_config.png)
2. Download the file `dump_config.json5`, which should already exist in the folder
3. Open `dump_config.json5` in any text editor
4. The file contains an example dump config entry, with comments explaining all fields. To add a new site to the dump, copy the example dump config and fill in the required fields. For a minimal configuration, use the following template:
- ```
    <enter config display name>: {
        base_url: "<enter root url for the site>",
        main_content_attrs: {
            <enter attribute 1 name>: "<enter attribute 1 value>",
            <enter attribute 2 name>: "<enter attribute 2 value>",
            //...
        }
    }
    ```
    - Enter a display name and the root url of the website to scrape in the fields specified
    - You will also need to specify attribute(s) of the html tag that wraps the main content of the webpage, so that the scraping will ignore extraneous information such as website headers, navbars, etc.
    - Inspect a page of the website using a tool such as [Chrome DevTools](https://developer.chrome.com/docs/devtools/open/), and find an identifying attribute (eg. id) of the outermost tag that contains only the main page content
    - Specify the identifying attribute(s) in the main_content_attrs. For example: `main_content_attrs: { id: "primary-content" }`
- Specifying additional fields of the dump_config can improve the preprocessing, but is best done by a developer. Details about the fields are included in the example config in `dump_config.json5`
5. Save the `dump_config.json5` file and in the AWS Console, click 'upload' and drag and drop the updated file.
6. The data pipeline will be triggered, and it may take several hours to complete. Once complete, the processed documents will be available in the web app, and the web app will display a banner with the date that the pipeline was run.

### Automatic Reruns
The data pipeline is scheduled to automatically rerun on the first Sunday of every September, January, and May. 

### Manual Reruns
If the data pipeline needs to be rerun outside of the scheduled times, it can be triggered by reuploading the `dump_config.json5` as described above, or it can be triggered by the Lambda function `student-advising-start-ecs-task`:
1. Run the command below, replacing `<profile-name>` with your AWS profile name.
```bash
aws lambda invoke \
    --function-name student-advising-start-ecs-task \
    --profile <profile-name> 
    student-advising-start-ecs-task-log.txt
```
2. The rerun will take several hours to complete. Once it is complete, the web app will display the time that the pipeline finished.