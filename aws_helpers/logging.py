import logging

def set_boto_log_levels(log_level):
    """
    Set the log level for all boto functions
    """
    for name in ['boto', 'urllib3', 's3transfer', 'boto3', 'botocore', 'nose']:
        logging.getLogger(name).setLevel(log_level)
        