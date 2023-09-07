from bs4 import Tag
import logging
import copy
import regex as re
from typing import List, Dict, Callable, Tuple, Optional
from website_dump_doc_extractor import make_tag, DEFAULT_SPLIT_CLASS, DEFAULT_TITLE_TAGS

"""
Contains processing functions for the website dump processing

These functions can be referred to by name in the file 'dump_config.json5'.
You can use these existing functions, or add your own.

This file contains processing functions specific to UBC Science Advising
"""

log = logging.getLogger(__name__)

### REPLACEMENT FUNCTIONS
"""
These are functions to convert a BeautifulSoup Tag into another Tag
They are applied to Tags that match certain attributes, as defined
in dump_config.json5
"""

def convert_table(table: Tag, url: str) -> Tag:
    """
    Converts any table in the page to a more machine readable format
    """
    if not table.find():
        # Empty table, ignore it
        return make_tag('div')
    
    new_table = table
    first_header = table.find("th")
    table_title = table.find(['h1','h2','h3','h4'])
    if not table_title: table_title = table.find_previous(['h1','h2','h3','h4'])
    table_title = table_title.text.strip()

    if first_header and first_header.text.strip() == '':
        # Likely a double-indexed table (both the rows and columns have headers)
        new_table = table_conversion_function(table,convert_double_indexed_row)
    else:
        log.info(f' No specific function provided to handle the table (will try to handle as a generic table): \n - URL: {url} \n - Title: {table_title}')

        try:
            new_table = table_conversion_function(table,convert_general_table_row)
        except Exception as e:
            log.error(f'Could not handle table: "{table_title}". Please add a method to handle this type of table.')
            log.debug(f'Error msg: {str(e)}')
            return table
    return new_table

def table_conversion_function(table: Tag, handle_row: Callable[[List[Tag], Dict, List[Tuple[Tag,str]]],Tag]) -> Tag:
    """
    Converts a table tag by applying the handle_row function to all data rows
    
    Definition for the handle_row function:
    Inputs:
    - cells: List[Tag], the list of cell tags in the row
    - footnotes: Dict, a dict of footnotes extracted from the table, if there are any
    - headers: List[Tuple[Tag,str]]], a list of tuples with each header's footnote, and text
               if there is no footnote in a header, the first element of the tuple is None.
    Outputs:
    - Outputs a single Tag object, should be a 'li' tag to insert into the output list
    """
    current_list = make_tag('ul')
    output = make_tag('div', current_list)
    headers = None

    footnotes = collect_footnotes(table)
    if footnotes != {} and not table.find(['td','th']):
        # This is a table of footnotes only, convert to a list
        return handle_footnotes_only_table(footnotes)
    
    row = table.find('tr')
    while row and table in row.parents:
        if title := row.find(['h1','h2','h3','h4']): 
            # row is a title row
            output.append(make_tag('p',title.text.strip(),{'class': DEFAULT_SPLIT_CLASS}))
            current_list = make_tag('ul')
            output.append(current_list)
        else:
            cells = get_row_cells(row)
            if len(cells) == 0:
                pass # ignore rows with no cells
            elif len(cells) == 1 and cells[0].name == 'th':
                # row with single heading becomes start of new list
                th = cells[0]
                footnote = combine_cell_footnotes(th, footnotes,remove_sup=True)
                p = make_tag('p',make_tag('div',th.text.strip(),{'class': DEFAULT_SPLIT_CLASS})) # title
                if footnote: p.extend(['(', *footnote.contents, ')']) # footnote
                
                ul = make_tag('ul')
                current_list = ul
                output.extend([p,ul])
            elif subtable := cells[0].find('table'):
                # nested table
                output.append(table_conversion_function(subtable, handle_row))
                subtable.decompose()
            elif cells[0].name == 'th':
                # Headers row, collect the headings (tuples of the heading's footnote if it exists, and the text)
                headers = [(combine_cell_footnotes(cell,footnotes,remove_sup=True), cell.text.strip()) for cell in cells]
            else:
                # Data row, let the handle_row function convert it
                if elem := handle_row(cells,footnotes,headers):
                    current_list.append(elem)
        
        row = row.find_next('tr')
    return output

def handle_footnotes_only_table(footnotes):
    """
    Some tables contain only footnotes, convert footnotes to a list
    eg. "Fee assessment exceptions" at https://vancouver.calendar.ubc.ca/fees/policies-fees 
    """
    ul = make_tag('ul')
    for num, note in footnotes.items():
        ul.append(make_tag('li',['[',num,'] ', *note.contents]))
    return ul

def convert_cell(cell: Tag, footnotes: Dict) -> List[Tag]:
    """
    Creates a list of contents from a generic cell and inserts footnotes if applicable
    """
    cell_footnote = combine_cell_footnotes(cell,footnotes,remove_sup=True)
    output = [*cell.contents]
    if cell_footnote:
        output.extend([' (',*cell_footnote.contents,')'])
    return output

