import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Core Service Configuration
M5_ADMIN_KEY = os.getenv("M5_ADMIN_KEY", "")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", ".")
DEFAULT_ORG_ID = os.getenv("DEFAULT_ORG_ID", "default_org")
DEFAULT_DEPT_ID = os.getenv("DEFAULT_DEPT_ID", "default_dept")
DEFAULT_REPO_ID = os.getenv("DEFAULT_REPO_ID", "default_repo")

# Vector Database Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

# Retrieval Limits
M5_MAX_CHUNKS = int(os.getenv("M5_MAX_CHUNKS", "15"))

