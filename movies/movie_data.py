import requests
import logging
import time
import random
from requests.adapters import HTTPAdapter
# Fix the import path for Retry
try:
    # For newer versions of requests
    from urllib3.util.retry import Retry
except ImportError:
    # For older versions of requests
    from requests.packages.urllib3.util.retry import Retry
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# TMDB API base URL
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_API_KEY = settings.TMDB_API_KEY

# Create a session with retry capability
def create_requests_session():
    """Create a requests session with retry capability"""
    session = requests.Session()
    
    # Configure retry strategy
    retries = Retry(
        total=5,  # Total number of retries
        backoff_factor=0.5,  # Backoff factor for sleep between retries
        status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry on
        allowed_methods=["GET"]  # Only retry on GET requests
    )
    
    # Add the retry adapter to the session
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

# Create a session to be reused
session = create_requests_session()

def make_tmdb_request(endpoint, params=None, cache_timeout=3600):
    """Make a request to TMDB API with caching and error handling"""
    global session  # Declare global at the beginning of the function
    
    if params is None:
        params = {}
    
    # Add API key to params
    params['api_key'] = TMDB_API_KEY
    
    # Create cache key based on endpoint and params
    cache_key = f"tmdb_{endpoint}_{str(params)}"
    
    # Try to get from cache first
    cached_response = cache.get(cache_key)
    if cached_response is not None:
        return cached_response
    
    # Not in cache, make the request
    url = f"{TMDB_BASE_URL}{endpoint}"
    
    try:
        # Add a small random delay to avoid hitting rate limits
        time.sleep(random.uniform(0.1, 0.3))
        
        # Make the request
        response = session.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        
        # Cache the response
        cache.set(cache_key, data, timeout=cache_timeout)
        
        return data
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error for {endpoint}: {e}")
        # Try to recreate the session
        session = create_requests_session()
        raise
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error for {endpoint}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for {endpoint}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error for {endpoint}: {e}")
        raise

