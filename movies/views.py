from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from datetime import datetime
import logging

# Initialize logger
logger = logging.getLogger(__name__)

# Import movie data functions
from .movie_data import get_movie, search_movies, get_popular_movies

def home(request):
    """Home page view showing personalized or popular movies"""
    try:
        from django.core.cache import cache
        import logging
        logger = logging.getLogger(__name__)
        
        if request.user.is_authenticated:
            # Cache recommendations for 24 hours (1 day)
            cache_key = f"user_home_cast_movies_{request.user.id}"
            movies = cache.get(cache_key)
            
            if movies is None:
                try:
                    # Get user's viewed movies and watchlist
                    from .mongodb_client import viewed_movies_collection, watchlists_collection
                    from .movie_data import get_movie, get_actor_movies
                    from datetime import datetime
                    
                    # Get current date for filtering unreleased movies
                    current_date = datetime.now().strftime('%Y-%m-%d')
                    
                    # Get viewed movie IDs
                    viewed_movies = viewed_movies_collection.find({'user_id': request.user.id})
                    viewed_movie_ids = [item['movie_id'] for item in viewed_movies]
                    
                    # Get watchlist movie IDs
                    watchlist_items = watchlists_collection.find({'user_id': request.user.id})
                    watchlist_movie_ids = [item['movie_id'] for item in watchlist_items]
                    
                    # Combine all user movie interactions
                    all_user_movie_ids = list(set(viewed_movie_ids + watchlist_movie_ids))
                    
                    # Get first cast members from these movies
                    first_cast_members = []
                    for movie_id in all_user_movie_ids:
                        movie = get_movie(movie_id)
                        if not movie or not movie.get('first_cast'):
                            continue
                            
                        first_cast = movie['first_cast']
                        first_cast_members.append({
                            'actor_id': first_cast['id'],
                            'name': first_cast['name'],
                            'source_movie_id': movie_id
                        })
                    
                    # Get movies from these cast members
                    cast_movies = []
                    processed_movie_ids = set(all_user_movie_ids)  # Don't show movies user already interacted with
                    
                    for cast_member in first_cast_members:
                        actor_movies = get_actor_movies(cast_member['actor_id'])
                        
                        # Filter out movies the user has already interacted with and unreleased movies
                        new_movies = [
                            movie for movie in actor_movies 
                            if movie['id'] not in processed_movie_ids
                            and movie.get('release_date', '') <= current_date  # Filter unreleased movies
                        ]
                        
                        # Add to our list and tracking set
                        for movie in new_movies:
                            if movie['id'] not in processed_movie_ids:
                                cast_movies.append(movie)
                                processed_movie_ids.add(movie['id'])
                    
                    # Sort by release date (newest first)
                    cast_movies.sort(key=lambda x: x.get('release_date', ''), reverse=True)
                    
                    # Limit to 20 movies
                    movies = cast_movies[:20]
                    
                    # If we don't have enough movies, supplement with popular movies
                    if len(movies) < 20:
                        from .movie_data import get_popular_movies
                        popular_movies = get_popular_movies(limit=20 - len(movies))
                        
                        # Filter out movies the user has already interacted with or that are already in recommendations
                        popular_movies = [
                            movie for movie in popular_movies 
                            if movie['id'] not in processed_movie_ids
                        ]
                        
                        movies.extend(popular_movies)
                        movies = movies[:20]  # Ensure we have at most 20 movies
                    
                    # Cache for 24 hours
                    cache.set(cache_key, movies, timeout=60*60*24)
                    logger.info(f"Generated {len(movies)} home cast movies for user {request.user.id}")
                except Exception as e:
                    logger.error(f"Error in home view: {e}")
                    from .movie_data import get_popular_movies
                    movies = get_popular_movies(limit=20)
            else:
                logger.info(f"Retrieved {len(movies)} home cast movies from cache for user {request.user.id}")
        else:
            from .movie_data import get_popular_movies
            movies = get_popular_movies(limit=20)
        
        return render(request, 'home.html', {
            'movies': movies,
            'page_title': 'Latest Movies from Your Favorite Actors' if request.user.is_authenticated else 'Popular Movies'
        })
    except Exception as e:
        logger.error(f"Error in home view: {e}")
        messages.error(request, "An error occurred while loading the home page. Please try again later.")
        from .movie_data import get_popular_movies
        movies = get_popular_movies(limit=20)
        return render(request, 'home.html', {
            'movies': movies,
            'page_title': 'Popular Movies'
        })

