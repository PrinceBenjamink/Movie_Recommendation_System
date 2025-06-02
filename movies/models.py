from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
from django.core.cache import cache
from django.conf import settings

# These are Django models that will help with form validation
# The actual data will be stored in MongoDB

class Watchlist(models.Model):
    """Model for watchlist items with improved error handling"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    movie_id = models.IntegerField()
    added_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        # This is just a proxy model - no table will be created
        managed = False
        
    def save(self, *args, **kwargs):
        """Save watchlist item to MongoDB with error handling"""
        try:
            from .mongodb_client import watchlists_collection
            import logging
            logger = logging.getLogger(__name__)
            
            # Ensure movie_id is an integer
            movie_id = int(self.movie_id)
            
            # Convert datetime to a format MongoDB can handle
            added_at = self.added_at
            
            watchlists_collection.update_one(
                {'user_id': self.user.id, 'movie_id': movie_id},
                {'$set': {
                    'user_id': self.user.id,
                    'movie_id': movie_id,
                    'added_at': added_at
                }},
                upsert=True
            )
            
            # Invalidate cache for this user's watchlist
            self._invalidate_cache(self.user.id)
            logger.info(f"Added movie {movie_id} to watchlist for user {self.user.id}")
        except Exception as e:
            logger.error(f"Error saving watchlist item: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    @classmethod
    def get_user_watchlist(cls, user_id):
        """Get watchlist for a user from cache or MongoDB with error handling"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Try to get from cache first
            cache_key = f"user_watchlist_{user_id}"
            watchlist = cache.get(cache_key)
            
            if watchlist is None:
                logger.info(f"Cache miss for user {user_id} watchlist")
                # Not in cache, get from MongoDB
                from .mongodb_client import watchlists_collection
                
                watchlist = list(watchlists_collection.find(
                    {'user_id': user_id}
                ).sort('added_at', -1))
                
                logger.info(f"Retrieved {len(watchlist)} items from MongoDB for user {user_id}")
                
                # Store in cache for future requests (cache for 30 minutes)
                cache.set(cache_key, watchlist, timeout=1800)
            else:
                logger.info(f"Cache hit for user {user_id} watchlist")
            
            return watchlist
        except Exception as e:
            logger.error(f"Error getting user watchlist: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Return empty list on error
            return []
    
    @classmethod
    def remove_from_watchlist(cls, user_id, movie_id):
        """Remove a movie from user's watchlist with error handling"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            from .mongodb_client import watchlists_collection
            
            # Ensure movie_id is an integer
            movie_id = int(movie_id)
            
            result = watchlists_collection.delete_one({
                'user_id': user_id,
                'movie_id': movie_id
            })
            
            # Invalidate cache
            cls._invalidate_cache(user_id)
            
            logger.info(f"Removed movie {movie_id} from watchlist for user {user_id}")
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error removing from watchlist: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    @classmethod
    def _invalidate_cache(cls, user_id):
        """Invalidate the cache for a user's watchlist with error handling"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            cache_key = f"user_watchlist_{user_id}"
            cache.delete(cache_key)
            logger.info(f"Invalidated cache for user {user_id}")
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")

class SearchHistory(models.Model):
    """Model for search history (used for form validation only)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.CharField(max_length=255)
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        managed = False
        
    def save(self, *args, **kwargs):
        from .mongodb_client import search_history_collection
        
        search_history_collection.insert_one({
            'user_id': self.user.id,
            'query': self.query,
            'timestamp': self.timestamp
        })
    
    @classmethod
    def get_user_searches(cls, user_id, limit=10):
        """Get search history for a user from MongoDB"""
        from .mongodb_client import search_history_collection
        
        searches = list(search_history_collection.find(
            {'user_id': user_id}
        ).sort('timestamp', -1).limit(limit))
        
        return searches

class ViewingHistory(models.Model):
    """Model for viewing history (used for form validation only)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    movie_id = models.IntegerField()
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        managed = False
        
    def save(self, *args, **kwargs):
        from .mongodb_client import viewing_history_collection
        
        viewing_history_collection.insert_one({
            'user_id': self.user.id,
            'movie_id': self.movie_id,
            'timestamp': self.timestamp
        })
    
    @classmethod
    def get_user_history(cls, user_id, limit=20):
        """Get viewing history for a user from MongoDB"""
        from .mongodb_client import viewing_history_collection
        
        history = list(viewing_history_collection.find(
            {'user_id': user_id}
        ).sort('timestamp', -1).limit(limit))
        
        return history


