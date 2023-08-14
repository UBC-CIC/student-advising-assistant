import pandas as pd
import ast 
import numpy as np
from typing import Dict
from dictdiffer import diff, patch
import pyjson5 as json5
import logging 

log = logging.getLogger(__name__)

def load_json_file(filepath: str) -> Dict:
    # Helper function to read file contents to json
    with open(filepath) as f:
        # Use json5, more lenient with trailing commas
        return json5.load(f)
    
def find_program_options(website_extracts_path: str) -> Dict:
    """
    Creates a dict of hierarchical program options (faculty, program, specialization)
    From all those available in the list of website extracts
    """
    df = pd.read_csv(website_extracts_path)

    faculties = {}
    faculty_groups = df.groupby('faculty')
    for group in faculty_groups:
        programs = {}
        program_groups = group[1].groupby('program')
        for group2 in program_groups:
            specializations = []
            for spec_list in group2[1]['specialization'].dropna().apply(ast.literal_eval):
                # Specializations are a list for each document
                specializations += spec_list
            specializations = np.unique(np.array(specializations))
            programs[group2[0]] = {'specializations': {specialization: {} for specialization in specializations}}
            
        """Uncomment the line below if you want to include the ids of documents in this faculty"""
        #faculties[group[0]] = {'programs': programs, 'doc_ids': group[1]['doc_id'].tolist()}
        faculties[group[0]] = {'programs': programs}
    
    return faculties

def apply_previous_difs(new_unpruned_faculties: Dict, old_unpruned_filepath: str, old_pruned_filepath: str) -> Dict:
    """
    Given the pruned and unpruned versions of a previously generated faculties dict, 
    apply the same changes to the new unpruned faculties dict.
    """
    # Find the diff between the previous iteration of faculties.json, if the files exist
    old_faculties_diff = None
    try:
        old_unpruned_faculties = load_json_file(old_unpruned_filepath)
        old_faculties = load_json_file(old_pruned_filepath)
        old_faculties_diff = diff(old_unpruned_faculties,old_faculties)
    except Exception as e:
        logging.error('Error while reading faculties files')
        logging.error(e)
        
        # The faculties files don't already exist, the diff is none
        old_faculties_diff = diff({}, {})
            
    # Create new faculties json and apply dif
    new_pruned_faculties = patch(old_faculties_diff, new_unpruned_faculties)
    
    return new_pruned_faculties