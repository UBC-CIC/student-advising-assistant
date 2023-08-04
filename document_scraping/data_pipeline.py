import platform
import os
import sys
import regex as re
import pyjson5 as json5
import json
from subprocess import check_call, STDOUT, CalledProcessError
import logging
from typing import Dict, List, Tuple, Any
from tools import write_file
import process_site_dumps
from website_dump_doc_extractor import DumpConfig, DocExtractor
from program_options_manager import find_program_options
from dotenv import load_dotenv
from dictdiffer import diff, patch
load_dotenv()
sys.path.append('..')
from aws_helpers.s3_tools import upload_file_to_s3, download_single_file, download_s3_directory

"""
Script to download the data sources using wget, and then split all pages into document extracts for 
downstream tasks.
"""

### CONSTANTS
# Input files
CONFIG_FILEPATH = 'dump_config.json5' # Filepath to the dump config file in current working dir
download_single_file(f"document_scraping/{CONFIG_FILEPATH}", CONFIG_FILEPATH)

WGET_EXE_PATH = "wget.exe" # Wget executable used on non-unix systems
WGET_CONFIG_PATH = 'wget_config.txt' # Config file for wget calls

# Output files
BASE_DUMP_PATH = 'site_dumps' # Directory where site dump files are saved
OUTPUT_PROCESSED_PATH = 'processed' # Directory where processed extracts are saved
REDIRECT_FILEPATH = os.path.join(BASE_DUMP_PATH,'redirects.txt') # Filepath for dict of redirects
FACULTIES_UNPRUNED_FILEPATH = os.path.join(OUTPUT_PROCESSED_PATH, "faculties_unpruned.json")
FACULTIES_FILEPATH = os.path.join(OUTPUT_PROCESSED_PATH, "faculties.json")

# Other constants
redirect_log_re = re.compile('http[^\n]*(\n[^\n]*){2}301 Moved Permanently\nLocation:\s[^\n\s]*')
# ^ regex matches entries in the wget logs that indicate a redirect
function_refs_file = process_site_dumps
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

def site_regex_rule(base_url: str) -> str:
    """
    Generates a regex string to match only sub urls of the given
    base url. Used in wget calls to fetch child pages of sites.
    """
    url_segments = [segment for segment in base_url.split('/') 
                        if len(segment) > 0 and not segment.startswith('http')]
    return f".*{re.escape('/'.join(url_segments))}.*"
    
### Main function to pull websites and process
def pull_sites(dump_configs: List[DumpConfig], system_os, output_folder = './', wget_exe_path = './wget.exe', wget_config_path = './wget_config.txt'):
    """
    Uses wget to pull the indicated websites, and processes
    the files into one combined csv of documents for use in the UBC Science 
    Advising question answering system.
    - dump_configs: Config objects for the sites to pull
    - system_os: 
    - output_folder: directory for the output site dumps
    - wget_exe_path: path to the wget.exe file
    - wget_config_path: path to the wget config file (aka .wgetrc)
    """
    # create the output dir if not exists, otherwise do nothing
    os.makedirs(output_folder, exist_ok=True)
    redirects = {}
    total_num = 0
    for dump_config in dump_configs:
        logging.info(dump_config)
        log_file = os.path.join(output_folder,f'wget_log_{dump_config.name}.txt')
        regex_rule_arg = f'--accept-regex=({site_regex_rule(dump_config.base_url)})'
            
        try:
            logging.info(f'- Beginning pull from {dump_config.base_url}, making call to wget')
            logging.info(f'    - ** This may take a long time')
            logging.info(f'    - Check the log file {log_file} for updates')
            if system_os == "Windows":
                check_call([wget_exe_path, f'--config={wget_config_path}', f'--output-file={log_file}', '--recursive', 
                            f'--directory-prefix={output_folder}', regex_rule_arg, dump_config.base_url], stderr=STDOUT)
            elif system_os in ["Darwin", "Linux"]:
                check_call(["wget", f'--config={wget_config_path}', f'--output-file={log_file}', '--recursive', 
                            f'--directory-prefix={output_folder}', regex_rule_arg, dump_config.base_url], stderr=STDOUT)
            else:
                logging.error(f"OS {system_os} is not currently supported. Currently supported OS are Windows, Darwin and Linux")
                raise OSError(f"OS {system_os} is not currently supported")
            logging.info(f'- Successfully pulled from {dump_config.base_url}')
        except CalledProcessError as exc:
            if exc.returncode == 8:
                # Server error return code
                logging.warning('- wget returned code 8, indicating server error:' 
                                + 'this will occur if it comes across any 404 error, so it is expected for the Academic Calendar.' 
                                + 'Please check that files were downloaded correctly.')
            else: 
                logging.error('- Call to wget failed')
                logging.error(f'- Error message: {exc.output}' if exc.output else 'No error message given')
        
        total_num += get_redirects_from_log(log_file, redirects)
    
    # Cleanup copied files
    logging.info("Cleanup any duplicated files from wget")
    cleanup_copy_files(output_folder)
    
    def writer(): 
        os.makedirs(output_folder, exist_ok=True)
        with open(REDIRECT_FILEPATH,'w') as f: json.dump(redirects,f)
    
    write_file(writer)
    print(f'Completed pulling sites, downloaded {total_num} pages')