def movie_detail(request, movie_id):
    """Show details for a specific movie"""
    try:
        from .movie_data import get_movie, get_actor_movies
        from datetime import datetime
        
        # Get current date for filtering unreleased movies
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Get movie details
        movie = get_movie(movie_id)
        if not movie:
            messages.warning(request, "Movie not found.")
            return redirect('home')
        
        # Get movies featuring the first cast member (if available)
        first_cast_movies = []
        if movie.get('first_cast'):
            first_cast_id = movie['first_cast']['id']
            first_cast_movies = get_actor_movies(first_cast_id)
            # Remove the current movie from the list
            first_cast_movies = [m for m in first_cast_movies if m['id'] != movie_id]
            
            # Filter out unreleased movies
            first_cast_movies = [m for m in first_cast_movies if m.get('release_date') and m['release_date'] <= current_date]
            
            # Sort by release date (newest first)
            first_cast_movies.sort(key=lambda x: x.get('release_date', ''), reverse=True)
            
            # Limit to 20 movies
            first_cast_movies = first_cast_movies[:20]
        
        # Record this movie as viewed by the user (if logged in)
        if request.user.is_authenticated:
            from .mongodb_client import viewed_movies_collection
            from datetime import datetime
            
            viewed_movies_collection.update_one(
                {'user_id': request.user.id, 'movie_id': movie_id},
                {'$set': {
                    'user_id': request.user.id,
                    'movie_id': movie_id,
                    'last_viewed': datetime.now()
                }},
                upsert=True
            )
        
        return render(request, 'movie_detail.html', {
            'movie': movie,
            'first_cast_movies': first_cast_movies
        })
    except Exception as e:
        logger.error(f"Error in movie_detail view for movie {movie_id}: {e}")
        messages.error(request, "An error occurred while loading movie details. Please try again later.")
        return redirect('home')

def movie_filter(request):
    """Filter movies by title, year, genre, and language"""
    return render(request, 'movie_search.html')

