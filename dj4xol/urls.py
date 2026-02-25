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
    url(r'^onboarding/theme/$', views.onboarding_theme, name='onboarding_theme'),
    url(r'^onboarding/race/$', views.onboarding_race, name='onboarding_race'),
    url(r'^profile/$', views.profile, name='profile'),
    url(r'^profile/theme/$', views.update_theme, name='update_theme'),
    url(r'^create-race/$', views.create_race, name='create_race'),
    url(r'^create-game/$', views.create_game, name='create_game'),
    url(r'^api/account-lookup/$', views.account_lookup, name='account_lookup'),
    url(r'^help/$', views.help_index, name='help_index'),
    url(r'^help/colony/$', views.help_colony, name='help_colony'),
    url(r'^help/fleet-composition/$', views.help_fleet_composition, name='help_fleet_composition'),
    url(r'^help/research-labs/$', views.help_research_labs, name='help_research_labs'),
    url(r'^help/space-combat/$', views.help_space_combat, name='help_space_combat'),
    url(r'^help/invasion/$', views.help_invasion, name='help_invasion'),
    url(r'^help/technology/$', views.help_technology, name='help_technology'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/$', views.starmap, name='game'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/join/$', views.join_game, name='join_game'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/turn-in/$', views.turn_in, name='turn_in'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/status/$', views.game_status, name='game_status'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/generate/$', views.generate_turn, name='generate_turn'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/debug/colonize/(?P<star_short_id>[0-9a-z]{12})/$', views.debug_colonize, name='debug_colonize'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/debug/create-fleet/$', views.debug_create_fleet, name='debug_create_fleet'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/production/add/$', views.add_production_order, name='add_production'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/production/remove/(?P<order_short_id>[0-9a-z]{12})/$', views.remove_production_order, name='remove_production'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/fleet-order/add/$', views.add_fleet_order, name='add_fleet_order'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/fleet-order/remove/(?P<order_short_id>[0-9a-z]{12})/$', views.remove_fleet_order, name='remove_fleet_order'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/objects-at/(?P<x>\d+)/(?P<y>\d+)/$', views.objects_at_location, name='objects_at_location'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/messages/$', views.message_history, name='message_history'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/research/$', views.research, name='research'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/rename/(?P<object_short_id>[0-9a-z]{12})/$', views.rename_object, name='rename_object'),
]
