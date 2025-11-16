import os
import re

from dotenv import find_dotenv, load_dotenv


# Load environment variables with .env, .env.dev/.env.prod support
def _load_env_files() -> None:
    """
    Load .env files with this precedence:
    1) Base .env (if present)
    2) Explicit file via ENV_FILE (e.g., .env.dev or ./config/.env.prod)
    3) Environment-specific file inferred from ENVIRONMENT/ENV/PYTHON_ENV
        - Supports aliases like dev/development, prod/production, stage/staging
    Note: Existing OS environment variables are never overridden.
    """
    # 1) Base .env
    base_path = find_dotenv(".env", usecwd=True)
    if base_path:
        load_dotenv(base_path, override=False)

    # 2) Explicit file via ENV_FILE
    explicit = os.environ.get("ENV_FILE")
    if explicit:
        explicit_path = explicit if os.path.isabs(explicit) else find_dotenv(explicit, usecwd=True)
        if explicit_path:
            load_dotenv(explicit_path, override=False)
            return

    # 3) Environment-specific file inferred from ENVIRONMENT/ENV/PYTHON_ENV
    env_name = (
        os.environ.get("ENVIRONMENT") or os.environ.get("ENV") or os.environ.get("PYTHON_ENV")
    )
    if env_name:
        slug = str(env_name).strip().lower()
        alias = {
            "dev": "development",
            "prod": "production",
            "stg": "staging",
            "test": "test",
        }
        resolved = alias.get(slug, slug)
        for candidate in (f".env.{resolved}", f".env.{slug}"):
            path = find_dotenv(candidate, usecwd=True)
            if path:
                load_dotenv(path, override=False)
                break


_load_env_files()

# === Environment Configuration ===
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")  # development, staging, production

# === Server Configuration ===
SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")


def _get_int_env(var_name: str, default_value: int) -> int:
    """
    Parse an integer environment variable robustly.
    - Trims whitespace and trailing semicolons.
    - Falls back to the first integer found in the string.
    - Returns the provided default if parsing fails.
    """
    raw = os.environ.get(var_name, str(default_value))
    text = str(raw).strip().rstrip(";")
    try:
        return int(text)
    except Exception:
        match = re.search(r"[-+]?\d+", text or "")
        if match:
            try:
                return int(match.group(0))
            except Exception:
                pass
    return int(default_value)


SERVER_PORT = _get_int_env("SERVER_PORT", 8060)
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

# === CORS Configuration ===
CORS_ORIGINS = os.environ.get("CORS_ORIGINS").split(",")
# Example: "http://localhost:3060,http://127.0.0.1:3060,http://localhost:3000,https://yourdomain.com"

# === Database Configuration ===
MONGODB_URI = os.environ.get("MONGODB_URI")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "travel_planner")

# === Google OAuth Configuration ===
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
# Google OAuth URLs (rarely change, but configurable if needed)
GOOGLE_TOKEN_URL = os.environ.get("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")
GOOGLE_USERINFO_URL = os.environ.get(
    "GOOGLE_USERINFO_URL", "https://www.googleapis.com/oauth2/v2/userinfo"
)

# === JWT Configuration ===
JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-this-in-production")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = _get_int_env("JWT_EXPIRATION_HOURS", 24)

# === AI/LLM API Keys ===
# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")

# Google AI
GOOGLE_AI_API_KEY = os.environ.get("GOOGLE_AI_API_KEY")
GOOGLE_AI_MODEL = "gemini-2.5-flash"

# LangChain/LangSmith
LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY")
LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGCHAIN_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "travel-planner")

# === Application Settings ===
APP_NAME = "Travel Planner API"
APP_VERSION = "1.0.0"
