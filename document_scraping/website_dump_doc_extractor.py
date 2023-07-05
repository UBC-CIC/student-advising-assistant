from os import listdir, sep, makedirs
import os.path
from urllib.parse import urljoin
from enum import IntEnum
import regex as re
from typing import Callable, Tuple
from bs4 import BeautifulSoup
import html2text
import networkx as nx
import pandas as pd
import spacy
from spacy.language import Language
import tools
from tqdm.auto import tqdm
import logging
from typing import List, Tuple

"""
DocExtractor class:
- Tool to split a website dump into document extracts for Retrieval Augmented Generation or Extractive Question Answering tasks
- Main entry point: DocExtractor.parse_folder method
- Pass in configurations via the DumpConfig class
"""

### CONSTANTS
generic_soup = BeautifulSoup()
nlp = spacy.load("en_core_web_sm",exclude=['tagger','attribute_ruler', 'lemmatizer', 'ner'])
custom_sent_boundaries = [
    '(\n|^)\s*\d+\.', # matches to an item in an enumerated list
    '(\n|^)\s*\*+',   # matches to an item in an itemized list
    '\n\n'       # matches to a new paragraph identified by newlines
    ]
re_custom_sent_boundaries = f"({'|'.join(custom_sent_boundaries)})"
log = logging.getLogger(__name__)

@Language.component('custom_merge')
def merge_custom_tokens(doc):
    with doc.retokenize() as retokenizer:
        spans = [doc.char_span(*match.span(),alignment_mode='expand') for match in re.finditer(re_custom_sent_boundaries,doc.text,flags=re.IGNORECASE)]
        for span in spans:
            retokenizer.merge(span)
    return doc

@Language.component('custom_boundaries')
def set_custom_boundaries(doc):
    for token in doc[:-1]:
        if re.match(re_custom_sent_boundaries, token.text):
            doc[token.i].is_sent_start = True
            doc[token.i+1].is_sent_start = False
    return doc

nlp.add_pipe('custom_boundaries', before='parser')
nlp.add_pipe('custom_merge', before='custom_boundaries')

### DEFAULT VALUES

DEFAULT_TITLE_TAGS = ['h1','h2','h3','h4']

def strong_tag_title(tag: BeautifulSoup) -> bool:
    """
    Identifier of titles indicated by <strong> tags
    """
    if tag.name != 'strong': return False
    if not tag.string: return False
    tag_text_len = len(tag.string)
    if tag_text_len > 1 and tag_text_len < 80:
        next_sib = tag.next_sibling
        parents = tag.parents
        for parent in parents:
            if parent.name in (DEFAULT_TITLE_TAGS + ['table','ul']): return False
        return next_sib == None
    return False

DEFAULT_SPLIT_CLASS = 'extractor-split'
DEFAULT_SPLIT_ATTRS = [{'name': tag} for tag in DEFAULT_TITLE_TAGS] + [{'class':DEFAULT_SPLIT_CLASS},{'function': strong_tag_title}]
DEFAULT_IGNORE_EMPTY_SPLIT_TAGS = True
DEFAULT_MANDATORY_SPLITS = 3
DEFAULT_NO_TITLE_SPLITS = []
DEFAULT_MAX_LEN = 1000
DEFAULT_ENCODING = 'utf-8-sig'
DEFAULT_WINDOW_OVERLAP = 200
DEFAULT_LINK_IGNORE_REGEX = r'mailto:.*'

### CLASS DEFINITIONS

class DocRelation(IntEnum):
    """
    Represents the possible relationships between documents
    """
    PARENT_PAGE = 1
    PARENT_EXTRACT = 2
    LINK = 3
    SIBLING_EXTRACT = 4
    SIBLING_SPLIT_EXTRACT = 5

