from bs4 import BeautifulSoup
from website_dump_doc_extractor import DocExtractor, DumpConfig, DEFAULT_SPLIT_CLASS, make_tag
import json
import logging
from tools import write_file
from os.path import join
import copy 
import regex as re
from typing import List

"""
Processing functions specific to the data sources:
- UBC Academic Calendar
- UBC Science Distillation Blog

Uses the DocExtractor class from website_dump_doc_extractor
"""

log = logging.getLogger(__name__)
unhandled_tables = {}
error_tables = {}


### PAGE PREPROCESSING FUNCTIONS

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

def convert_table(table: BeautifulSoup, url: str) -> BeautifulSoup:
    """
    Converts any table in the page to a more machine readable format
    Specifically converts degree requirements tables, and attempts to convert all others
    - soup: BeautifulSoup object for the page
    """
    if not table.find():
        # Empty table, ignore it
        return make_tag('div')
    
    new_table = table
    first_header = table.find("th")
    table_title = table.find(['h1','h2','h3','h4'])
    if not table_title: table_title = table.find_previous(['h1','h2','h3','h4'])
    table_title = table_title.text.strip()

    if first_header and (first_header.text.strip() in ["First Year","Lower-level Requirements","Lower-Level Prerequisites","Term 1","Year One"] or 
        table.find(string=lambda x: x and x.strip().lower() in ["total credits","program total"])):
        # Table is a degree requirements table
        new_table = table_conversion_function(table,convert_degree_requirements_row)
    elif first_header and "Sessional Average & Course Success" in first_header.text.strip():
        new_table = table_conversion_function(table,convert_continuation_requirements_row)
    elif 'B.Sc. Specialization-Specific Courses Required for Promotion' in table_title:
        new_table = table_conversion_function(table,convert_promotion_courses_row)
    elif first_header and first_header.text.strip() == '':
        # Likely a double-indexed table (both the rows and columns have headers)
        new_table = table_conversion_function(table,convert_double_indexed_row)
    else:
        log.info(f' No specific function provided to handle the table (will try to handle as a generic table): \n - URL: {url} \n - Title: {table_title}')

        add_elem_to_dict(unhandled_tables,url,table_title)

        try:
            new_table = table_conversion_function(table,convert_general_table_row)
        except Exception as e:
            log.error(f'Could not handle table: "{table_title}". Please add a method to handle this type of table.')
            log.debug(f'Error msg: {str(e)}')
            add_elem_to_dict(error_tables,url,table_title)
            return table
    return new_table

def table_conversion_function(table: BeautifulSoup, handle_row) -> BeautifulSoup:
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
                # nested table, seen in some pages eg. https://vancouver.calendar.ubc.ca/emeriti-staff 'Librarians' section
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

def convert_degree_requirements_row(cells: list[BeautifulSoup], footnotes: list[BeautifulSoup], *_) -> BeautifulSoup:
    """
    Converts a row from the degree requirements table from the academic calendar to a 
    more machine-understandable format
    """
    notes = find_cell_footnotes(cells[0],footnotes,remove_sup=True)
    if len(cells) == 2:
        li = make_tag('li', [f"{cells[1].text.strip()} credits of {cells[0].text.strip()}"])
        if notes: 
            note_lis = [make_tag('li',note) for note in notes]
            li.append(make_tag('ul',note_lis))
        return li
    else:
        return make_tag('li', cells[0].contents)

def convert_continuation_requirements_row(cells: list[BeautifulSoup], *_) -> BeautifulSoup:
    """
    Converts a row from the continuation requirements table from the academic calendar to a 
    more machine-understandable format

    Intended table:
    https://vancouver.calendar.ubc.ca/faculties-colleges-and-schools/faculty-science/bachelor-science/academic-performance-review-and-continuation#18568
    """
    headers = ['', 'Good standing', 'Academic Probation (ACPR)', 'Failed standing, permitted to continue']

    if cells[0] == None or cells[0].string.strip() == '': return None # skip the row of standings upon entering session

    p = make_tag('p',f'Sessional average & course success: {cells[0].text.strip()}')
    ul = make_tag('ul', [make_tag('li', f'Standing Upon Entering Session: {headers[i]}; New Standing: {cells[i].text.strip()}') 
                             for i in range(1,4)])
    
    return make_tag('li',[p,ul])

