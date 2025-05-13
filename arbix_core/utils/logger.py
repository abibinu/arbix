import logging
import logging.config
import json
import os

def setup_logging(
    default_path='config/logging_config.json',
    default_level=logging.INFO,
    env_key='LOG_CFG'
):
    """Setup logging configuration"""
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            try:
                config = json.load(f)
                logging.config.dictConfig(config)
                logging.info("Logging configured successfully from file.")
            except json.JSONDecodeError as e:
                logging.basicConfig(level=default_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                logging.error(f"Error loading logging_config.json: {e}. Using basicConfig.")
            except Exception as e:
                logging.basicConfig(level=default_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                logging.error(f"An unexpected error occurred while configuring logging from file: {e}. Using basicConfig.")

    else:
        logging.basicConfig(level=default_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logging.info("logging_config.json not found. Using basicConfig.")

# Example usage (you can call this from main.py)
# if __name__ == '__main__':
#     setup_logging()
#     logger = logging.getLogger(__name__)
#     logger.info("This is an info message from logger.py.")
#     logger.error("This is an error message from logger.py.")