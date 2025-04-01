"""Configuration settings for the ferry application."""
import os

# Flask configuration
SECRET_KEY = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Database configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///gtfs.db")

# Gemini API configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-1.5-pro")
AGENT_TEMPERATURE = float(os.environ.get("AGENT_TEMPERATURE", "0.2"))

# Data file paths
DEFAULT_DATA_PATH = os.environ.get("FERRY_DATA_PATH", "attached_assets/GTFS_data_v5.json")
HISTORICAL_DATA_PATH = os.environ.get("HISTORICAL_DATA_PATH", "attached_assets/GTFS appear dates.json")

# Misc settings
DEBUG = bool(os.environ.get("DEBUG", "True") == "True")