class DumpConfig:
    """
    Data class containing the configuration details for a particular site dump
    """
    # root directory of the dump files
    dump_path: str
    # base url corresponding to the root directory
    base_url: str
    # dict of attributes describing the page's title tag
    title_attrs: dict
    # dict of attributes describing the main content html tag
    main_content_attrs: dict
    # list of dicts of attributes describing tags to remove
    # as the first step of processing a page
    remove_tag_attrs: List[dict]
    # list of tuples: (dict,function) where the dict describes the attributes of a
    # tag to replace, and the function returns a tag to replace it with
    # - The function inputs are the BeautifulSoup tag and the site url, and it 
    #   should output the replacement BeautifulSoup tag
    replacements: List[Tuple[dict,Callable[[BeautifulSoup,str],BeautifulSoup]]]
    # function that will return any additional metadata to be added to a document
    # inputs: page url, page titles. titles of parent pages, text content for the document
    metadata_extractor: Callable[[str,List[str],List[str],str],dict]
    # Function that, given the contents of a 'parent' document extract, returns any context that 
    # will be included in the 'context' column for child pages
    # Eg. if the parent extract describes the purpose of a table, that purpose should be
    #    considered for child pages containing the actual table
    # inputs: page url, page titles. titles of parent pages, text content for the document
    parent_context_extractor: Callable[[str,List[str],List[str],str],str]
    # Hierarchy of the attributes of tags to split the pages on
    # Documents are split only if the extract is over the maximum document length
    # You can specify a predicate function instead of attributes using {'function': <function name>}
    split_attrs: list
    # If true, will not split a document on a tag matching split attributes if
    # the tag contains no text
    ignore_empty_split_tags: bool
    # Indicates the index of the last element in split_attrs on which to always split
    # the document, regardless of extract length. Any entries beyond this index will
    # only be used to split if the document is longer than the maximum length.
    mandatory_splits: int
    # Indexes of split attrs where the text of the tag should not be used as a new title
    # An integer index will be used instead
    no_title_splits: list[int]
    
    def __init__(self):
        self.split_attrs = DEFAULT_SPLIT_ATTRS
        self.ignore_empty_split_tags = DEFAULT_IGNORE_EMPTY_SPLIT_TAGS
        self.mandatory_splits = DEFAULT_MANDATORY_SPLITS
        self.no_title_splits = DEFAULT_NO_TITLE_SPLITS

class DocIndex:
    """
    DocIndex stores document metadata that is needed during parsing
    Handles assigning indexes to documents
    """
    def __init__(self):
        self.doc_idx = 0
        self.idx_to_doc = {}
        self.url_title_to_idx = {}
        self.url_to_idx = {}
        self.path_to_idx = {}
    
    def add_doc(self, titles: list[str], url:str, path:str = None, parent_titles:str = None) -> int:
        """
        Add the doc to the dictionary, and give it the next available index.
        Returns the index of the new doc.
        Title and url combined must be unique.
        Path, if provided, must be unique.
        """
        title = str(titles)

        if self.has_doc(url,title): 
            return self.url_title_to_idx(url,title)

        idx = self.doc_idx
        url = clean_url(url)
        self.idx_to_doc[idx] = {'titles': titles, 'url': url, 'path': path, 'parent_titles': parent_titles}
        self.url_title_to_idx[(url,title)] = idx

        if not self.has_url(url): self.url_to_idx[url] = []
        self.url_to_idx[url].append(idx)

        if path: self.path_to_idx[path] = idx

        self.doc_idx += 1
        return idx

    def get_doc(self,idx: int) -> str:
        """
        Return the info for the doc with the given index, or none if 
        the index is not in the dictionary
        """
        return self.idx_to_doc[idx] if self.has_idx(idx) else None
    
    def find_doc_idx(self,url: str, titles: list[str]) -> int:
        """
        Return the idx of the doc with the given title and url, or none if 
        the doc is not in the dictionary
        """
        if self.has_doc(url,str(titles)): return self.url_title_to_idx[(url,str(titles))]
        return None
    
    def doc_url_to_idx(self, url: str) -> int:
        """
        Return the idx of the doc with the given title, or none if 
        the url is not in the dictionary
        There may be more than one document with the url: returns 
        the first one that was added
        """
        url = clean_url(url)
        if self.has_url(url): return self.url_to_idx[url][0]
        return None
    
    def doc_path_to_idx(self, path: str) -> int:
        """
        Return the idx of the doc with the given path, or none if 
        the path is not in the dictionary
        """
        if self.has_path(path): return self.path_to_idx[path]
        return None
    
    def has_idx(self,idx: int) -> bool: 
        """
        Return True if the doc with given idx is in the dictionary
        """
        return idx in self.idx_to_doc
    
    def has_doc(self, titles: list[str], url:str) -> bool: 
        """
        Return True if the doc with given title is in the dictionary
        """
        return (url,str(titles)) in self.url_title_to_idx
    
    def has_url(self,url: str) -> bool: 
        """
        Return True if the doc with given url is in the dictionary
        """
        return clean_url(url) in self.url_to_idx
    
    def has_path(self,path: str) -> bool: 
        """
        Return True if the doc with given path is in the dictionary
        """
        return path in self.path_to_idx