def movie_filter_ajax(request):
    """AJAX endpoint for filtering movies"""
    try:
        from .movie_data import search_movies, get_popular_movies
        from datetime import datetime
        import re
        
        # Get filter parameters
        query = request.GET.get('query', '').strip()
        genre = request.GET.get('genre', '').strip()
        year = request.GET.get('year', '').strip()
        language = request.GET.get('language', '').strip()
        
        # Log the search if user is authenticated
        if request.user.is_authenticated and (query or genre or year or language):
            try:
                from .mongodb_client import search_history_collection
                
                search_history_collection.insert_one({
                    'user_id': request.user.id,
                    'query': query,
                    'filters': {
                        'genre': genre,
                        'year': year,
                        'language': language
                    },
                    'timestamp': datetime.now()
                })
                logger.info(f"Logged filtered search for user {request.user.id}")
            except Exception as e:
                logger.error(f"Error logging search: {e}")
        
        # Different search strategies based on provided filters
        results = []
        
        # Case 1: Title search (with or without other filters)
        if query:
            results = search_movies(query)
            
            # Apply additional filters if provided
            if year:
                # Filter by year
                year_pattern = re.compile(f'^{year}')
                results = [movie for movie in results if movie.get('release_date') and year_pattern.match(movie.get('release_date', ''))]
            
            if genre:
                # Filter by genre
                results = [movie for movie in results if genre.lower() in [g.lower() for g in movie.get('genres', [])]]
            
            if language:
                # Filter by language
                results = [movie for movie in results if movie.get('original_language') == language]
        
        # Case 2: No title, but other filters
        else:
            # Start with popular movies as base
            results = get_popular_movies(limit=100)  # Get more to filter from
            
            # Apply filters
            if year:
                # Filter by year
                year_pattern = re.compile(f'^{year}')
                results = [movie for movie in results if movie.get('release_date') and year_pattern.match(movie.get('release_date', ''))]
            
            if genre:
                # Filter by genre
                results = [movie for movie in results if genre.lower() in [g.lower() for g in movie.get('genres', [])]]
            
            if language:
                # Filter by language
                results = [movie for movie in results if movie.get('original_language') == language]
            
            # If only year is provided, prioritize Tamil and English movies
            if year and not genre and not language:
                # First get Tamil and English movies for that year
                tamil_english = [movie for movie in results if movie.get('original_language') in ['ta', 'en']]
                other_langs = [movie for movie in results if movie.get('original_language') not in ['ta', 'en']]
                
                # Sort by popularity
                tamil_english.sort(key=lambda x: x.get('vote_average', 0), reverse=True)
                other_langs.sort(key=lambda x: x.get('vote_average', 0), reverse=True)
                
                # Combine with Tamil/English first
                results = tamil_english + other_langs
            
            # If only genre is provided, sort by release date (newest first)
            if genre and not year and not language:
                results.sort(key=lambda x: x.get('release_date', ''), reverse=True)
        
        # Limit results to 50 for performance
        results = results[:50]
        
        # Return JSON response
        return JsonResponse({
            'movies': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Error in movie filter: {e}")
        return JsonResponse({
            'movies': [],
            'count': 0,
            'error': str(e)
        })

@login_required
def watchlist(request):
    """View user's watchlist with robust error handling and fallbacks"""
    try:
        from .models import Watchlist
        from .movie_data import get_movie, get_popular_movies
        from django.core.cache import cache
        import traceback
        
        # Get user's watchlist (this will use cache if available)
        try:
            watchlist_entries = Watchlist.get_user_watchlist(request.user.id)
            logger.info(f"Retrieved {len(watchlist_entries)} watchlist entries for user {request.user.id}")
        except Exception as e:
            logger.error(f"Error getting watchlist entries: {e}")
            logger.error(traceback.format_exc())
            watchlist_entries = []
        
        # Create a cache key for the full watchlist with movie details
        cache_key = f"user_watchlist_details_{request.user.id}"
        movies = cache.get(cache_key)
        
        if movies is None:
            # Cache miss - need to fetch movie details
            movies = []
            api_errors = 0  # Count API errors
            
            for entry in watchlist_entries:
                try:
                    movie_id = entry.get('movie_id')
                    if not movie_id:
                        logger.warning(f"Missing movie_id in watchlist entry: {entry}")
                        continue
                        
                    movie = get_movie(movie_id)
                    if movie:
                        # Add the date the movie was added to watchlist
                        movie['added_date'] = entry.get('added_at')
                        movies.append(movie)
                    else:
                        logger.warning(f"Movie with ID {movie_id} not found")
                except Exception as movie_error:
                    logger.error(f"Error processing movie {entry.get('movie_id', 'unknown')}: {movie_error}")
                    api_errors += 1
                    
                    # If we've had too many API errors, stop trying to fetch more movies
                    if api_errors >= 3:
                        logger.error("Too many API errors, stopping movie fetching")
                        break
                    
                    continue
            
            # Only cache if we have movies and didn't encounter too many errors
            if movies and api_errors < 3:
                try:
                    cache.set(cache_key, movies, timeout=900)
                except Exception as cache_error:
                    logger.error(f"Error setting cache: {cache_error}")
        
        logger.info(f"User {request.user.id} has {len(movies)} movies in watchlist")
        
        # If we couldn't fetch any movies due to API errors, show a specific message
        if not movies and watchlist_entries:
            messages.warning(request, "We're having trouble connecting to our movie database. Your watchlist is still saved, but we can't display the movies right now. Please try again later.")
        
        # If watchlist is empty or has very few movies, add some recommended movies
        recommended_movies = []
        if len(movies) < 5:
            try:
                # Try to get recommendations from cache
                rec_cache_key = f"user_recommendations_{request.user.id}"
                recommended_movies = cache.get(rec_cache_key)
                
                if recommended_movies is None:
                    # Get some popular movies as recommendations
                    popular_movies = get_popular_movies(limit=10)
                    
                    # Filter out movies already in watchlist
                    watchlist_ids = [m.get('id') for m in movies if m.get('id')]
                    recommended_movies = [m for m in popular_movies if m.get('id') not in watchlist_ids]
                    
                    # Limit to 5 recommendations
                    recommended_movies = recommended_movies[:5]
                    
                    # Cache recommendations for 1 hour
                    cache.set(rec_cache_key, recommended_movies, timeout=3600)
            except Exception as rec_error:
                logger.error(f"Error getting recommendations: {rec_error}")
                logger.error(traceback.format_exc())
                recommended_movies = []
        
        return render(request, 'watchlist.html', {
            'movies': movies,
            'recommended_movies': recommended_movies,
            'has_few_movies': len(movies) < 5 and len(recommended_movies) > 0
        })
    except Exception as e:
        logger.error(f"Error in watchlist view for user {request.user.id}: {e}")
        logger.error(traceback.format_exc())
        messages.error(request, "An error occurred while loading your watchlist. Please try again later.")
        return render(request, 'watchlist.html', {'movies': []})

@login_required
def add_to_watchlist(request, movie_id):
    """Add a movie to user's watchlist with cache invalidation"""
    try:
        # Import the Watchlist model
        from .models import Watchlist
        from django.utils import timezone
        from django.core.cache import cache
        
        # Convert movie_id to integer to ensure consistency
        movie_id = int(movie_id)
        
        # Check if movie exists
        from .movie_data import get_movie
        movie = get_movie(movie_id)
        if not movie:
            messages.warning(request, "Movie not found.")
            return redirect('home')
        
        # Add to watchlist using our model method (which handles caching)
        watchlist_item = Watchlist(
            user=request.user,
            movie_id=movie_id,
            added_at=timezone.now()
        )
        watchlist_item.save()
        
        # Also invalidate the full watchlist details cache
        cache.delete(f"user_watchlist_details_{request.user.id}")
        cache.delete(f"user_recommendations_{request.user.id}")
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'success': True, 'message': 'Movie added to watchlist'})
        
        messages.success(request, f"'{movie['title']}' added to your watchlist.")
        
        # Redirect back to the referring page if available
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('movie_detail', movie_id=movie_id)
    except Exception as e:
        logger.error(f"Error adding movie {movie_id} to watchlist for user {request.user.id}: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'success': False, 'message': 'Error adding movie to watchlist'})
        messages.error(request, "An error occurred. Please try again later.")
        return redirect('home')

@login_required
def remove_from_watchlist(request, movie_id):
    """Remove a movie from user's watchlist with cache invalidation"""
    try:
        # Import necessary modules
        from .models import Watchlist
        from django.core.cache import cache
        
        # Convert movie_id to integer to ensure consistency
        movie_id = int(movie_id)
        
        # Remove from watchlist using our model method (which handles caching)
        success = Watchlist.remove_from_watchlist(request.user.id, movie_id)
        
        # Also invalidate the full watchlist details cache
        cache.delete(f"user_watchlist_details_{request.user.id}")
        cache.delete(f"user_recommendations_{request.user.id}")
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            if success:
                return JsonResponse({'success': True, 'message': 'Movie removed from watchlist'})
            else:
                return JsonResponse({'success': False, 'message': 'Movie was not in watchlist'})
        
        if success:
            messages.success(request, "Movie removed from your watchlist.")
        else:
            messages.info(request, "Movie was not in your watchlist.")
        
        # Redirect back to the watchlist page
        return redirect('watchlist')
    except Exception as e:
        logger.error(f"Error removing movie {movie_id} from watchlist for user {request.user.id}: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'success': False, 'message': 'Error removing movie from watchlist'})
        messages.error(request, "An error occurred. Please try again later.")
        return redirect('watchlist')

def register(request):
    """Register a new user"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully! You can now log in.")
            return redirect('login')
    else:
        form = UserCreationForm()
    
    return render(request, 'register.html', {'form': form})

def actor_movies(request, actor_id):
    """Show movies for a specific actor"""
    try:
        from .movie_data import get_actor_details, get_actor_movies
        
        # Get actor details
        actor = get_actor_details(actor_id)
        if not actor:
            messages.warning(request, "Actor not found.")
            return redirect('home')
        
        # Get movies for this actor
        movies = get_actor_movies(actor_id)
        
        return render(request, 'actor_movies.html', {
            'actor': actor,
            'movies': movies
        })
    except Exception as e:
        logger.error(f"Error in actor_movies view for actor {actor_id}: {e}")
        messages.error(request, "An error occurred while loading actor information. Please try again later.")
        return redirect('home')

# The function below should be removed or commented out
# def trending(request):
#     """Show trending movies"""
#     try:
#         from .movie_data import get_trending_movies
#         trending_movies = get_trending_movies()
#         
#         return render(request, 'trending.html', {
#             'movies': trending_movies,
#             'title': 'Trending Movies'
#         })
#     except Exception as e:
#         logger.error(f"Error in trending view: {e}")
#         messages.error(request, "An error occurred while loading trending movies. Please try again later.")
#         return render(request, 'trending.html', {'movies': []})

def search(request):
    """Search for movies by title, actor, or director with filters"""
    query = request.GET.get('q', '')
    year = request.GET.get('year', '')
    genre = request.GET.get('genre', '')
    language = request.GET.get('language', '')
    
    # Generate year range for dropdown (current year down to 1900)
    import datetime
    current_year = datetime.datetime.now().year
    year_range = range(current_year, 1900, -1)
    
    # Log search query if user is authenticated
    if request.user.is_authenticated and (query or year or genre or language):
        try:
            from .mongodb_client import search_history_collection
            from datetime import datetime
            
            search_history_collection.insert_one({
                'user_id': request.user.id,
                'query': query,
                'filters': {
                    'year': year,
                    'genre': genre,
                    'language': language
                },
                'timestamp': datetime.now()
            })
            logger.info(f"Logged search query with filters for user {request.user.id}")
        except Exception as e:
            logger.error(f"Error logging search query: {e}")
            # Continue with search even if logging fails
    
    results = []
    
    # Search for movies based on provided parameters
    if query or year or genre or language:
        try:
            from .movie_data import search_movies, get_popular_movies
            import re
            
            # Case 1: Title search (with or without other filters)
            if query:
                results = search_movies(query)
                
                # Apply additional filters if provided
                if year:
                    # Filter by year
                    year_pattern = re.compile(f'^{year}')
                    results = [movie for movie in results if movie.get('release_date') and year_pattern.match(movie.get('release_date', ''))]
                
                if genre:
                    # Filter by genre
                    results = [movie for movie in results if genre.lower() in [g.lower() for g in movie.get('genres', [])]]
                
                if language:
                    # Filter by language
                    results = [movie for movie in results if movie.get('original_language') == language]
            
            # Case 2: No title, but other filters
            else:
                # Start with popular movies as base
                results = get_popular_movies(limit=100)  # Get more to filter from
                
                # Apply filters
                if year:
                    # Filter by year
                    year_pattern = re.compile(f'^{year}')
                    results = [movie for movie in results if movie.get('release_date') and year_pattern.match(movie.get('release_date', ''))]
                
                if genre:
                    # Filter by genre
                    results = [movie for movie in results if genre.lower() in [g.lower() for g in movie.get('genres', [])]]
                
                if language:
                    # Filter by language
                    results = [movie for movie in results if movie.get('original_language') == language]
                
                # If only year is provided, prioritize Tamil and English movies
                if year and not genre and not language:
                    # First get Tamil and English movies for that year
                    tamil_english = [movie for movie in results if movie.get('original_language') in ['ta', 'en']]
                    other_langs = [movie for movie in results if movie.get('original_language') not in ['ta', 'en']]
                    
                    # Sort by popularity
                    tamil_english.sort(key=lambda x: x.get('vote_average', 0), reverse=True)
                    other_langs.sort(key=lambda x: x.get('vote_average', 0), reverse=True)
                    
                    # Combine with Tamil/English first
                    results = tamil_english + other_langs
                
                # If only genre is provided, sort by release date (newest first)
                if genre and not year and not language:
                    results.sort(key=lambda x: x.get('release_date', ''), reverse=True)
            
            logger.info(f"Search with filters returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"Error searching for movies with filters: {e}")
            results = []
            messages.error(request, "An error occurred while searching. Please try again later.")
    
    return render(request, 'search.html', {
        'query': query,
        'year': year,
        'genre': genre,
        'language': language,
        'results': results,
        'year_range': year_range
    })

@login_required
def recommendations(request):
    """Show personalized movie recommendations for the user"""
    try:
        from django.core.cache import cache
        import traceback
        from datetime import datetime
        
        # Get current date for filtering unreleased movies
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Try to get recommendations from cache
        cache_key = f"user_recommendations_{request.user.id}"
        recommendations = cache.get(cache_key)
        
        if recommendations is None:
            # Get user's viewed movies and watchlist
            from .mongodb_client import viewed_movies_collection, watchlists_collection
            from .movie_data import get_movie, get_actor_movies, get_popular_movies
            
            # Get viewed movie IDs
            viewed_movies = viewed_movies_collection.find({'user_id': request.user.id})
            viewed_movie_ids = [item['movie_id'] for item in viewed_movies]
            
            # Get watchlist movie IDs
            watchlist_items = watchlists_collection.find({'user_id': request.user.id})
            watchlist_movie_ids = [item['movie_id'] for item in watchlist_items]
            
            # Combine all user movie interactions
            all_user_movie_ids = list(set(viewed_movie_ids + watchlist_movie_ids))
            
            # If user has no history, return popular movies
            if not all_user_movie_ids:
                recommendations = get_popular_movies(limit=20)
                message = "Explore some movies to get personalized recommendations!"
                recommendation_type = "popular"
            else:
                # Get first cast members from these movies
                first_cast_members = []
                for movie_id in all_user_movie_ids:
                    movie = get_movie(movie_id)
                    if not movie or not movie.get('first_cast'):
                        continue
                        
                    first_cast = movie['first_cast']
                    first_cast_members.append({
                        'actor_id': first_cast['id'],
                        'name': first_cast['name'],
                        'source_movie_id': movie_id,
                        'source_movie_title': movie['title']
                    })
                
                # Get movies from these cast members
                cast_movies = []
                processed_movie_ids = set(all_user_movie_ids)  # Don't show movies user already interacted with
                
                for cast_member in first_cast_members:
                    actor_movies = get_actor_movies(cast_member['actor_id'])
                    
                    # Filter out movies the user has already interacted with and unreleased movies
                    new_movies = [
                        movie for movie in actor_movies 
                        if movie['id'] not in processed_movie_ids
                        and movie.get('release_date', '') <= current_date  # Filter unreleased movies
                    ]
                    
                    # Add to our list and tracking set
                    for movie in new_movies:
                        if movie['id'] not in processed_movie_ids:
                            # Add source information to the movie
                            movie['recommended_because'] = {
                                'actor_name': cast_member['name'],
                                'source_movie': cast_member['source_movie_title']
                            }
                            cast_movies.append(movie)
                            processed_movie_ids.add(movie['id'])
                
                # Sort by release date (newest first)
                cast_movies.sort(key=lambda x: x.get('release_date', ''), reverse=True)
                
                # Limit to 20 movies
                recommendations = cast_movies[:20]
                
                # If we don't have enough movies, supplement with popular movies
                if len(recommendations) < 20:
                    popular_movies = get_popular_movies(limit=20 - len(recommendations))
                    
                    # Filter out movies the user has already interacted with or that are already in recommendations
                    popular_movies = [
                        movie for movie in popular_movies 
                        if movie['id'] not in processed_movie_ids
                    ]
                    
                    recommendations.extend(popular_movies)
                    recommendations = recommendations[:20]  # Ensure we have at most 20 movies
                
                message = "Latest movies from actors in your favorite films"
                recommendation_type = "personalized"
            
            # Cache the recommendations for 1 hour
            cache.set(cache_key, recommendations, timeout=3600)
            
            logger.info(f"Generated {len(recommendations)} recommendations for user {request.user.id}")
        else:
            logger.info(f"Retrieved {len(recommendations)} recommendations from cache for user {request.user.id}")
            message = "Latest movies from actors in your favorite films"
            recommendation_type = "personalized"
        
        return render(request, 'recommendations.html', {
            'recommendations': recommendations,
            'recommendation_type': recommendation_type,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Error generating recommendations for user {request.user.id}: {e}")
        logger.error(traceback.format_exc())
        messages.error(request, "An error occurred while generating recommendations. Please try again later.")
        
        # Fallback to popular movies
        from .movie_data import get_popular_movies
        popular_movies = get_popular_movies(limit=20)
        return render(request, 'recommendations.html', {
            'recommendations': popular_movies,
            'recommendation_type': 'popular',
            'message': "Popular movies (error occurred with personalized recommendations)"
        })

@login_required
def profile(request):
    """User profile view"""
    try:
        # Get user's movie statistics
        from .mongodb_client import viewed_movies_collection, watchlists_collection
        
        # Count viewed movies
        viewed_count = viewed_movies_collection.count_documents({'user_id': request.user.id})
        
        # Count watchlist movies
        watchlist_count = watchlists_collection.count_documents({'user_id': request.user.id})
        
        # Get recently viewed movies
        recent_views = list(viewed_movies_collection.find(
            {'user_id': request.user.id}
        ).sort('last_viewed', -1).limit(5))
        
        recent_movies = []
        for view in recent_views:
            movie = get_movie(view['movie_id'])
            if movie:
                movie['last_viewed'] = view.get('last_viewed')
                recent_movies.append(movie)
        
        context = {
            'user': request.user,
            'viewed_count': viewed_count,
            'watchlist_count': watchlist_count,
            'recent_movies': recent_movies
        }
        
        return render(request, 'profile.html', context)
    except Exception as e:
        logger.error(f"Error in profile view for user {request.user.id}: {e}")
        messages.error(request, "An error occurred while loading your profile. Please try again later.")
        return render(request, 'profile.html', {'user': request.user})

def custom_logout(request):
    """Custom logout view that redirects to home page with a message"""
    from django.contrib.auth import logout
    from django.contrib import messages
    
    if request.method == 'POST':
        logout(request)
        messages.success(request, "You have been successfully logged out.")
    
    return redirect('home')

def landing(request):
    return render(request, 'landing.html')








































