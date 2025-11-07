import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === Environment Configuration ===
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")  # development, staging, production

# === Server Configuration ===
SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8060"))
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

# === CORS Configuration ===
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3060,http://127.0.0.1:3060").split(",")
# Example: "http://localhost:3060,http://127.0.0.1:3060,http://localhost:3000,https://yourdomain.com"

# === Database Configuration ===
MONGODB_URI = os.environ.get("MONGODB_URI")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "travel_planer")

# === Google OAuth Configuration ===
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:3060/auth/callback")
# Google OAuth URLs (rarely change, but configurable if needed)
GOOGLE_TOKEN_URL = os.environ.get("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")
GOOGLE_USERINFO_URL = os.environ.get("GOOGLE_USERINFO_URL", "https://www.googleapis.com/oauth2/v2/userinfo")

# === JWT Configuration ===
JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-this-in-production")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.environ.get("JWT_EXPIRATION_HOURS", "24"))

# === AI/LLM API Keys ===
# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")

# Google AI
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# LangChain/LangSmith
LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY")
LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGCHAIN_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "travel-planer")

# === Application Settings ===
APP_NAME = "Travel Planer API"
APP_VERSION = "1.0.0"