def get_movie(movie_id):
    """Get detailed information about a specific movie with improved error handling"""
    try:
        # Try to get from cache first
        cache_key = f"movie_details_{movie_id}"
        movie = cache.get(cache_key)
        
        if movie is not None:
            return movie
        
        # Not in cache, fetch from API
        endpoint = f"/movie/{movie_id}"
        params = {
            'append_to_response': 'credits,videos,recommendations'
        }
        
        movie_data = make_tmdb_request(endpoint, params, cache_timeout=86400)  # Cache for 24 hours
        
        # Process movie data
        release_date = movie_data.get('release_date', '')
        
        movie = {
            'id': movie_data['id'],
            'title': movie_data['title'],
            'overview': movie_data.get('overview', ''),
            'release_date': release_date,  # Store the original date string
            'runtime': movie_data.get('runtime', 0),
            'vote_average': movie_data.get('vote_average', 0),
            'vote_count': movie_data.get('vote_count', 0),
            'genres': [genre['name'] for genre in movie_data.get('genres', [])],
            'poster_url': f"https://image.tmdb.org/t/p/w500{movie_data['poster_path']}" if movie_data.get('poster_path') else None,
            'backdrop_url': f"https://image.tmdb.org/t/p/original{movie_data['backdrop_path']}" if movie_data.get('backdrop_path') else None,
            'tagline': movie_data.get('tagline', ''),
            'status': movie_data.get('status', ''),
            'budget': movie_data.get('budget', 0),
            'revenue': movie_data.get('revenue', 0),
            'original_language': movie_data.get('original_language', ''),
            'production_companies': [company['name'] for company in movie_data.get('production_companies', [])],
            'production_countries': [country['name'] for country in movie_data.get('production_countries', [])],
        }
        
        # Add a formatted date for display if needed
        if release_date:
            try:
                from datetime import datetime
                date_obj = datetime.strptime(release_date, '%Y-%m-%d')
                movie['release_date_formatted'] = date_obj.strftime('%d-%m-%Y')
            except Exception as e:
                logger.warning(f"Could not format date {release_date}: {e}")
                movie['release_date_formatted'] = release_date
        
        # Add cast information - only include cast members with profile images
        cast = []
        for actor in movie_data.get('credits', {}).get('cast', [])[:20]:  # Check more actors to ensure we get enough with images
            # Only add cast members who have a profile image
            if actor.get('profile_path'):
                cast_member = {
                    'id': actor['id'],
                    'name': actor['name'],
                    'character': actor.get('character', ''),
                    'profile_path': actor.get('profile_path')
                }
                cast.append(cast_member)
                
                # Limit to top 10 actors with images
                if len(cast) >= 10:
                    break
                    
        movie['cast'] = cast
        
        # Store first cast member for related movies section (if any cast members exist)
        if cast:
            movie['first_cast'] = cast[0]
        else:
            movie['first_cast'] = None
        
        # Add director and writer information
        crew = movie_data.get('credits', {}).get('crew', [])
        
        directors = []
        writers = []
        
        for crew_member in crew:
            if crew_member.get('job') == 'Director':
                directors.append({
                    'id': crew_member['id'],
                    'name': crew_member['name'],
                    'profile_path': crew_member.get('profile_path')
                })
            elif crew_member.get('department') == 'Writing':
                writers.append({
                    'id': crew_member['id'],
                    'name': crew_member['name'],
                    'job': crew_member.get('job', ''),
                    'profile_path': crew_member.get('profile_path')
                })
        
        movie['directors'] = directors
        movie['writers'] = writers
        
        # Add trailer information
        movie['trailer_key'] = None  # Default to None

        # Look for trailers in the videos results
        videos = movie_data.get('videos', {}).get('results', [])

        # If no videos in the main response, try a dedicated videos request
        if not videos:
            logger.info(f"No videos in main response for movie {movie_id}, fetching videos separately")
            try:
                videos_data = make_tmdb_request(f"/movie/{movie_id}/videos", cache_timeout=86400)
                videos = videos_data.get('results', [])
            except Exception as e:
                logger.error(f"Error fetching videos for movie {movie_id}: {e}")
                videos = []

        # First look for official trailers
        for video in videos:
            # Check for YouTube videos that are trailers
            if (video.get('site') == 'YouTube' and 
                video.get('type') == 'Trailer' and 
                video.get('official', True) and
                video.get('key')):
                movie['trailer_key'] = video.get('key')
                logger.info(f"Found official trailer for movie {movie_id}: {video.get('key')}")
                break

        # If no official trailer, try any trailer
        if not movie['trailer_key']:
            for video in videos:
                if video.get('site') == 'YouTube' and video.get('type') == 'Trailer' and video.get('key'):
                    movie['trailer_key'] = video.get('key')
                    logger.info(f"Found trailer for movie {movie_id}: {video.get('key')}")
                    break

        # If still no trailer, try teasers
        if not movie['trailer_key']:
            for video in videos:
                if video.get('site') == 'YouTube' and video.get('type') == 'Teaser' and video.get('key'):
                    movie['trailer_key'] = video.get('key')
                    logger.info(f"Found teaser for movie {movie_id}: {video.get('key')}")
                    break

        # If still no trailer, try any YouTube video
        if not movie['trailer_key']:
            for video in videos:
                if video.get('site') == 'YouTube' and video.get('key'):
                    movie['trailer_key'] = video.get('key')
                    logger.info(f"Found YouTube video for movie {movie_id}: {video.get('key')}")
                    break

        # Add recommendations
        recommendations = []
        for rec in movie_data.get('recommendations', {}).get('results', [])[:6]:  # Limit to 6 recommendations
            if rec.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{rec['poster_path']}"
            else:
                poster_url = None
                
            recommendations.append({
                'id': rec['id'],
                'title': rec['title'],
                'poster_url': poster_url,
                'vote_average': rec.get('vote_average', 0)
            })
        movie['recommendations'] = recommendations
        
        # Cache the processed movie data
        cache.set(cache_key, movie, timeout=86400)  # Cache for 24 hours
        
        return movie
        
    except Exception as e:
        logger.error(f"Error fetching movie {movie_id}: {e}")
        return None

def get_popular_movies(page=1, limit=20):
    """Get a list of popular movies with improved error handling"""
    try:
        endpoint = "/movie/popular"
        params = {'page': page}
        
        data = make_tmdb_request(endpoint, params, cache_timeout=3600)  # Cache for 1 hour
        
        movies = []
        for movie in data.get('results', [])[:limit]:
            if movie.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            else:
                poster_url = None
                
            movies.append({
                'id': movie['id'],
                'title': movie['title'],
                'poster_url': poster_url,
                'release_date': movie.get('release_date', ''),
                'vote_average': movie.get('vote_average', 0),
                'overview': movie.get('overview', '')
            })
            
        return movies
        
    except Exception as e:
        logger.error(f"Error fetching popular movies: {e}")
        return []

