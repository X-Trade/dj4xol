try:
    from django.conf.urls import url
except ImportError:
    from django.urls import re_path as url

import dj4xol.legacy_starmap
from . import views

app_name = 'dj4xol'

urlpatterns = [
    url(r'^$', views.gamelist, name='index'),
    url(r'^signup/$', views.signup, name='signup'),
    url(r'^register/$', views.register, name='register'),
    url(r'^create-race/$', views.create_race, name='create_race'),
    url(r'^create-game/$', views.create_game, name='create_game'),
    url(r'^(?P<game_id>[0-9]+)/$', views.starmap, name='game'),
    url(r'^(?P<game_id>[0-9]+)/join/$', views.join_game, name='join_game'),
    url(r'^(?P<game_id>[0-9]+)/turn-in/$', views.turn_in, name='turn_in'),
    url(r'^(?P<game_id>[0-9]+)/generate/$', views.generate_turn, name='generate_turn'),
    url(r'^(?P<game_id>[0-9]+)/debug/colonize/(?P<star_id>[0-9]+)/$', views.debug_colonize, name='debug_colonize'),
    url(r'^(?P<game_id>[0-9]+)/debug/create-fleet/$', views.debug_create_fleet, name='debug_create_fleet'),
]

