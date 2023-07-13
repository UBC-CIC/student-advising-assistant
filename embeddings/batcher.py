from typing import Callable, List, Any
from tqdm import tqdm

# Batching code adapted from https://github.com/hwchase17/langchain/blob/master/langchain/retrievers/pinecone_hybrid_search.py

def perform_batches(operation: Callable, batch_size: int, args: List[List[Any]], verbose=False):
    """
    Performs a function that takes list arguments, splitting the list arguments
    into batches
    - operation: function to perform on batches
    - batch_size: number of items per batch
    - args: list of lists to split by batch size
            requires all lists to be the same length
    - verbose: If true, prints progress of batches
    """
    if len(args) < 1:
        raise Exception('perform_batches needs at least one argument to batch')
    
    n = len(args[0])
    _iterator = range(0, n, batch_size)
    
    if verbose: _iterator = tqdm(_iterator)
    
    for i in _iterator:
        # find end of batch
        i_end = min(i + batch_size, n)
        
        # extract batch arguments
        batch_args = [arg[i:i_end] for arg in args]
        
        # perform batch operation
        operation(*batch_args)