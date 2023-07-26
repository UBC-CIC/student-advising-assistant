import json

### Helpers
def load_json_file(file: str):
    with open(file,'r') as f: 
        return json.load(f)
