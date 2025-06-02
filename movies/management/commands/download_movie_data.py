import os
import json
import requests
import logging
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)

# TMDB API settings
TMDB_API_KEY = settings.TMDB_API_KEY
TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"

class Command(BaseCommand):
    help = 'Download movie data from TMDB API and save to JSON files'

    def add_arguments(self, parser):
        parser.add_argument('--pages', type=int, default=5, help='Number of pages of popular movies to download')
        parser.add_argument('--force', action='store_true', help='Force download even if files exist')

    def handle(self, *args, **options):
        if not TMDB_API_KEY:
            self.stdout.write(self.style.ERROR('TMDB API key not found. Please set TMDB_API_KEY in .env file.'))
            return
            
        pages = options['pages']
        force = options['force']
        
        # Create data directory if it doesn't exist
        data_dir = getattr(settings, 'MOVIE_DATA_DIR', os.path.join(settings.BASE_DIR, 'data'))
        os.makedirs(data_dir, exist_ok=True)
        
        # File paths
        movies_file = os.path.join(data_dir, 'movies.json')
        genres_file = os.path.join(data_dir, 'genres.json')
        
        # Check if files already exist
        if not force and os.path.exists(movies_file) and os.path.exists(genres_file):
            self.stdout.write(self.style.WARNING('Movie data files already exist. Use --force to overwrite.'))
            return
        
        # Download genres
        self.stdout.write('Downloading genres...')
        genres = self.download_genres()
        
        if not genres:
            self.stdout.write(self.style.ERROR('Failed to download genres. Aborting.'))
            return
        
        # Save genres to file
        with open(genres_file, 'w', encoding='utf-8') as f:
            json.dump(genres, f, indent=2)
        
        self.stdout.write(self.style.SUCCESS(f'Saved {len(genres)} genres to {genres_file}'))
        
        # Download popular movies
        self.stdout.write(f'Downloading {pages} pages of popular movies...')
        movies = self.download_popular_movies(pages)
        
        if not movies:
            self.stdout.write(self.style.ERROR('Failed to download movies. Aborting.'))
            return
        
        # Process movies (add image URLs, etc.)
        for movie in movies:
            self.process_movie(movie, genres)
        
        # Save movies to file
        with open(movies_file, 'w', encoding='utf-8') as f:
            json.dump(movies, f, indent=2)
        
        self.stdout.write(self.style.SUCCESS(f'Saved {len(movies)} movies to {movies_file}'))
    
    def download_genres(self):
        """Download movie genres from TMDB API"""
        url = f"{TMDB_API_URL}/genre/movie/list"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'en-US'
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('genres', [])
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error downloading genres: {e}'))
            return []
    
    def download_popular_movies(self, pages):
        """Download popular movies from TMDB API"""
        all_movies = []
        
        for page in range(1, pages + 1):
            self.stdout.write(f'Downloading page {page} of {pages}...')
            url = f"{TMDB_API_URL}/movie/popular"
            params = {
                'api_key': TMDB_API_KEY,
                'language': 'en-US',
                'page': page
            }
            
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                movies = data.get('results', [])
                
                # Get full movie details for each movie
                for movie in movies:
                    movie_id = movie.get('id')
                    if movie_id:
                        movie_details = self.get_movie_details(movie_id)
                        if movie_details:
                            all_movies.append(movie_details)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error downloading page {page}: {e}'))
        
        return all_movies
    
    def get_movie_details(self, movie_id):
        """Get detailed information for a specific movie"""
        url = f"{TMDB_API_URL}/movie/{movie_id}"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'en-US',
            'append_to_response': 'credits,videos'
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error getting details for movie {movie_id}: {e}'))
            return None
    
    def process_movie(self, movie, genres):
        """Process movie data to add additional information"""
        # Add poster and backdrop URLs
        if movie.get('poster_path'):
            movie['poster_url'] = f"{TMDB_IMAGE_BASE_URL}w500{movie['poster_path']}"
        else:
            movie['poster_url'] = None
            
        if movie.get('backdrop_path'):
            movie['backdrop_url'] = f"{TMDB_IMAGE_BASE_URL}original{movie['backdrop_path']}"
        else:
            movie['backdrop_url'] = None
        
        # Ensure genres is a list of objects
        if 'genre_ids' in movie:
            genre_objects = []
            for genre_id in movie['genre_ids']:
                for genre in genres:
                    if genre['id'] == genre_id:
                        genre_objects.append(genre)
                        break
            movie['genres'] = genre_objects
            del movie['genre_ids']

