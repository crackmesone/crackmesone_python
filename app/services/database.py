"""
Database service for MongoDB connection.
"""

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Global database client and database reference
mongo_client = None
db = None


def init_db(app, config):
    """Initialize database connection."""
    global mongo_client, db

    try:
        mongo_url = config['MongoDB'].get('URL', 'mongodb://127.0.0.1:27017')
        database_name = config['MongoDB'].get('Database', 'crackmes')

        mongo_client = MongoClient(mongo_url)
        # Verify connection
        mongo_client.admin.command('ping')

        db = mongo_client[database_name]
        app.config['MONGO_CLIENT'] = mongo_client
        app.config['MONGO_DB'] = db

        print(f"Connected to MongoDB: {database_name}")
    except ConnectionFailure as e:
        print(f"MongoDB connection failed: {e}")
        raise


def get_db():
    """Get the database instance."""
    global db
    return db


def get_collection(name):
    """Get a collection by name."""
    global db
    if db is None:
        raise RuntimeError("Database not initialized")
    return db[name]


def check_connection():
    """Check if database connection is available."""
    global mongo_client
    if mongo_client is None:
        return False
    try:
        mongo_client.admin.command('ping')
        return True
    except ConnectionFailure:
        return False