def convert_promotion_courses_row(cells: list[BeautifulSoup], _, headers) -> BeautifulSoup:
    """
    Converts row from a promotion courses table from the academic calendar to a 
    more machine-understandable format

    Example of the intended table: 
    https://vancouver.calendar.ubc.ca/faculties-colleges-and-schools/faculty-science/bachelor-science/bsc-specialization-specific-courses-required-promotion
    """
    if not hasattr(convert_promotion_courses_row, 'state'): convert_promotion_courses_row.state = None

    if len(cells) == 1:
        convert_promotion_courses_row.state = cells[0].text.strip()
        return None
    else:
        p = make_tag('p', convert_promotion_courses_row.state)
        ul = make_tag('ul',[
            make_tag('li', f'{headers[1][1]}: {cells[1].text.strip()}'),
            make_tag('li', f'{headers[2][1]}: {cells[2].text.strip()}')])
        return make_tag('li',[p,ul])

def convert_cell(cell, footnotes):
    """
    Creates a list of contents for a generic cell and inserts footnotes if applicable
    """
    cell_footnote = combine_cell_footnotes(cell,footnotes,remove_sup=True)
    output = [*cell.contents]
    if cell_footnote:
        output.extend([' (',*cell_footnote.contents,')'])
    return output

def convert_cell_and_header(cell, header, footnotes):
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

def convert_general_table_row(cells: list[BeautifulSoup], footnotes: dict, headers: list[str]) -> BeautifulSoup:
    """
    Converts row from a generic table from the academic calendar to a 
    more machine-understandable format
    """
    li = make_tag('li')
    if not headers and len(cells) == 2:
        li.extend([*convert_cell(cells[0],footnotes),': ',*convert_cell(cells[1],footnotes)])
    elif len(cells) == 1:
        # Assuming this is a note cell, not needing a header
        return li.extend(convert_cell(cells[0],footnotes))
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

def convert_double_indexed_row(cells: list[BeautifulSoup], footnotes: dict, headers: list[str]):
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

def collect_footnotes(table):
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

def inject_footnote(cell, footnotes, prefix: str =' Note: ', suffix: str = ''):
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

def is_footnote_cell(tag):
    """
    Filter function returns true if the tag is a footnote cell of a requirements table
    """
    if not tag or not (tag.name in ['td','p']): return False
    if tag.get('class') == 'footnote': return True
    for child in tag.contents:
        if child and child.name == 'sup': return True
        if child.text and child.text.strip() != '': return False
    return False

def get_footnotes_for_indexes(indexes,footnotes,strip_newlines=True):
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

def find_cell_footnotes(cell,footnotes,remove_sup=False):
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

def combine_cell_footnotes(cell,footnotes,remove_sup=False):
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

### UTILITY FNS

def add_elem_to_dict(dict, url, title):
    """
    Adds the given title to dict, indexed by the url
    If there is already an element in the dict at this url, appends the new title
    """
    if url not in dict:
        dict[url] = []
    dict[url].append(title)

def get_row_cells(row: BeautifulSoup) -> list[BeautifulSoup]:
    """
    Gets the list of cells in the row
    Removes trailing empty cells
    """
    cells: list[BeautifulSoup] = row.find_all(['td','th'])
    for cell in reversed(cells):
        if cell.text.strip() == '': cells.remove(cell)
        else: break
    return cells

### DUMP CONFIGS

BASE_DUMP_PATH = 'site_dumps'

generic_remove_tags = [
    {'class': 'sr-only'},               # screenreader only tags
    {'class': 'hidden'},                # hidden tags
    {'name': 'a', 'href': '#top'}       # 'go to top' links
]

faculty_prefixes = ['The Faculty of', 'The School of']
faculty_suffixes = ['College(s)?', 'School of \w+']
faculty_prefix_regex = f"({'|'.join(faculty_prefixes)}).+"
faculty_suffix_regex = f".+({'|'.join(faculty_suffixes)})"
faculty_regex = re.compile(f"^({faculty_prefix_regex}|{faculty_suffix_regex})$")

program_prefixes = ['Bachelor of','Master of','Doctor of','Diploma in','Certificate in','Program in', 'B.[\w\.]+ in']
program_suffixes = ['Program','Programs']
program_prefix_regex = f"(\w+\s)?({'|'.join(program_prefixes)}).+"
program_suffix_regex = f".+({'|'.join(program_suffixes)})"
program_regex = re.compile(f"^({program_prefix_regex}|{program_suffix_regex})$")

