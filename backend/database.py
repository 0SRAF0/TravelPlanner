"""
MongoDB Database Configuration and Connection
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = "travel_planer"

# Global database client
_client = None
_database = None


def get_database():
    """
    Get MongoDB database instance
    Creates a new connection if one doesn't exist
    """
    global _client, _database
    
    if _database is None:
        if not MONGODB_URI:
            raise ValueError("MONGODB_URI environment variable is not set")
        
        # Create MongoDB client with server API version
        _client = AsyncIOMotorClient(
            MONGODB_URI,
            server_api=ServerApi('1')
        )
        _database = _client[DATABASE_NAME]
        
        print(f"✅ Connected to MongoDB database: {DATABASE_NAME}")
    
    return _database


def get_users_collection():
    """
    Get the users collection from the database
    """
    db = get_database()
    return db.users


async def init_indexes():
    """
    Initialize database indexes for better query performance
    """
    try:
        users_collection = get_users_collection()
        
        # Create unique index on google_id
        await users_collection.create_index("google_id", unique=True)
        
        # Create index on email for faster lookups
        await users_collection.create_index("email")
        
        print("✅ Database indexes created successfully")
    except Exception as e:
        print(f"⚠️  Index creation warning: {e}")


async def close_database_connection():
    """
    Close the MongoDB connection
    Call this when shutting down the application
    """
    global _client, _database
    
    if _client:
        _client.close()
        _client = None
        _database = None
        print("🔌 Closed MongoDB connection")


async def test_connection():
    """
    Test the MongoDB connection
    """
    try:
        db = get_database()
        # Ping the database
        await db.command('ping')
        print("✅ MongoDB connection successful!")
        return True
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return False

