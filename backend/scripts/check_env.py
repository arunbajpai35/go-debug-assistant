# scripts/check_env.py
import os
from dotenv import load_dotenv

load_dotenv()

print("TOGETHER_API_KEY:", os.getenv("TOGETHER_API_KEY"))
