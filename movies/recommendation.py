import logging
from .mongodb_client import watchlists_collection, viewed_movies_collection
from .movie_data import get_movie, get_popular_movies

logger = logging.getLogger(__name__)

def get_recommendations(user_id, limit=50):
    """
    Get movie recommendations for a user based on their viewing history and watchlist
    """
    from django.core.cache import cache
    import logging
    from datetime import datetime
    logger = logging.getLogger(__name__)
    
    # Try to get from cache first
    cache_key = f"user_recommendations_data_{user_id}_{limit}"
    cached_recommendations = cache.get(cache_key)
    if cached_recommendations is not None:
        logger.info(f"Retrieved recommendations from cache for user {user_id}")
        return cached_recommendations
    
    # Get current date for filtering unreleased movies
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    # Get user's viewed movies
    from .mongodb_client import viewed_movies_collection, watchlists_collection
    viewed_movies = viewed_movies_collection.find({'user_id': user_id})
    viewed_movie_ids = [item['movie_id'] for item in viewed_movies]
    
    # Get user's watchlist
    watchlist_items = watchlists_collection.find({'user_id': user_id})
    watchlist_movie_ids = [item['movie_id'] for item in watchlist_items]
    
    # Combine all user movie interactions
    all_user_movie_ids = set(viewed_movie_ids + watchlist_movie_ids)
    
    # If user has no history, return popular movies
    if not all_user_movie_ids:
        from .movie_data import get_popular_movies
        popular_movies = get_popular_movies(limit=limit)
        cache.set(cache_key, popular_movies, timeout=3600)  # Cache for 1 hour
        logger.info(f"No history for user {user_id}, returning popular movies")
        return popular_movies
    
    # Get cast recommendations based on user's movie history
    from .movie_data import get_movie, get_actor_movies
    
    # Dictionary to store all actor movies by actor ID
    actor_movies_dict = {}
    # Set to track processed actors
    processed_actors = set()
    # Set to track movies already added to recommendations
    recommended_movie_ids = set()
    # Final recommendations list
    recommendations = []
    
    logger.info(f"Processing {len(all_user_movie_ids)} movies for user {user_id}")
    
    # First, collect all first cast members from user's movies
    first_cast_members = []
    for movie_id in all_user_movie_ids:
        movie = get_movie(movie_id)
        if not movie or not movie.get('cast'):
            continue
            
        # Get the first cast member
        if movie['cast']:
            first_cast = movie['cast'][0]
            first_cast_members.append({
                'actor_id': first_cast['id'],
                'name': first_cast['name'],
                'source_movie_id': movie_id,
                'source_movie_title': movie['title']
            })
    
    logger.info(f"Found {len(first_cast_members)} first cast members")
    
    # Now process each first cast member
    for cast_member in first_cast_members:
        actor_id = cast_member['actor_id']
        
        # Skip if we've already processed this actor
        if actor_id in processed_actors:
            continue
            
        processed_actors.add(actor_id)
        
        # Get movies featuring this actor
        actor_movies = get_actor_movies(actor_id)
        
        # Filter out movies the user has already interacted with
        new_recommendations = [
            movie for movie in actor_movies 
            if movie['id'] not in all_user_movie_ids and movie['id'] not in recommended_movie_ids
        ]
        
        # Sort by release date (newest first)
        new_recommendations.sort(key=lambda x: x.get('release_date', ''), reverse=True)
        
        # Take only the top 5 newest movies from each actor
        new_recommendations = new_recommendations[:5]
        
        # Add to our tracking set
        for movie in new_recommendations:
            recommended_movie_ids.add(movie['id'])
        
        # Store in our dictionary
        actor_movies_dict[actor_id] = {
            'actor_name': cast_member['name'],
            'source_movie': cast_member['source_movie_title'],
            'movies': new_recommendations
        }
    
    logger.info(f"Processed {len(actor_movies_dict)} unique actors")
    
    # Now create a mixed list of recommendations by taking movies from each actor in turn
    mixed_recommendations = []
    
    # Keep going until we have enough recommendations or run out of movies
    while len(mixed_recommendations) < limit and actor_movies_dict:
        # Make a copy of the keys to avoid modification during iteration
        actor_ids = list(actor_movies_dict.keys())
        
        for actor_id in actor_ids:
            actor_data = actor_movies_dict[actor_id]
            if actor_data['movies']:
                # Take the first movie from this actor's list
                movie = actor_data['movies'].pop(0)
                mixed_recommendations.append(movie)
                
                # If we've reached our limit, break
                if len(mixed_recommendations) >= limit:
                    break
            else:
                # No more movies for this actor, remove from dictionary
                del actor_movies_dict[actor_id]
                
        # If we've gone through all actors and still need more recommendations,
        # we'll go through the remaining actors again in the next iteration
    
    # If we still don't have enough recommendations, supplement with genre-based recommendations
    if len(mixed_recommendations) < limit:
        logger.info(f"Only have {len(mixed_recommendations)} cast recommendations, adding genre-based")
        
        # Get genre preferences from user history
        genre_counts = {}
        
        # Process viewed movies
        for movie_id in viewed_movie_ids:
            movie = get_movie(movie_id)
            if movie and movie.get('genres'):
                for genre in movie.get('genres', []):
                    # Make sure genre is a dictionary with an 'id' key
                    if isinstance(genre, dict) and 'id' in genre:
                        genre_id = genre['id']
                        genre_counts[genre_id] = genre_counts.get(genre_id, 0) + 2  # Higher weight for viewed movies
        
        # Process watchlist
        for movie_id in watchlist_movie_ids:
            movie = get_movie(movie_id)
            if movie and movie.get('genres'):
                for genre in movie.get('genres', []):
                    # Make sure genre is a dictionary with an 'id' key
                    if isinstance(genre, dict) and 'id' in genre:
                        genre_id = genre['id']
                        genre_counts[genre_id] = genre_counts.get(genre_id, 0) + 3  # Higher weight for watchlist
        
        # Get popular movies as fallback if we can't get genre-based recommendations
        from .movie_data import get_popular_movies
        popular_movies = get_popular_movies(limit=limit - len(mixed_recommendations))
        
        # Filter out movies the user has already interacted with or that are already in recommendations
        popular_movies = [
            movie for movie in popular_movies 
            if movie['id'] not in all_user_movie_ids and movie['id'] not in recommended_movie_ids
        ]
        
        # Add popular movies to our recommendations
        mixed_recommendations.extend(popular_movies)
    
    # Before returning recommendations, filter out unreleased movies
    filtered_recommendations = []
    for movie in mixed_recommendations:
        # Only include movies with a release date that's in the past
        if movie.get('release_date') and movie['release_date'] <= current_date:
            filtered_recommendations.append(movie)
    
    # Limit to requested number
    recommendations = filtered_recommendations[:limit]
    
    logger.info(f"Final recommendation count after filtering unreleased: {len(recommendations)}")
    
    # Cache the results
    cache.set(cache_key, recommendations, timeout=3600)  # Cache for 1 hour
    
    return recommendations