def convert_cell_and_header(cell: Tag, header: Tuple[Tag, str], footnotes: Dict) -> List[Tag]:
    """
    Creates a list of contents for a generic cell and its corresponding header
    Inserts footnotes if applicable
    """
    cell_footnote = combine_cell_footnotes(cell,footnotes,remove_sup=True)
    output = [header[1],': ',*cell.contents]
    if cell_footnote:
        output.extend([' (',*cell_footnote.contents,')'])
    if header_footnote := header[0]:
        copy_footnote = copy.copy(header_footnote)
        output.extend([' (',*copy_footnote.contents,')'])
    return output

def convert_general_table_row(cells: list[Tag], footnotes: Dict, headers: list[str]) -> Tag:
    """
    Converts row from a generic table to a list entry
    """
    li = make_tag('li')
    if not headers and len(cells) == 2:
        li.extend([*convert_cell(cells[0],footnotes),': ',*convert_cell(cells[1],footnotes)])
    elif len(cells) == 1:
        # Assuming this is a note cell, not needing a header
        li.extend(convert_cell(cells[0],footnotes))
    else:
        if not headers:
            for cell in cells:
                li.extend([*cell.contents,'; '])
        elif headers[0][1].strip() == '':
            # Leftmost column has no header, treat as its own header for the row
            li.append(make_tag('p',cells[0]))
            ul = make_tag('ul')
            for i in range(1,len(cells)):
                ul.append(make_tag('li',convert_cell_and_header(cells[i],headers[i],footnotes)))
            li.append(ul)
        else:
            for i in range(len(cells)):
                li.extend(make_tag('li',convert_cell_and_header(cells[i],headers[i],footnotes)))
                li.append('; ')
    return li

def convert_double_indexed_row(cells: list[Tag], footnotes: dict, headers: list[str]) -> Tag:
    """
    Converts row from a generic double indexed table from the academic calendar to a 
    more machine-understandable format
    
    Double indexed: both the first row and the first column are headers. 
    eg: the term dates table at https://vancouver.calendar.ubc.ca/dates-and-deadlines
    """
    p = make_tag('p',cells[0].contents)
    ul = make_tag('ul')
    for i in range(1,len(cells)):
        ul.append(make_tag('li',convert_cell_and_header(cells[i],headers[i],footnotes)))

    return make_tag('li',[p,ul])

def collect_footnotes(table: Tag) -> Dict:
    """
    Finds all footnotes in the table, removes them from the table,
    and returns a dict of footnote indices and contents
    """
    # Collect all footnotes
    footnotes = {}
    footnote_cells = table.find_all(is_footnote_cell)
    rows_to_remove = set()
    for footnote in footnote_cells:
        sup = footnote.find("sup")
        if not sup: continue # ignore footnotes without superscript
        num = str(sup.text)
        sup.decompose()
        rows_to_remove.add(footnote.find_previous('tr'))
        footnotes[num] = footnote.extract()

    for row in rows_to_remove: row.decompose() # Remove the footnote row from the table
    
    return footnotes

def inject_footnote(cell: Tag, footnotes: Dict, prefix: str =' Note: ', suffix: str = ''):
    """
    Injects the cell's footnote in place of a <sup> tag
    - cell: the cell to inject footnote into
    - footnotes: dict of footnotes
    - prefix: text to place before the note
    - suffix: text to place after the note
    """
    note = combine_cell_footnotes(cell,footnotes)
    if note:
        sup = cell.find('sup')
        sup.replace_with(make_tag('div',[prefix, note, suffix]))

def is_footnote_cell(tag: Tag):
    """
    Filter function returns true if the tag is a footnote cell
    """
    if not tag or not (tag.name in ['td','p']): return False
    if tag.get('class') == 'footnote': return True # tag's class is footnote
    for child in tag.contents:
        if child and child.name == 'sup': return True # tag's first child is superscript
        if child.text and child.text.strip() != '': return False
    return False

def get_footnotes_for_indexes(indexes: List[int], footnotes: Dict, strip_newlines=True) -> List[Tag]:
    """
    Returns the list of footnote contents for the given indexes,
    if they exist in the footnotes dict.
    Will return a copy of all contents so they can be inserted into
    another tag.
    """
    notes = []
    for index in indexes:
        if index in footnotes:
            copy_footnote = copy.copy(footnotes[index]).contents
            if strip_newlines and len(copy_footnote) > 0:
                if copy_footnote[0] == '\n': 
                    if len(copy_footnote) > 0:
                        copy_footnote = copy_footnote[1:]
                    else:
                        copy_footnote = []
                if copy_footnote[-1] == '\n': copy_footnote = copy_footnote[:-1]
            notes.append(copy_footnote)
    return notes

def find_cell_footnotes(cell: Tag, footnotes: Dict, remove_sup=False) -> Optional[List[Tag]]:
    """
    If the given table cell contains a footnote index in <sup> tag, then returns
    the corresponding notes from the footnotes dict.
    - remove_sup: If true, also removes the <sup> tag from the cell
    """
    if sup := cell.find("sup"):
        notes = []
        indexes = sup.text.split(',')
        notes = get_footnotes_for_indexes(indexes,footnotes)
        if remove_sup: sup.decompose()
        return notes
    return None

