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
    url(r'^(?P<game_short_id>[a-f0-9]{8})/$', views.starmap, name='game'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/join/$', views.join_game, name='join_game'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/turn-in/$', views.turn_in, name='turn_in'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/generate/$', views.generate_turn, name='generate_turn'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/debug/colonize/(?P<star_short_id>[a-f0-9]{12})/$', views.debug_colonize, name='debug_colonize'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/debug/create-fleet/$', views.debug_create_fleet, name='debug_create_fleet'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/production/add/$', views.add_production_order, name='add_production'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/production/remove/(?P<order_short_id>[a-f0-9]{12})/$', views.remove_production_order, name='remove_production'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/fleet-order/add/$', views.add_fleet_order, name='add_fleet_order'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/fleet-order/remove/(?P<order_short_id>[a-f0-9]{12})/$', views.remove_fleet_order, name='remove_fleet_order'),
    url(r'^(?P<game_short_id>[a-f0-9]{8})/messages/$', views.message_history, name='message_history'),
]

