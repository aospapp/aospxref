import os


INDEXER_JAVA_OPTS = os.environ.get("INDEXER_JAVA_OPTS")
CHECK_INDEX = os.environ.get("CHECK_INDEX")
OPENGROK_LOG_LEVEL = os.environ.get("OPENGROK_LOG_LEVEL")
READONLY_CONFIG_FILE = os.environ.get("READONLY_CONFIG_FILE")
TEST_MODE = os.environ.get("TEST_MODE") is not None
