# logger.py
import logging
import os
import config

def setup_logger():
    """Configures and returns a centralized logger for the application."""
    log_file_path = os.path.join(config.BASE_DIR, 'adawriter.log')

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler() # Also print to console
        ]
    )
    
    return logging.getLogger(__name__)