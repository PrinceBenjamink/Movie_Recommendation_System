from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('movie/<int:movie_id>/', views.movie_detail, name='movie_detail'),
    path('search/', views.search, name='search'),
    path('filter/', views.movie_filter, name='movie_filter'),
    path('filter/ajax/', views.movie_filter_ajax, name='movie_filter_ajax'),
    path('watchlist/', views.watchlist, name='watchlist'),
    path('add-to-watchlist/<int:movie_id>/', views.add_to_watchlist, name='add_to_watchlist'),
    path('remove-from-watchlist/<int:movie_id>/', views.remove_from_watchlist, name='remove_from_watchlist'),
    path('recommendations/', views.recommendations, name='recommendations'),
    path('actor/<int:actor_id>/', views.actor_movies, name='actor_movies'),
    path('profile/', views.profile, name='profile'),
]


