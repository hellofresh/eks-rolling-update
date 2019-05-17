import logging

# Create a custom logger
logger = logging.getLogger(__name__)

# Create handlers
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)

# Create formatters and add it to handlers
stream_format = '%(asctime)s %(levelname)-8s %(message)s'
stream_handler.setFormatter(stream_format)

# Add handlers to the logger
logger.addHandler(stream_handler)
