from django.urls import path, include
from django.contrib.auth import views as auth_views
from movies import views as movie_views

urlpatterns = [
    # Remove admin path
    path('', include('movies.urls')),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('accounts/register/', movie_views.register, name='register'),
]
