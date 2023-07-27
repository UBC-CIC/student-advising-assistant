from langchain.retrievers.document_compressors import LLMChainFilter
from typing import Optional, Sequence, Tuple
from langchain.schema import Document
from langchain.callbacks.manager import Callbacks
from langchain import LLMChain

class VerboseFilter(LLMChainFilter):
    """
    Filter that uses an LLM to drop documents that aren't relevant to the query.
    Returns the list of relevant documents, and the irrelevant documents.
    Adds metadata with an explanation for why the LLM thinks they are 
    relevant/irrelevant, if provided.
    """
    
    reason_metadata_key: str = 'keep_reason'
    
    llm_chain: LLMChain
    """LLM wrapper to use for filtering documents. 
    The chain prompt is expected to parse output to a tuple of Boolean, String
    Where the Boolean value indicates if the document should be returned,
    and the String value contains any justification for the decision."""
    
    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Optional[Callbacks] = None,
    ) -> Tuple[Sequence[Document],Sequence[Document]]:
        """Filter down documents based on their relevance to the query."""
        filtered_docs = []
        removed_docs = []
        for doc in documents:
            _input = self.get_input(query, doc)
            include_doc, reason = self.llm_chain.predict_and_parse(
                **_input, callbacks=callbacks
            )
            doc.metadata[self.reason_metadata_key] = reason
            if include_doc:
                filtered_docs.append(doc)
            else:
                removed_docs.append(doc)
        return filtered_docs, removed_docs