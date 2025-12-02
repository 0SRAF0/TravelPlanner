"""
MongoDB Database Configuration and Connection
"""

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi

from app.core.config import DATABASE_NAME, MONGODB_URI

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
        _client = AsyncIOMotorClient(MONGODB_URI, server_api=ServerApi("1"))
        _database = _client[DATABASE_NAME]

        print(f"✅ Connected to MongoDB database: {DATABASE_NAME}")

    return _database


async def init_indexes():
    """
    Initialize database indexes for better query performance
    """
    try:
        users_collection = get_users_collection()
        preferences_collection = get_preferences_collection()
        activities_collection = get_activities_collection()
        trips_collection = get_trips_collection()
        itineraries_collection = get_itineraries_collection()

        # Users indexes
        await users_collection.create_index("google_id", unique=True)
        await users_collection.create_index("email")

        # Preferences indexes
        await preferences_collection.create_index(
            [("trip_id", 1), ("user_id", 1)], unique=True, name="uniq_trip_user"
        )
        await preferences_collection.create_index("user_id")
        await preferences_collection.create_index("trip_id")

        # Activities indexes
        await activities_collection.create_index("trip_id")
        await activities_collection.create_index("category")

        # Trips indexes
        await trips_collection.create_index("trip_code", unique=True)
        await trips_collection.create_index("creator_id")
        await trips_collection.create_index("members")

        # Itineraries indexes
        await itineraries_collection.create_index([("trip_id", 1), ("is_current", -1), ("version", -1)], name="trip_current_version")
        await itineraries_collection.create_index([("trip_id", 1), ("status", 1)], name="trip_status")
        await itineraries_collection.create_index([("trip_id", 1), ("days.date", 1)], name="trip_day_date")

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
        await db.command("ping")
        print("✅ MongoDB connection successful!")
        return True
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return False


def get_users_collection():
    """
    Get the users collection from the database
    """
    db = get_database()
    return db.users


def get_preferences_collection():
    """
    Get the preferences collection from the database
    """
    db = get_database()
    return db.preferences


def get_activities_collection():
    """
    Get the activities collection from the database
    """
    db = get_database()
    return db.activities


def get_trips_collection():
    """
    Get the trips collection from the database
    """
    db = get_database()
    return db.trips


def get_itineraries_collection():
    """
    Get the itineraries collection from the database
    """
    db = get_database()
    return db.itineraries