def combine_cell_footnotes(cell: Tag, footnotes: Dict, remove_sup=False) -> Tag:
    """
    If the given table cell contains a footnote index in <sup> tag, then returns
    the corresponding notes from the footnotes dict, combined into one tag.
    - remove_sup: If true, also removes the <sup> tag from the cell
    """
    notes = find_cell_footnotes(cell,footnotes,remove_sup)
    if not notes: return None

    note_tag = make_tag('div')
    for note in notes:
        note_tag.extend([*note, ' '])
    return note_tag

### UTILITIES FOR REPLACEMENT FUNCTIONS

def get_row_cells(row: Tag) -> list[Tag]:
    """
    Gets the list of cells in the row
    Removes trailing empty cells
    """
    cells: list[Tag] = row.find_all(['td','th'])
    for cell in reversed(cells):
        if cell.text.strip() == '': cells.remove(cell)
        else: break
    return cells

### METADATA EXTRACTION FUNCTIONS
"""
These functions extract metadata for extracts.
They are specified by name on a site-by-site basis in the dump_config.json5 file.
"""

faculty_prefixes = ['The Faculty of', 'The School of']
faculty_suffixes = ['College(s)?', 'School of \w+']
faculty_prefix_regex = f"({'|'.join(faculty_prefixes)}).+"
faculty_suffix_regex = f".+({'|'.join(faculty_suffixes)})"
faculty_regex = re.compile(f"^({faculty_prefix_regex}|{faculty_suffix_regex})$")

program_prefixes = ['Bachelor of','Master of','Doctor of','Diploma in','Certificate in','(Dual Degree )?Program in', 'B.[\w\.]+ in']
program_suffixes = ['Program','Programs']
program_prefix_regex = f"(\w+\s)?({'|'.join(program_prefixes)}).+"
program_suffix_regex = f".+({'|'.join(program_suffixes)})"
program_regex = re.compile(f"^({program_prefix_regex}|{program_suffix_regex})$")

specialization_prefixes = ['Combined Major','Major','Minor','Combined Honours','Honours']
specialization_suffixes = ['Major','Minor']
specialization_prefix_regex = f"({'|'.join(specialization_prefixes)}).+"
specialization_suffix_regex = f".+({'|'.join(specialization_suffixes)})"
specialization_regex = re.compile(f"^({specialization_prefix_regex}|{specialization_suffix_regex})$")

def default_extract_metadata(url: str, titles: List[str], parent_titles: List[str], text: str):
    """
    Extracts metadata from titles, if any title elements match the
    faculty, program, or specialization regex.
    """
    metadata = {}
    for subtitle in parent_titles + titles:
        if 'faculty' not in metadata and re.match(faculty_regex, subtitle):
            metadata['faculty'] = subtitle
        if 'program' not in metadata and re.match(program_regex, subtitle):
            metadata['program'] = subtitle
        if re.match(specialization_regex, subtitle):
            if 'specialization' not in metadata:
                metadata['specialization'] = []
            metadata['specialization'].append(subtitle)
    return metadata

### SPLIT TAG PREDICATES 
"""
These are predicates that identify tags that will be used for splitting the page.
The predicate functions are necessary only if you need more complicated logic
than can be specified with attributes.
The predicates are indicated by name under the split_tags for a site in dump_configs.json5
"""

def is_h3_or_split_class(tag: Tag) -> bool:
    """
    Returns true if a tag is a h3 tag 
    OR it has the split class applied
    """
    return tag.name == 'h3' or DEFAULT_SPLIT_CLASS in tag.get_attribute_list('class')

def strong_tag_title(tag: Tag) -> bool:
    """
    Identifier of titles indicated by <strong> tags
    """
    # Check that the tag is a strong tag and contains text
    if tag.name != 'strong': return False
    if not tag.string: return False
    
    # Check that the tag has a length within a given range
    tag_text_len = len(tag.string)
    if tag_text_len < 1 or tag_text_len > 80: return False
    
    # Ensure that the tag is not within a table
    next_sib = tag.next_sibling
    parents = tag.parents
    for parent in parents:
        if parent.name in (DEFAULT_TITLE_TAGS + ['table','ul']): return False
    return next_sib == None

### CONTEXT EXTRACTION FUNCTIONS
"""
These functions identify 'context' text in a parent extract, that should be included
with child extracts. The context is included in the 'context' column of child extracts.
The functions will be applied on a site-by-site basis as defined in dump_configs.json5
"""

def parent_context_extractor(url: str, titles: List[str], parent_titles: List[str], text: str) -> str:
    """
    Given the contents of a 'parent' document extract, returns any context that 
    should be considered for child pages.
    Eg. if the parent extract describes the purpose of a table, that purpose should be
        considered for child pages containing the actual table
    """
    keywords = ['below','as follows']
    if len(text) < 400 and any(keyword in text for keyword in keywords): 
        return text
    return None