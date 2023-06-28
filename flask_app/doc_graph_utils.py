from typing import List
import networkx as nx
from enum import IntEnum

GRAPH_FILEPATH = './data/website_graph.txt'

class DocRelation(IntEnum):
    """
    Represents the possible relationships between documents
    """
    PARENT = 1
    LINK = 2
    SIBLING_EXTRACT = 3
    SIBLING_SPLIT_EXTRACT = 4

def read_graph() -> nx.DiGraph:
    """
    Read the website relationship graph from file
    """
    graph = nx.read_multiline_adjlist(GRAPH_FILEPATH, create_using=nx.DiGraph, nodetype = int)
    return graph 

def get_doc_relation_ids(graph: nx.DiGraph, doc_id: int, relation: DocRelation, in_only = False, out_only = False, only_one=False) -> List[int]:
    """
    Return the ids of documents related to the given document by the given relation
    """
    out_ids = []
    if not out_only:
        for (id2,_,data) in list(graph.in_edges([doc_id],data=True)):
            if data['type'] == int(relation):
                out_ids.append(id2)
    if not in_only: 
        for (_,id2,data) in list(graph.out_edges([doc_id],data=True)):
            if data['type'] == int(relation):
                out_ids.append(id2)

    if only_one:
        if len(out_ids) == 1: 
            return out_ids[0]
        else: return None
    else: return out_ids

def get_split_sib_ids(graph: nx.DiGraph, doc_id: int):
    ids = []
    prev_sib = get_doc_relation_ids(graph, doc_id, DocRelation.SIBLING_SPLIT_EXTRACT, in_only=True, only_one=True)
    while prev_sib:
        ids.insert(0,prev_sib)
        prev_sib = get_doc_relation_ids(graph, prev_sib, DocRelation.SIBLING_SPLIT_EXTRACT, in_only=True, only_one=True)
    
    ids.append(doc_id)

    next_sib = get_doc_relation_ids(graph, doc_id, DocRelation.SIBLING_SPLIT_EXTRACT, out_only=True, only_one=True)
    while next_sib:
        ids.append(next_sib)
        next_sib = get_doc_relation_ids(graph, next_sib, DocRelation.SIBLING_SPLIT_EXTRACT, out_only=True, only_one=True)
    
    return ids

def get_doc_sib_ids(graph: nx.DiGraph, doc_id: int) -> List[int]:
    """
    Return the ids of the given document's previous and next sibling documents
    (One or both may not exist)
    """
    return get_doc_relation_ids(graph,doc_id,DocRelation.SIBLING_EXTRACT)

def get_doc_child_ids(graph: nx.DiGraph, doc_id: int) -> List[int]:
    """
    Return the ids of the given document's child documents
    """
    return get_doc_relation_ids(graph,doc_id,DocRelation.PARENT, out_only=True)

