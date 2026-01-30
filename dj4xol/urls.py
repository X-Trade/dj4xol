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
]

