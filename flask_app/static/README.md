# Response Configuration

This folder contains configuration files to customize the system's interface and responses. The files and their functions are listed below:
- `about.md`: This markdown file contains some general information about the system to display to users.
- `query_suggestions.md`: This markdown file describes a list of suggested techniques for users to employ when entering questions to improve the model's performance.
- `backup_response.md`: This is a markdown file with the fallback response that the system will return to if it does not believe it can answer a question. It should provide alternate resources where a user might find advice.
- `data_source_annotations.json`: This contains a list of data sources and the annotation that should be provided when responses are sourced from them. This could include disclaimers regarding the reliability of the data. Entries should be in the following format:
    - ```
        {
            ...
            {
                "<root url of the site>": {
                    "name": "<display name of the site>",
                    "annotation": "<annotation to provide>"
                }
            },
            ...
        }
        ```
    - The root url should be a section of the url that is present for all pages in the intended data source, eg "vancouver.calendar.ubc.ca"
    - Different subsections of the same site could have different annotations by specifying a subdirectory, eg "science.ubc.ca/students" and "science.ubc.ca/grad"