class DocExtractor:
    # When the document needs to be split beyond the split attributes, number of
    # characters of overlap to use in the rough splits
    # Note that a token is usually 3-4 characters
    # NOT CURRENTLY IMPLEMENTED
    overlap_window: int
    # Maximum extract length in characters - longer extracts will be further split into parts
    # Note that a token is usually 3-4 characters
    max_len: int
    # Dict of urls that redirect to other urls 
    # - hrefs in links will be replaced with their redirects
    link_redirects: dict
    # Regex to match links that should be ignored
    link_ignore_regex: str
    # Encoding type to use for the input html files and the output csv
    encoding: str

    def __init__(self) -> None:
        self.overlap_window = DEFAULT_WINDOW_OVERLAP
        self.max_len = DEFAULT_MAX_LEN
        self.link_redirects = {}
        self.link_ignore_regex = DEFAULT_LINK_IGNORE_REGEX
        self.encoding = DEFAULT_ENCODING
        self._init_html_to_text()

    def _init_html_to_text(self) -> None:
        # Initialize the HTML2Text object for html parsing
        self.html2text = html2text.HTML2Text()
        self.html2text.ignore_links = True
        self.html2text.ignore_images = True
        self.html2text.ignore_emphasis = True
        self.html2text.skip_internal_links = True
        self.html2text.body_width = 0 # No text wrap
        self.html2text.ul_item_mark = '-'

    ### MAIN PARSING FUNCTIONS 

    def parse_folder(self, dump_configs: list[DumpConfig], out_path: str):
        """
        Processes a directory of website pages (raw html) to prepared documents
        Full web pages are split hierarchically into extracts according to split_attrs
        - dump_configs: list of configurations of the website dump files
        - out_path: filepath to place the output processed files, defaults to the parent of the in_path

        Output files:
        - website_extracts.csv: spreadsheet of page extracts
          CSV column details:
            - doc_id: unique index of the document
            - url: original link corresponding to the document or extract (may include anchor links for extracts)
            - parent: doc_id of the parent document (linked webpage, or parent extract within one page)
            - titles: hierarchy of titles of the document (all titles within the page leading to this extract)
            - text: converted text from document html
            - links: dict of links within the extract, {'title': <text of the link>, 'url': <href of the link>}
            - orig_doc: filepath of the original document that the extract is from
            - last_modified: date that the original document was last modified
            - parent_titles: titles of the parent webpages for the extract
            - Additional columns are added if returned from the DumpConfig.metadata_extractor
        - website_graph.txt: NetworkX graph (adjacency list format) of doc_ids, edges are links between pages
        """
        
        self.doc_index = DocIndex()
        self.graph = nx.DiGraph()
        df_list = []

        for dump_config in dump_configs:
            # Init the document index, queue, and relation graph for this dump
            dump_config.dump_path = os.path.abspath(dump_config.dump_path)
            base_id = self.doc_index.add_doc('base', dump_config.base_url, dump_config.dump_path)
            dump_config.base_url = self.doc_index.get_doc(base_id)['url']
            queue = [(dump_config.dump_path,base_id)]
            self.graph.add_node(base_id)
            df_list.append({'doc_id': base_id, 'url': dump_config.base_url, 'parent': '', 'titles': [], 'parent_titles': [], 'text': '', 'links': {}})

            # Process the dump
            log.info(f'Processing {dump_config.base_url}')
            while queue:
                (path,parent_idx) = queue.pop()
                entries = [os.path.abspath(os.path.join(path, entry)) for entry in listdir(path)]
                files = [entry for entry in entries if os.path.isfile(entry)]
                directories = [entry for entry in entries if not os.path.isfile(entry)]

                for filepath in files:
                    if not filepath.endswith('.html'): 
                        log.debug(f'Ignoring non-html file {filepath}')
                        continue # ignore non html files 

                    url = url_from_filepath(dump_config.dump_path,dump_config.base_url,filepath)
                    log.debug(f' Parsing {url}')
                    dirpath = filepath.replace('.html','')

                    html = ''
                    with open(filepath,'r',encoding=self.encoding) as f:
                        html = f.read() # read raw html of this page

                    try:
                        (idx, extracts) = self.parse_page(html, parent_idx, url, dump_config)
                        extracts = [{**extract, 'orig_doc': filepath, 'last_modified': os.path.getmtime(filepath)} for extract in extracts]
                        df_list.extend(extracts) # add processed document extracts
                        if dirpath in directories: queue.append((dirpath,idx))
                    except Exception as e:
                        log.error(f"Failed to parse page {filepath}: {str(e)}")
                        if dirpath in directories:
                            log.error(f"Also skipping associated directory {dirpath}")

        df = pd.DataFrame.from_dict(df_list)
        df.set_index('doc_id')
        self.handle_links(df)

        log.info('Writing files')
        def writer():
            makedirs(out_path, exist_ok=True)
            df.to_csv(os.path.join(out_path,"website_extracts.csv"),encoding=self.encoding)    # save pages to csv
            nx.write_multiline_adjlist(self.graph,os.path.join(out_path,"website_graph.txt"))    # save page graph to file

        try:
            tools.write_file(writer)
            log.info(' Wrote files "website_extracts.csv" and "website_graph.txt"')
        except:
            log.error(" Didn't save the parsed document files")
        log.info(' Document parsing complete')

    def parse_page(self, html: str, parent_idx: int, url: str, dump_config: DumpConfig) -> Tuple[int,list[dict]]:
        """
        Converts html page from the calendar to the processed documents, 
        adds documents to the DocIndex, and adds document relations to the graph
        - html: raw html for the page
        - parent_idx: doc_id of the parent page
        - url: academic calendar url of the page
        Returns: tuple (idx,extracts) containing the base idx for the page, and the page's extracts
        """
        soup = make_soup(html)
        parent_titles = self.doc_index.get_doc(parent_idx)['parent_titles']
        if title := soup.find(**dump_config.title_attrs):
            if not parent_titles: parent_titles = []
            parent_titles = [*parent_titles,title.text.strip()]
        soup = self.preprocess(soup, url, dump_config)
        extracts = self.split_page_by_tag(soup, 0, dump_config)

        docs = self.handle_extracts(extracts, url, parent_idx, [], parent_titles, '', dump_config, root_level = True)
        base_idx = docs[0]['doc_id']
        return (base_idx,docs)
    
    def preprocess(self, soup: BeautifulSoup, url: str, dump_config: DumpConfig) -> BeautifulSoup:
        """
        Applies any preprocessing steps to the BeautifulSoup for the page, 
        and returns the processed soup
        """
        # Skip to the main content, if attributes are provided
        mainContent = soup
        if dump_config.main_content_attrs: 
            if tag := soup.find(**dump_config.main_content_attrs):
                mainContent = tag.extract() 
            else:
                log.warning(f'No main content found for page {url}')

        # Remove tags matching the attributes in remove_tag_attrs
        for tag_attrs in dump_config.remove_tag_attrs:
            tags = mainContent.find_all(**tag_attrs)
            for tag in tags: tag.decompose()

        # Apply replacement functions
        for (tag_attrs, replacement_fn) in dump_config.replacements:
            tag = mainContent.find(**tag_attrs)
            while tag:
                replacement = replacement_fn(tag, url)
                tag.replace_with(replacement)
                tag = replacement.find_next(**tag_attrs)

        return mainContent

    def handle_links(self, df) -> None:
        """
        Given the dataframe of docs including links, identify the doc_id for internal links and
        add an edge betweeen the pages in the page graph. 
        Converts links to their redirect link as specified in redirect_map.
        df: dataframe of processed documents
        """
        log.debug('Converting links')
        for row in tqdm(df.loc[:,['url','links']].itertuples()):
            doc_id = row.Index
            to_remove = []
            for (title,href) in row.links.items():
                linked_doc_idx = None
                if type(href) == int:
                    # href is already converted to doc id
                    linked_doc_idx = href
                elif re.match(self.link_ignore_regex, href):
                    # link should be ignored
                    to_remove.append(title)
                else:
                    url = make_absolute_url(row.url,href)
                    url_split = url.split('#') # split off anchor tag
                    if url_split[0] in self.link_redirects: url_split[0] = self.link_redirects[url_split[0]]
                    url = '#'.join(url_split)
                    linked_doc_idx = self.doc_index.doc_url_to_idx(url)
                    if linked_doc_idx: 
                        add_page_relation(self.graph,doc_id,linked_doc_idx,DocRelation.LINK)
                        df.at[doc_id,'links'][title] = (url,linked_doc_idx)
                    else:
                        df.at[doc_id,'links'][title] = (url,None)

            for link_title in to_remove: df.at[doc_id,'links'].pop(link_title)
            
        log.debug('Finished converting links')

    ### PAGE SPLITTING

    def split_sent(self, sent) -> list[str]:
        """
        Splits an oversize sentence (greater than max document length) into sections
        by word boundary.
        """
        extracts = ['']
        tokens = ['']

        # Combine tokens that don't have whitespace between them
        for token in sent:
            tokens[-1] += token.text
            if token.whitespace_ == ' ':
                tokens.append('')

        for token in tokens:
            if len(extracts[-1]) + len(token) > self.max_len:
                extracts.append(token)
            else:
                extracts[-1] += ' ' + token
        return extracts

    def split_extract_by_sentence(self, text) -> list[str]:
        """
        Splits an oversize extract (greater than max document length) into sections
        by sentence boundary (and word boundary if the sentences are too long)
        """
        extracts = ['']
        doc = nlp(text)
        for sent in doc.sents:
            sentlen = len(sent.text)
            if sentlen > self.max_len:
                splits = self.split_sent(sent)
                extracts.extend(splits)
            elif len(extracts[-1]) + sentlen > self.max_len:
                extracts.append(sent.text)
            else:
                extracts[-1] += ' ' + sent.text
        return extracts

    def split_page_by_tag(self, soup_orig, split_tag_index: int, dump_config: DumpConfig) -> list[dict]:
        """
        Splits page by the tags specified by split_attrs, hierarchically, into extracts
        - soup_orig: the BeautifulSoup object for the page to be split. The object will be copied, not modified.
        - split_tag_index: index of the split_attrs list to begin splitting the document on
        """
        
        if (split_tag_index > dump_config.mandatory_splits and len(self.html_to_text(soup_orig)) <= self.max_len) or split_tag_index >= len(dump_config.split_attrs):
            # if document is already below the maximum length, and all mandatory splits completed, return extract 
            # or there are no more tags to split on
            return [{
                'titles': [],
                'html': soup_orig,
                'anchor_link': None,
                'links': {link.text: link['href'] for link in soup_orig.find_all('a') if link.has_attr('href')},
                'children': []}]

        matching_tags = None 
        if 'function' in dump_config.split_attrs[split_tag_index]:
            matching_tags = soup_orig.find_all(dump_config.split_attrs[split_tag_index]['function'])
        else:
            matching_tags = soup_orig.find_all(**dump_config.split_attrs[split_tag_index])

        if len(matching_tags) == 0:
            # Extract doesn't contain current split tag, move to next tag
            return self.split_page_by_tag(soup_orig, split_tag_index+1, dump_config)

        extracts = []
        soup = make_soup(str(soup_orig)) # duplicate the page's BeautifulSoup object
        soup_current = soup # current element while walking the soup object
        extract = generic_soup.new_tag("div")
        extract_current = extract # current element while walking the extract soup object
        extract_links = {} # stores list of links within the extract
        current_title = '' # title of the current extract
        current_title_idx = 1
        current_anchor_link = None
        next_anchor_link = None
        while soup_current and extract_current:
            if soup_current in matching_tags and not(dump_config.ignore_empty_split_tags and soup_current.text.strip() == ''):
                self.add_extract(extracts, extract, current_title, current_anchor_link, extract_links, split_tag_index, dump_config)
                (extract,extract_current) = parent_skeleton(extract_current)
                
                if split_tag_index in dump_config.no_title_splits:
                    # Don't take the title from this tag as specified by the dump config
                    current_title = current_title_idx
                    current_title_idx += 1
                else:
                    current_title = soup_current.text.strip().replace('\n','')
                    
                extract_links = {}
                current_anchor_link = next_anchor_link
                next_anchor_link = None
                
                # Remove the title text from the soup
                for content in soup_current.contents:
                    content.extract()
                    
            if soup_current.name == 'a':
                if soup_current.has_attr('href'):
                    # Add link to extract links
                    extract_links[soup_current.text.strip()] = soup_current['href']
                elif soup_current.has_attr('id'):
                    # Link is anchor link
                    next_anchor_link = soup_current['id']
                elif soup_current.has_attr('name'):
                    # Link is anchor link
                    next_anchor_link = soup_current['name']
            if hasattr(soup_current,'contents') and len(soup_current.contents) > 0:
                # Move to child element
                child = soup_current.contents[0]
                attrs = soup_current.attrs
                if 'name' in attrs: attrs.pop('name')
                elem = generic_soup.new_tag(soup_current.name,**attrs)
                extract_current.append(elem)
                extract_current = elem
                soup_current = child
            elif sibling := soup_current.next_sibling:
                # No child, move to sibling element
                elem = soup_current.extract()
                extract_current.append(elem)
                soup_current = sibling
            else:
                # No child or sibling, move to parent
                parent = soup_current.parent
                elem = soup_current.extract()
                extract_current.append(elem)
                soup_current = parent
                while soup_current and not soup_current.next_sibling and extract_current.parent: 
                    parent = soup_current.parent
                    soup_current.decompose()
                    soup_current = parent
                    extract_current = extract_current.parent
                if soup_current:
                    soup_current = soup_current.next_sibling
                    extract_current = extract_current.parent
        
        # Add the remainder of the current extract
        self.add_extract(extracts, extract, current_title, current_anchor_link, extract_links, split_tag_index, dump_config)
        return extracts

    def add_extract(self, extracts: list[dict], extract: BeautifulSoup, title: str, anchor_link: str, 
                    extract_links: dict, split_tag_index: int, dump_config: DumpConfig) -> None:
        """
        Helper function for split_page: finds sub-extracts for the given extract, and adds result
        to the extracts list
        """
        children = self.split_page_by_tag(extract, split_tag_index+1, dump_config)
        extracts.append({
            'title': title,
            'html': extract,
            'anchor_link': anchor_link,
            'links': extract_links,
            'children': children if len(children) > 1 else []})
        
    def handle_extracts(self, extracts: list[dict], url: str, parent_idx: int, titles: list[str], 
                        parent_titles: list[str], parent_context: str, dump_config: DumpConfig, root_level = False) -> list[dict]:
        """
        Convert the page extracts to document dicts, add documents to the DocIndex, and add parent
        relations to the graph. Further splits the plain text of documents if they are too long.
        - extracts: List of extracts returned from split_page
        - url: base url of the page
        - parent_idx: index of the parent page
        - titles: list of titles within the page, leading to the current extract
        - parent_titles: titles of parent pages in the original site structure
        - parent_context: context from the parent extract to include with this extract
        - dump_config: DumpConfig for the current site dump
        - root_level: True if the given list of extracts is at the root level of a website (top of the split hierarchy)
        """
        docs = []
        previous_sib_id = None
        for extract in extracts:
            if len(extract['children']) > 0:
                # This extract has a child for an intro section
                first_child = extract['children'][0]
                if first_child['title'] == '' and len(first_child['children']) == 0:
                    # Combine the initial intro document with this one
                    extract['html'] = first_child['html']
                    extract['links'] = first_child['links']
                    extract['children'].remove(first_child)
                else:
                    if first_child['title'] == '': first_child['title'] = 'Intro'
                    # All content in this extract is covered by children, remove content
                    extract['html'] = None
                    extract['links'] = {}
                
            if extract['anchor_link'] is not None:
                url = re.sub(r'#.+\Z','',url) # remove existing anchor
                url = f'{url}#{extract["anchor_link"]}' # add new anchor

            extract_titles = [*titles,extract["title"]]
            text = self.html_to_text(extract['html'])
            if text.strip() == '' and len(extract['children']) == 0:
                continue # skip empty extract with no children

            first_page_idx = None
            split_texts = self.split_extract_by_sentence(text) if len(text) > self.max_len else [text]
            for split_idx, text in enumerate(split_texts):
                links = extract['links']
                if len(split_texts) > 1:
                    links = {title:href for (title,href) in extract['links'].items() if title in text}

                idx = self.doc_index.add_doc(extract_titles,url,parent_titles=parent_titles)
                if not first_page_idx: first_page_idx = idx # keep the index of the first page in the split texts
                
                if root_level:
                    add_page_relation(self.graph, parent_idx, idx, DocRelation.PARENT_PAGE) # add edge from parent page to this page
                else:
                    add_page_relation(self.graph, parent_idx, idx, DocRelation.PARENT_EXTRACT) # add edge from parent extract to this page
                    
                if previous_sib_id:
                    # add edge from previous sibling to this page
                    relation = DocRelation.SIBLING_SPLIT_EXTRACT if split_idx > 0 else DocRelation.SIBLING_EXTRACT
                    add_page_relation(self.graph, previous_sib_id, idx, relation) 

                docs.append({
                    'doc_id': idx, 
                    'url': url, 
                    'parent': parent_idx, 
                    'titles': extract_titles, 
                    'text': text, 
                    'links': links,
                    'parent_titles': parent_titles,
                    'context': parent_context,
                    'split_idx': split_idx,
                    **dump_config.metadata_extractor(url,extract_titles,parent_titles,text)})
                previous_sib_id = idx

            parent_context = ''
            if dump_config.parent_context_extractor:
                parent_context = dump_config.parent_context_extractor(url,titles,parent_titles,text)

            docs.extend(self.handle_extracts(extract['children'],url,first_page_idx,extract_titles,parent_titles,parent_context,dump_config))
        return docs
    
    def html_to_text(self, html: BeautifulSoup) -> str:
        """
        Convert BeautifulSoup object to text
        """
        if not html: return ''
        for sup in html.find_all('sup'):
            # Replace superscripts with square brackets
            if sup.string and sup.string.isdigit():
                replacement = make_tag('div',['[',sup.string,']'])
                sup.replace_with(replacement)
        result = self.html2text.handle(str(html))
        result = result.replace('<[document]>','')
        result = re.sub('\n{2,}','\n\n',result) # Replace any sequence of more than 2 newlines with just 2
        result = re.sub('(?<=\w)\n(?=\w)',' ',result) # Replace in-paragraph linebreaks with a space
        result = re.sub('#+','',result) # Remove heading identifiers
        return result

