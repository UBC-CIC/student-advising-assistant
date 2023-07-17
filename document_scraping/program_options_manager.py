import pandas as pd
import json
import ast 
from tools import write_file
import numpy as np
import os

def find_program_options(website_extracts_path: str):
    """
    Creates a json file of hierarchical program options (faculty, program, specialization)
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
    
    def writer():
        with open(f'{os.path.dirname(website_extracts_path)}/faculties.txt','w') as f: 
            json.dump(faculties,f,indent=4)
    
    write_file(writer)
    
find_program_options('./processed/website_extracts.csv')