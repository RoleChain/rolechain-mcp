import logging

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a handler to log to a file
fh = logging.FileHandler("app.log")
fh.setLevel(logging.INFO)


# Create a logging format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(fh)