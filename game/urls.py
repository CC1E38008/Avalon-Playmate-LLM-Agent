from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('setup/', views.setup_game, name='setup'),
    path('game/<str:game_id>/', views.game_page, name='game'),
    path('api/game/<str:game_id>/state/', views.game_state_api, name='game_state_api'),
    path('api/game/<str:game_id>/action/', views.game_action, name='game_action'),
    path('api/game/<str:game_id>/result/', views.game_result_api, name='game_result_api'),
    path('game/<str:game_id>/result/', views.result_page, name='result'),
]
