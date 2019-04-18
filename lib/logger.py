import logging

# Create a custom logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create handlers
stream_handler = logging.StreamHandler()

# Create formatters and add it to handlers
stream_format = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
stream_handler.setFormatter(stream_format)

# Add handlers to the logger
logger.addHandler(stream_handler)
