from langchain.math_utils import cosine_similarity, cosine_similarity_top_k
from langchain.embeddings.base import Embeddings
from langchain.docstore.document import Document
from typing import List

class Comparator():
    def __init__(self, base_model: Embeddings):
        self.base_model = base_model

    def compare_query_to_title(self, query: str, document: Document, context: str = None):
        """
        Returns the cosine similarity of the given query (or combined context/query, if context is provided)
        to the document's title
        """
        if context: query = f"{context} | {query}"
        query_embed = self.base_model.embed_query(query)
        doc_title_embed = self.document_title_embed(document)
        return cosine_similarity([query_embed],[doc_title_embed])[0][0]
        
    def compare_query_to_document(self, query: str, document: Document, context: str = None):
        """
        Returns the cosine similarity of the query (or combined context/query, if context is provided)
        to the document title and page content
        """
        if context: query = f"{context} | {query}"
        query_embed = self.embed_query(query)
        document_embed = self.embed_document(document)
        return cosine_similarity([query_embed],[document_embed])[0][0]
    
    def compare_query_to_text(self, query: str, text: str, context: str = None):
        """
        Returns the cosine similarity of the query (or combined context/query, if context is provided)
        to a list of generic texts
        """
        if context: query = f"{context} : {query}"
        query_embed = self.base_model.embed_query(query)
        text_embed = self.base_model.embed_documents(text)
        return cosine_similarity([query_embed],[text_embed])[0][0]
    
    def compare_query_to_texts(self, query: str, texts: list[str], context: str = None):
        """
        Returns the cosine similarity of the query (or combined context/query, if context is provided)
        to a list of generic texts
        """
        if context: query = f"{context} : {query}"
        query_embed = self.base_model.embed_query(query)
        text_embeds = self.base_model.embed_documents(texts)
        return cosine_similarity([query_embed],text_embeds)