def get_recommendations_for_movies(movie_ids, limit=20):
    """Get movie recommendations based on a list of movie IDs"""
    try:
        all_recommendations = []
        
        # Get recommendations for each movie
        for movie_id in movie_ids:
            url = f"{TMDB_BASE_URL}/movie/{movie_id}/recommendations"
            params = {
                'api_key': TMDB_API_KEY
            }
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Process recommendations
            for movie in data.get('results', []):
                if movie.get('poster_path'):
                    poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
                else:
                    poster_url = None
                    
                all_recommendations.append({
                    'id': movie['id'],
                    'title': movie['title'],
                    'poster_url': poster_url,
                    'release_date': movie.get('release_date', ''),
                    'vote_average': movie.get('vote_average', 0),
                    'overview': movie.get('overview', '')
                })
        
        # Remove duplicates by creating a dictionary with movie ID as key
        unique_recommendations = {}
        for movie in all_recommendations:
            if movie['id'] not in unique_recommendations:
                unique_recommendations[movie['id']] = movie
        
        # Convert back to list and sort by vote average
        recommendations = list(unique_recommendations.values())
        recommendations.sort(key=lambda x: x.get('vote_average', 0), reverse=True)
        
        return recommendations[:limit]  # Return top recommendations
        
    except Exception as e:
        logger.error(f"Error getting recommendations for movies {movie_ids}: {e}")
        return []

