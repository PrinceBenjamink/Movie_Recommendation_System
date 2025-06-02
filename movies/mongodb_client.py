"""MongoDB client for the movies app"""
import logging
import os
from pymongo import MongoClient
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    # Get MongoDB connection string from settings or environment
    MONGODB_URI = getattr(settings, 'MONGODB_URI', os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/'))
    
    # Create a MongoDB client
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    
    # Test the connection
    client.admin.command('ping')
    
    # Get the database
    db = client.get_database('movie_recommender')
    
    # Get collections
    watchlists_collection = db.get_collection('watchlists')
    viewed_movies_collection = db.get_collection('viewed_movies')
    search_history_collection = db.get_collection('search_history')
    
    # Create indexes for better performance
    watchlists_collection.create_index([('user_id', 1), ('movie_id', 1)], unique=True)
    viewed_movies_collection.create_index([('user_id', 1), ('movie_id', 1)], unique=True)
    search_history_collection.create_index([('user_id', 1), ('timestamp', -1)])
    
    logger.info("MongoDB connection established successfully")
except Exception as e:
    logger.error(f"Error connecting to MongoDB: {e}")
    
    # Create fallback collections that log errors but don't crash the app
    class FallbackCollection:
        def __init__(self, name):
            self.name = name
            
        def find(self, *args, **kwargs):
            logger.error(f"MongoDB error: Cannot query {self.name} collection")
            return []
            
        def update_one(self, *args, **kwargs):
            logger.error(f"MongoDB error: Cannot update {self.name} collection")
            return None
            
        def delete_one(self, *args, **kwargs):
            logger.error(f"MongoDB error: Cannot delete from {self.name} collection")
            return None
            
        def create_index(self, *args, **kwargs):
            logger.error(f"MongoDB error: Cannot create index on {self.name} collection")
            return None
            
        def insert_one(self, *args, **kwargs):
            logger.error(f"MongoDB error: Cannot insert into {self.name} collection")
            return None
            
        def count_documents(self, *args, **kwargs):
            logger.error(f"MongoDB error: Cannot count documents in {self.name} collection")
            return 0
    
    watchlists_collection = FallbackCollection('watchlists')
    viewed_movies_collection = FallbackCollection('viewed_movies')
    search_history_collection = FallbackCollection('search_history')



