import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PROMPTS_DIR = Path(__file__).parent / "prompts"

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
STUB_MODE = os.getenv("DISASTERLENS_STUB", "0") == "1"
JUDGE_ENABLED = os.getenv("DISASTERLENS_JUDGE", "1") == "1"
JUDGE_TIMEOUT = float(os.getenv("DISASTERLENS_JUDGE_TIMEOUT", "5"))

MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))
REQUEST_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))  # seconds
# Wall-clock budget for ONE report, retries included; this is what bounds POST /reports.
TOTAL_TIMEOUT = float(os.getenv("LLM_TOTAL_BUDGET", str(REQUEST_TIMEOUT * (MAX_RETRIES + 1))))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "900"))
DUPLICATE_THRESHOLD = 0.55
JUDGE_LOW = 0.35
DUP_NEAR_KM = 0.3
DUP_FAR_KM = 3.0
DUP_HARD_CUTOFF_KM = 5.0
DUP_WINDOW_HOURS = 24
# Geo-near LLM judge for cross-language duplicates with zero token overlap
DUP_JUDGE_NEAR_KM = 1.0
DUP_JUDGE_MAX_CANDIDATES = 2