def get_trending_movies(time_window='week', page=1):
    """Get trending movies for the day or week"""
    try:
        url = f"{TMDB_BASE_URL}/trending/movie/{time_window}"
        params = {
            'api_key': TMDB_API_KEY,
            'page': page
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        movies = []
        for movie in data.get('results', []):
            if movie.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            else:
                poster_url = None
                
            movies.append({
                'id': movie['id'],
                'title': movie['title'],
                'poster_url': poster_url,
                'release_date': movie.get('release_date', ''),
                'vote_average': movie.get('vote_average', 0),
                'overview': movie.get('overview', '')
            })
            
        return movies
        
    except Exception as e:
        logger.error(f"Error fetching trending movies: {e}")
        return []

def get_actor_details(actor_id):
    """Get detailed information about an actor"""
    try:
        cache_key = f"actor_details_{actor_id}"
        actor = cache.get(cache_key)
        if actor is not None:
            return actor

        endpoint = f"/person/{actor_id}"
        params = {
            'append_to_response': 'images'
        }
        data = make_tmdb_request(endpoint, params, cache_timeout=86400)  # Use retry/caching

        # Process actor data
        actor = {
            'id': data['id'],
            'name': data['name'],
            'biography': data.get('biography', ''),
            'birthday': data.get('birthday'),
            'deathday': data.get('deathday'),
            'place_of_birth': data.get('place_of_birth'),
            'profile_url': f"https://image.tmdb.org/t/p/w500{data['profile_path']}" if data.get('profile_path') else None,
            'known_for_department': data.get('known_for_department'),
            'gender': data.get('gender'),
            'popularity': data.get('popularity')
        }

        # Get additional images if available
        images = []
        for image in data.get('images', {}).get('profiles', [])[:10]:  # Limit to 10 images
            images.append({
                'file_path': f"https://image.tmdb.org/t/p/w500{image['file_path']}",
                'aspect_ratio': image.get('aspect_ratio', 0),
                'height': image.get('height', 0),
                'width': image.get('width', 0)
            })
        actor['images'] = images

        cache.set(cache_key, actor, timeout=86400)  # Cache for 24 hours
        return actor

    except Exception as e:
        logger.error(f"Error fetching actor {actor_id}: {e}")
        return None

def get_actor_movies(actor_id, limit=20):
    """Get movies featuring a specific actor"""
    try:
        # Try to get from cache first
        cache_key = f"actor_movies_{actor_id}"
        movies = cache.get(cache_key)
        
        if movies is not None:
            return movies
        
        # Not in cache, fetch from API
        endpoint = f"/person/{actor_id}/movie_credits"
        
        data = make_tmdb_request(endpoint, cache_timeout=86400)  # Cache for 24 hours
        
        # Process cast credits (movies the actor appeared in)
        movies = []
        for movie in data.get('cast', []):
            if movie.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            else:
                poster_url = None
                
            movies.append({
                'id': movie['id'],
                'title': movie['title'],
                'poster_url': poster_url,
                'release_date': movie.get('release_date', ''),
                'vote_average': movie.get('vote_average', 0),
                'character': movie.get('character', ''),
                'overview': movie.get('overview', '')
            })
        
        # Cache the results
        cache.set(cache_key, movies, timeout=86400)  # Cache for 24 hours
        
        return movies
        
    except Exception as e:
        logger.error(f"Error fetching movies for actor {actor_id}: {e}")
        return []

def search_movies(query, page=1):
    """Search for movies by title"""
    try:
        endpoint = "/search/movie"
        params = {
            'query': query,
            'page': page,
            'include_adult': 'false'
        }
        
        data = make_tmdb_request(endpoint, params, cache_timeout=3600)
        
        results = []
        
        for movie in data.get('results', []):
            if movie.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            else:
                poster_url = None
            
            # Get genres for the movie
            genres = []
            for genre_id in movie.get('genre_ids', []):
                genre_name = get_genre_name(genre_id)
                if genre_name:
                    genres.append(genre_name)
            
            results.append({
                'id': movie['id'],
                'title': movie['title'],
                'poster_url': poster_url,
                'release_date': movie.get('release_date', ''),
                'vote_average': movie.get('vote_average', 0),
                'overview': movie.get('overview', ''),
                'original_language': movie.get('original_language', ''),
                'genres': genres
            })
        
        return results
    except Exception as e:
        logger.error(f"Error searching movies: {e}")
        return []

def get_movie_genres(movie_id):
    """Get genres for a specific movie"""
    try:
        movie = get_movie(movie_id)
        if movie and 'genres' in movie:
            return movie['genres']
        return []
    except Exception as e:
        logger.error(f"Error getting genres for movie {movie_id}: {e}")
        return []

def search_movies_by_filters(query=None, year=None, genre=None, language=None, page=1):
    """Search for movies with multiple filters"""
    try:
        # Start with basic search or discover endpoint
        if query:
            endpoint = "/search/movie"
            params = {
                'query': query,
                'page': page,
                'include_adult': 'false'
            }
        else:
            endpoint = "/discover/movie"
            params = {
                'page': page,
                'include_adult': 'false',
                'sort_by': 'popularity.desc'
            }
        
        # Add year filter if provided
        if year:
            params['primary_release_year'] = year
        
        # Add language filter if provided
        if language:
            params['with_original_language'] = language
        
        # Genre needs to be handled separately as it requires genre ID
        if genre:
            # Get genre ID from name (would need a mapping function)
            genre_id = get_genre_id(genre)
            if genre_id:
                params['with_genres'] = genre_id
        
        # Make the API request
        data = make_tmdb_request(endpoint, params, cache_timeout=3600)
        
        results = []
        
        # Process movie results
        for movie in data.get('results', []):
            if movie.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            else:
                poster_url = None
            
            # Get genres for the movie
            genres = []
            for genre_id in movie.get('genre_ids', []):
                genre_name = get_genre_name(genre_id)
                if genre_name:
                    genres.append(genre_name)
                
            results.append({
                'id': movie['id'],
                'title': movie['title'],
                'poster_url': poster_url,
                'release_date': movie.get('release_date', ''),
                'vote_average': movie.get('vote_average', 0),
                'overview': movie.get('overview', ''),
                'original_language': movie.get('original_language', ''),
                'genres': genres
            })
        
        return results
    except Exception as e:
        logger.error(f"Error searching movies with filters: {e}")
        return []

# Helper functions for genre mapping
def get_genre_id(genre_name):
    """Convert genre name to genre ID"""
    genre_map = {
        'Action': 28,
        'Adventure': 12,
        'Animation': 16,
        'Comedy': 35,
        'Crime': 80,
        'Documentary': 99,
        'Drama': 18,
        'Family': 10751,
        'Fantasy': 14,
        'History': 36,
        'Horror': 27,
        'Music': 10402,
        'Mystery': 9648,
        'Romance': 10749,
        'Science Fiction': 878,
        'TV Movie': 10770,
        'Thriller': 53,
        'War': 10752,
        'Western': 37
    }
    return genre_map.get(genre_name)

def get_genre_name(genre_id):
    """Convert genre ID to genre name"""
    genre_map = {
        28: 'Action',
        12: 'Adventure',
        16: 'Animation',
        35: 'Comedy',
        80: 'Crime',
        99: 'Documentary',
        18: 'Drama',
        10751: 'Family',
        14: 'Fantasy',
        36: 'History',
        27: 'Horror',
        10402: 'Music',
        9648: 'Mystery',
        10749: 'Romance',
        878: 'Science Fiction',
        10770: 'TV Movie',
        53: 'Thriller',
        10752: 'War',
        37: 'Western'
    }
    return genre_map.get(genre_id)

def search_movies_by_person(person_id):
    """Search for movies by a specific person (actor or director)"""
    try:
        endpoint = f"/person/{person_id}/movie_credits"
        params = {
            'api_key': TMDB_API_KEY
        }
        data = make_tmdb_request(endpoint, params, cache_timeout=86400)  # Cache for 24 hours
        
        # Process movie results
        results = []
        for movie in data.get('cast', []) + data.get('crew', []):
            if movie.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            else:
                poster_url = None
            
            results.append({
                'id': movie['id'],
                'title': movie['title'],
                'poster_url': poster_url,
                'release_date': movie.get('release_date', ''),
                'vote_average': movie.get('vote_average', 0),
                'overview': movie.get('overview', '')
            })
        
        return results
    except Exception as e:
        logger.error(f"Error searching movies for person {person_id}: {e}")
        return []































