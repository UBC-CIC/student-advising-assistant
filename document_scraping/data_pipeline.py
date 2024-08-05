import platform
import os
import sys
import regex as re
import pyjson5 as json5
import json
import logging
from typing import Dict, List, Tuple, Any
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from site_pull_spider import SitePullSpider
from tools import write_file
import processing_functions
from website_dump_doc_extractor import DumpConfig, DocExtractor
from program_options_manager import find_program_options, apply_previous_difs
from dotenv import load_dotenv
load_dotenv()
sys.path.append('..')
from aws_helpers.s3_tools import upload_file_to_s3, download_single_file, download_s3_directory
from aws_helpers.logging import set_boto_log_levels

"""
Script to download the data sources using wget, and then split all pages into document extracts for 
downstream tasks.
"""

# /app/data is where ECS Tasks have writing privilegs due to EFS from Inference Stack

### CONSTANTS
# Input files
CONFIG_FILEPATH = '/app/data/dump_config.json5' # Filepath to the dump config file in current working dir

# Output files
BASE_DUMP_PATH = '/app/data/site_dumps' # Directory where site dump files are saved
LOCAL_DOCUMENTS_DIR = '/app/data/documents' # Local directory where processed extracts are saved
S3_DOCUMENTS_DIR = 'documents' # S3 directory where processed extracts are saved
REDIRECT_FILEPATH = os.path.join(BASE_DUMP_PATH, 'redirects.txt') # Filepath for dict of redirects
LOCAL_FACULTIES_UNPRUNED_FILEPATH = os.path.join(LOCAL_DOCUMENTS_DIR, "faculties_unpruned.json")
LOCAL_FACULTIES_FILEPATH = os.path.join(LOCAL_DOCUMENTS_DIR, "faculties.json")
S3_FACULTIES_UNPRUNED_FILEPATH = os.path.join(S3_DOCUMENTS_DIR, "faculties_unpruned.json")
S3_FACULTIES_FILEPATH = os.path.join(S3_DOCUMENTS_DIR, "faculties.json")

# Other constants
redirect_log_re = re.compile('http[^\n]*(\n[^\n]*){2}301 Moved Permanently\nLocation:\s[^\n\s]*')
# ^ regex matches entries in the wget logs that indicate a redirect
function_refs_file = processing_functions
# ^ file to search in for functions referenced by name in the config file

### Functions to load configuration from json file

def replace_function_refs(item: Any) -> Any:
    """
    Used to handle function references in the config json
    Recursively replace any function names in the dictionary values 
    with the corresponding function reference.
    Assumes all functions are in the function_refs_file
    - item: A dict or list to recursively search
    
    Returns the modified dictionary
    """
    # Keys where the value is a function name
    function_keys = ['function','metadata_extractor','parent_context_extractor']
    
    if type(item) == dict:
        for key, val in item.items():
            if key in function_keys:
                # val should be the name of a function
                # replace val with the associated function reference
                try:
                    item[key] = getattr(function_refs_file, val)
                except:
                    logging.error(f'Could not find the function {val} in {function_refs_file.__name__}')
                    raise ValueError(f'Invalid function name "{val}" specified in the config.')
            else: 
                item[key] = replace_function_refs(val)
        return item
    elif type(item) == list:
        return [replace_function_refs(entry) for entry in item]
    else:
        return item
    
def dict_to_class(dict: Dict, object: Any) -> Any:
    """
    For all attributes in the dict, sets the corresponding attribute of the object
    """
    for key,val in dict.items():
        setattr(object, key, val)
    
required_keys = ['base_url','main_content_attrs']
def validate_dump_config(name: str, dump_config_json: Dict):
    """
    Verifies that a config for a site dump from the dump config file
    contains all necessary values
    """
    if not all([key in dump_config_json for key in required_keys]):
        raise KeyError(f'Missing required key in the dump config for {name}. Required keys are {required_keys}.')

def load_general_config(general_config_json: Dict) -> DocExtractor:
    """
    Create a DocExtractor from the given config json
    """
    doc_extractor = DocExtractor()
    dict_to_class(general_config_json,doc_extractor)
    return doc_extractor

def load_dump_config(dump_config_json: Dict) -> DumpConfig:
    """
    Create a DumpConfig from the given config json
    """
    dump_config = DumpConfig()
    dict_to_class(dump_config_json,dump_config)
    
    # Create the dump path from the url
    base_url_elems = [segment for segment in dump_config.base_url.split('/') 
                        if len(segment) > 0 and not segment.startswith('http')]
    dump_config.dump_path = os.path.join(BASE_DUMP_PATH, *base_url_elems)
    
    return dump_config
        