specialization_prefixes = ['Combined Major','Major','Minor','Combined Honours','Honours']
specialization_suffixes = ['Major','Minor']
specialization_prefix_regex = f"({'|'.join(specialization_prefixes)}).+"
specialization_suffix_regex = f".+({'|'.join(specialization_suffixes)})"
specialization_regex = re.compile(f"^({specialization_prefix_regex}|{specialization_suffix_regex})$")

def calendar_extract_metadata(url: str, titles: List[str], parent_titles: List[str], text: str):
    metadata = {}
    for subtitle in parent_titles + titles:
        if 'faculty' not in metadata and re.match(faculty_regex, subtitle):
            metadata['faculty'] = subtitle
        if 'program' not in metadata and re.match(program_regex, subtitle):
            metadata['program'] = subtitle
        if 'specialization' not in metadata and re.match(specialization_regex, subtitle):
            metadata['specialization'] = subtitle

    if re.search('\* \d+ credits of ', text):
        if 'specialization' in metadata:
            metadata['context'] = f"This is a list of degree requirements for {metadata['specialization']}.\n"
        else: metadata['context'] = f'This is a list of degree requirements.\n'

    return metadata

def blog_extract_metadata(url: str, titles: List[str], parent_titles: List[str], text: str):
    metadata = {'faculty': 'The Faculty of Science'}
    return metadata

calendar_is_new_format = True
calendar_config = DumpConfig()
calendar_config.base_url = 'https://vancouver.calendar.ubc.ca/'
calendar_config.dump_path = BASE_DUMP_PATH + '\\vancouver.calendar.ubc.ca\\'
calendar_config.remove_tag_attrs = generic_remove_tags + [{'id': 'block-shareblock'}] if calendar_is_new_format else [{'id': 'shadedBox'},{'id': 'breadcrumbsWrapper'}]
calendar_config.replacements = [({'name': 'table'}, convert_table)]
calendar_config.main_content_attrs = {'id': 'primary-content' if calendar_is_new_format else 'unit-content'}
calendar_config.title_attrs = {'name': 'h1'}
calendar_config.metadata_extractor = calendar_extract_metadata
calendar_config.parent_context_extractor = parent_context_extractor

sc_students_config = DumpConfig()
sc_students_config.base_url = 'https://science.ubc.ca/students/'
sc_students_config.dump_path = BASE_DUMP_PATH + '\\science.ubc.ca\\students\\'
sc_students_config.remove_tag_attrs = generic_remove_tags + [{'class': 'customBread'},{'id': 'block-views-student-notices-block-2'},{'class':'field-name-field-student-blog-topic'}]
sc_students_config.replacements = [({'name': 'table'}, convert_table)]
sc_students_config.main_content_attrs = {'id': 'content'}
sc_students_config.title_attrs = {'name': 'h1'}
sc_students_config.metadata_extractor = blog_extract_metadata
sc_students_config.parent_context_extractor = None

### MAIN FUNCTION

def process_site_dumps(dump_configs: list[DumpConfig] = [calendar_config,sc_students_config], 
                       redirect_map_path: str = BASE_DUMP_PATH + '\\redirects.txt', 
                       out_path: str = BASE_DUMP_PATH + '\\processed\\'):
    """
    Parse website dumps
    - dump_configs
    - redirect_map_path: filepath to the redirect map
    """

    doc_extractor = DocExtractor()
    doc_extractor.max_len = 1000
    doc_extractor.overlap_window = 100

    # Read the redirect map
    if redirect_map_path:
        with open(redirect_map_path,'r') as f:
            redirect_map = json.loads(f.read())
            doc_extractor.link_redirects = redirect_map

    doc_extractor.parse_folder(dump_configs,out_path)

    def writer():
        unhandled_tables_file = join(out_path,'unhandled_tables.txt')
        error_tables_file = join(out_path,'error_tables.txt')
        with open(unhandled_tables_file,'w') as f:
            json.dump(unhandled_tables,f, indent=4)
        with open(error_tables_file,'w') as f:
            json.dump(error_tables,f, indent=4)
    
    try:
        write_file(writer)
        log.info(" Wrote titles of unhandled and error tables to 'unhandled_tables.txt', 'error_tables.txt'")
    except:
        log.error(" Couldn't save record of unhandled and error table")