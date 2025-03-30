import os

# API Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Database Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///ferry_data.db")

# Default data file path
DEFAULT_DATA_PATH = "attached_assets/GTFS_data_v5.json"

# Maximum conversation history to maintain
MAX_CONVERSATION_HISTORY = 10

# Agent configuration
AGENT_VERBOSE = True
AGENT_TEMPERATURE = 0.1

# Model configuration
MODEL_NAME = "gemini-1.5-flash"