def load_config(config_filepath: str) -> Tuple[DocExtractor, List[DumpConfig]]:
    """
    Loads the dump configurations from a json file
    """
    config_json = None
    with open(config_filepath,'r') as f:
        config_json = json5.load(f)
        
    doc_extractor = load_general_config(config_json['general_config'])
    dump_configs = []
    for name, dump_json in config_json['dump_configs'].items():
        if name == "example_config": 
            continue # Ignore the example dump config in the file
        validate_dump_config(name, dump_json)
        dump_json = replace_function_refs(dump_json)
        dump_config = load_dump_config(dump_json)
        dump_config.name = name
        dump_configs.append(dump_config)
    
    return doc_extractor, dump_configs
    
### Main function to pull websites and process
def pull_sites(dump_configs: List[DumpConfig], output_folder = './'):
    """
    Uses wget to pull the indicated websites, and processes
    the files into one combined csv of documents for use in the UBC Science 
    Advising question answering system.
    - dump_configs: Config objects for the sites to pull
    - output_folder: directory for the output site dumps
    """
    start_urls = [dump_config.base_url for dump_config in dump_configs]
    
    logging.info(f'Beginning pull from sites, this may take a long time')
    process = CrawlerProcess(get_project_settings())
    process.crawl(SitePullSpider, start_urls=start_urls, out_dir=output_folder)
    process.start()
    
    print(f'Completed pulling sites')

### Main
    
def write_json_file(filepath: str, item: Dict):
    # Helper function to write json to file
    def writer():
        with open(filepath,'w') as f: 
            json.dump(item,f,indent=4)
    
    write_file(writer)
    
def process_site_dumps(doc_extractor: DocExtractor, dump_configs: list[DumpConfig], 
                       redirect_map_path: str, out_path: str):
    
    # Read the redirect map if it exists
    if os.path.exists(redirect_map_path):
        with open(redirect_map_path, 'r') as f:
            redirect_map = json.loads(f.read())
            doc_extractor.link_redirects = redirect_map

    doc_extractor.parse_folder(dump_configs, out_path)

def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    set_boto_log_levels(logging.INFO) # Quiet boto logs, debug clogs up stdout
    
    # Download the config file from s3
    download_single_file(f"document_scraping/dump_config.json5", CONFIG_FILEPATH)

    # Pull and process sites
    doc_extractor, dump_configs = load_config(CONFIG_FILEPATH)
    pull_sites(dump_configs, output_folder = BASE_DUMP_PATH)
    process_site_dumps(doc_extractor, dump_configs, redirect_map_path=REDIRECT_FILEPATH, out_path=LOCAL_DOCUMENTS_DIR)

    # Upload the website_extracts.csv and website_graph.txt
    upload_file_to_s3(os.path.join(LOCAL_DOCUMENTS_DIR, "website_extracts.csv"), f"{S3_DOCUMENTS_DIR}/website_extracts.csv")
    upload_file_to_s3(os.path.join(LOCAL_DOCUMENTS_DIR, "website_graph.txt"), f"{S3_DOCUMENTS_DIR}/website_graph.txt")
    
    # Find the diff between the previous iteration of faculties.json, if the files exist
    download_s3_directory(S3_DOCUMENTS_DIR, ecs_task=True)
    new_unpruned_faculties = find_program_options(os.path.join(LOCAL_DOCUMENTS_DIR, "website_extracts.csv"))
    new_pruned_faculties = apply_previous_difs(new_unpruned_faculties, LOCAL_FACULTIES_UNPRUNED_FILEPATH, LOCAL_FACULTIES_FILEPATH)
    
    # Upload faculties files
    write_json_file(LOCAL_FACULTIES_UNPRUNED_FILEPATH, new_unpruned_faculties)
    write_json_file(LOCAL_FACULTIES_FILEPATH, new_pruned_faculties)
    upload_file_to_s3(LOCAL_FACULTIES_UNPRUNED_FILEPATH, S3_FACULTIES_UNPRUNED_FILEPATH)
    upload_file_to_s3(LOCAL_FACULTIES_FILEPATH, S3_FACULTIES_FILEPATH)

if __name__ == '__main__':
    main()