def cleanup_copy_files(filepath):
    """
    wget will sometimes name the new version of a file as <name>.1.html,
    we want to rename it to <name>.html and delete the previous version
    """
    for root, _, files in os.walk(filepath):
        for name in files:
            splitname = name.split('.')
            if len(splitname) == 3 and splitname[1] == '1':
                # this is a new version of a file
                orig_name = f'{splitname[0]}.{splitname[2]}'
                copy_filepath = os.path.join(root, name)
                orig_filepath = os.path.join(root, orig_name)
                try: os.remove(orig_filepath) # remove the old version of the file
                except OSError: pass
                os.rename(copy_filepath,orig_filepath) # rename copy file to original file

def get_redirects_from_log(log_file, redirects):
    """
    Given a wget log file (on verbose mode), adds any redirected urls to the redirects dict
    Also returns the total number of URLs processed from the log
    """
    logging.info('- Getting redirects from the log file')
    total_num = 0
    with open(log_file,'r') as f: 
        initial_url = None
        redirected = False
        for line in f: # read line by line since the log file could be large
            if re.match(r'Saving to: \'[^\n\s]*\'',line):
                total_num += 1
            elif match := re.search('(?<=--\s\s)[^\n\s]*',line):
                initial_url = match.captures()[0]
                redirected = False
            elif '301 Moved Permanently' in line:
                redirected = True
            elif redirected and (match := re.search('(?<=Location: )[^\n\s]*',line)):
                final_url = match.captures()[0]
                redirects[initial_url] = final_url
    logging.info('- Completed processing redirects')
    return total_num

### Main

def load_json_file(filepath: str) -> Dict:
    # Helper function to read file contents to json
    with open(filepath) as f:
        # Use json5, more lenient with trailing commas
        return json5.load(f)
    
def write_json_file(filepath: str, item: Dict):
    # Helper function to write json to file
    def writer():
        with open(filepath,'w') as f: 
            json.dump(item,f,indent=4)
    
    write_file(writer)
            
def main(recreate_faculties: bool = False):
    """
    - recreate_faculties: if True, recreates the faculties.txt file
                be careful, because the results may have to be
                manually pruned after (remove unnecessary specializations)
    """
    
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # check the system OS since Windows Machine requires a wget.exe
    # darwin (OS X) and Linux probably not
    system_os = platform.system()
    logging.info(f"System OS: {system_os}")

    doc_extractor, dump_configs = load_config(CONFIG_FILEPATH)
    #pull_sites(dump_configs, system_os=system_os, output_folder = BASE_DUMP_PATH, wget_exe_path=WGET_EXE_PATH, wget_config_path=WGET_CONFIG_PATH)
    #process_site_dumps.process_site_dumps(doc_extractor, dump_configs, redirect_map_path=REDIRECT_FILEPATH, out_path=OUTPUT_PROCESSED_PATH)

    # Upload the website_extracts.csv and website_graph.txt
    upload_file_to_s3(os.path.join(OUTPUT_PROCESSED_PATH, "website_extracts.csv"), "documents/website_extracts.csv")
    upload_file_to_s3(os.path.join(OUTPUT_PROCESSED_PATH, "website_graph.txt"), "documents/website_graph.txt")
    
    # Find the diff between the previous iteration of faculties.json, if the files exist
    download_s3_directory('documents')
    old_faculties_diff = None
    try:
        old_unpruned_faculties = load_json_file(FACULTIES_UNPRUNED_FILEPATH)
        old_faculties = load_json_file(FACULTIES_FILEPATH)
        old_faculties_diff = diff(old_unpruned_faculties,old_faculties)
    except Exception as e:
        logging.error('Error while reading faculties files')
        logging.error(e)
        
        # The faculties files don't already exist, the diff is none
        old_faculties_diff = diff({}, {})
        
    # Filter for removal diffs only
    old_faculties_diff = [(type,key,val) for (type,key,val) in old_faculties_diff if type == 'remove']
            
    # Create new faculties json and apply dif
    new_unpruned_faculties = find_program_options(os.path.join(OUTPUT_PROCESSED_PATH, "website_extracts.csv"))
    new_pruned_faculties = patch(old_faculties_diff, new_unpruned_faculties)
    
    # Upload faculties files
    write_json_file(FACULTIES_UNPRUNED_FILEPATH,new_unpruned_faculties)
    write_json_file(FACULTIES_FILEPATH,new_pruned_faculties)
    upload_file_to_s3(FACULTIES_UNPRUNED_FILEPATH, "documents/faculties_unpruned.json")
    upload_file_to_s3(FACULTIES_FILEPATH, "documents/faculties.json")

if __name__ == '__main__':
    main(recreate_faculties=True)
 