import os
from dotenv import load_dotenv
from configparser import ConfigParser

# Load .env if present
load_dotenv()

# Load fallback config.ini if .env is missing
config = ConfigParser()
config.read("config/config.ini")

# Azure OpenAI config
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT") or config.get("azure_openai", "endpoint", fallback="")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY") or config.get("azure_openai", "api_key", fallback="")
AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL") or config.get("azure_openai", "deployment_name", fallback="gpt-4o-mini")

# Database config
DB_HOST = os.getenv("DB_HOST") or config.get("database", "host", fallback="localhost")
DB_PORT = os.getenv("DB_PORT") or config.get("database", "port", fallback=5432)
DB_USER = os.getenv("DB_USER") or config.get("database", "user", fallback="postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD") or config.get("database", "password", fallback="postgres")
DB_NAME = os.getenv("DB_NAME") or config.get("database", "dbname", fallback="debug_logs")
