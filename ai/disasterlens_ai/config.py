import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PROMPTS_DIR = Path(__file__).parent / "prompts"

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
STUB_MODE = os.getenv("DISASTERLENS_STUB", "0") == "1"

MAX_RETRIES = 2
DUPLICATE_THRESHOLD = 0.55
