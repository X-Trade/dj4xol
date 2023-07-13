try:
    from django.conf.urls import url
except ImportError:
    from django.urls import re_path as url

import dj4xol.legacy_starmap
from . import views


urlpatterns = [
    url(r'^(?P<game_id>[0-9]+)/$', views.starmap, name='game'),
    url(r'^(?P<game_id>[0-9]+)/join/$', views.join_game, name='join_game'),
    url('', views.gamelist, name='index'),
]

