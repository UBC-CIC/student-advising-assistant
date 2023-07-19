from typing import Callable
import os

"""
Tools used by various document scraping scripts
"""

def write_file(writer: Callable):
    """
    Calls a file writing callback, and upon an error, gives
    the user the opportunity to try saving again.
    """
    response = 'y'
    while(response == 'y'):
        try:
           writer()
           return
        except Exception as e:
            print(f"Unable to write to file: {str(e)}")
            print("Could not save the files. Make sure the files to write are not open.")
            response = input("Try saving files again? <y,n> ")