### UTILITY FUNCTIONS

def make_tag(tag, content = None, attrs = {}):
    """
    Make a new BeautifulSoup tag with the given contents
    """
    tag = generic_soup.new_tag(tag, **attrs)
    if content: 
        if isinstance(content, list): tag.extend(content)
        else: tag.append(content)
    return tag

def parent_skeleton(elem):
    """
    Returns the skeleton structure of all parent tags for the soup element,
    including the current element
    """
    skeleton = generic_soup.new_tag(elem.name,**elem.attrs)
    bottom_elem = skeleton
    for parent in elem.parents:
        new_skeleton = generic_soup.new_tag(parent.name,**parent.attrs)
        new_skeleton.append(skeleton)
        skeleton = new_skeleton
    return (skeleton,bottom_elem)

def url_from_filepath(base_path: str, base_url: str, filepath: str) -> str:
    """
    Get the vancouver calendar url for a given filepath
    from a calendar dump directory
    - base_path: filepath of the root of the calendar dump
    - base_url: url corresponding to the root of the calendar dump
    - filepath: path to convert to url
    """
    return '/'.join(filepath.replace(base_path,base_url).replace('.html','').split(sep))

def add_page_relation(G, idx_1: int, idx_2: int, relation: DocRelation):
    """
    Adds a directed link between two pages in the graph
    G: NetworkX graph
    idx_1: page 1 index
    idx_2: page 2 index
    type: DocRelation from page 1 to page 2
    """
    G.add_edge(idx_1, idx_2, type=int(relation))

def print_doc_structure(docs: list[dict], level = 0):
    """
    Function for development & debug: recursively displays the titles and 
    anchor links discovered by split_page
    - docs: list of extracts outputted from split_page
    - level: current indent level, defaults to 0 for the top of the hierarchy
    """
    indent = ''.join(['  ' for i in range(level)])
    for doc in docs:
        print(f'{indent}- {doc["title"]} #{doc["anchor_link"]}')
        print_doc_structure(doc['children'],level+1)
    
def make_soup(html):
    """
    Get the BeautifulSoup object for the given raw html string
    """
    return BeautifulSoup(html, "html.parser")

def make_absolute_url(base_url, href):
    """
    Returns the absolute url
    If url is relative, combines it with the base url
    """
    if '//' in href: return href
    return clean_url(urljoin(base_url,href))

def clean_url(url):
    """
    Cleans url to a standard format
    """
    url = url.replace('http://','https://').replace('.html','').replace('#top','')
    if url[-1] == '/': url = url[:-1]
    return url