from django.contrib import messages
from django.urls import path, include

urlpatterns = [
    path('', include('game.urls')),
]
