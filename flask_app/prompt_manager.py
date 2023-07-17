import os
import csv
from typing import List, Optional

SAMPLES_PATH = os.path.join('config','prompt_samples.csv')
CATEGORIES_PATH = os.path.join('config','prompt_categories.csv')

class PromptCategory:
    name: str
    retriever_keywords: str
    generator_prompt: str
    metadata: Optional[dict]
    
    def __init__(self, name: str, retriever_keywords: str, generator_prompt: str, metadata: Optional[dict]) -> None:
        """
        Create a prompt category for augmenting the retrieval augmented generation system
        - name: Display name for the prompt (used only for logging)
        - retriever_keywords: Keywords to add to the request to the retriever when using this prompt category
        - generator_prompt: Prelude to add to the generator prompt when using this prompt category
        - metadata: Dict of values to match against the input program_info - the category only applies when the values match
        """
        self.name = name
        self.retriever_keywords = retriever_keywords
        self.generator_prompt = generator_prompt
        self.metadata = metadata
            
class PromptManager:
    categories = {}
    samples = []
    sample_to_category = {}

    def read_config(self):
        # Read the prompt category data
        with open(CATEGORIES_PATH, 'r') as stream:
            reader = csv.DictReader(stream)
            count = 0
            for row in reader:
                if count == 0: continue # skip the header
                # Separate the row into named columns and metadata filter columns
                named_columns = {"Category", "Retriever Keywords", "Generator Prompt"}
                metadata_filter = {k: row[k] for k in row.keys() - named_columns}
                category: PromptCategory = PromptCategory(*[row[k] for k in named_columns], metadata_filter)
                self.categories[category.name] = category
                count += 1
        
        # Read the prompt samples data
        with open(SAMPLES_PATH, 'r') as stream:
            reader = csv.DictReader(stream)
            count = 0
            for row in reader:
                if count == 0: continue # skip the header
                category_name = row["Category"]
                prompt = row["Prompt"]
                # Add the prompt to the list of samples
                self.samples.append(prompt)
                
                # Add reference from the prompt index to its category
                if category_name not in self.categories:
                    raise Exception(f'Found prompt with undefined category {category}')
                self.sample_to_category[count - 1] = self.categories[category_name]
                
                count += 1
            
    def __init__(self):
        self.read_config()
        