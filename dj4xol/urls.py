try:
    from django.conf.urls import url
except ImportError:
    from django.urls import re_path as url

import dj4xol.legacy_starmap
from . import views

app_name = 'dj4xol'

urlpatterns = [
    url(r'^$', views.gamelist, name='index'),
    url(r'^gallery/$', views.gallery, name='gallery'),
    url(r'^signup/$', views.signup, name='signup'),
    url(r'^register/$', views.register, name='register'),
    url(r'^onboarding/theme/$', views.onboarding_theme, name='onboarding_theme'),
    url(r'^onboarding/race/$', views.onboarding_race, name='onboarding_race'),
    url(r'^profile/$', views.profile, name='profile'),
    url(r'^profile/theme/$', views.update_theme, name='update_theme'),
    url(r'^profile/email-preferences/$', views.update_email_preferences, name='update_email_preferences'),
    url(r'^profile/test-email-rollup/$', views.test_email_rollup, name='test_email_rollup'),
    url(r'^profile/test-generic-email/$', views.test_generic_email, name='test_generic_email'),
    url(r'^unsubscribe/(?P<key>[0-9a-f]{32})/$', views.unsubscribe_email, name='unsubscribe_email'),
    url(r'^create-race/$', views.create_race, name='create_race'),
    url(r'^create-game/$', views.create_game, name='create_game'),
    url(r'^hulls/$', views.hull_design_list, name='hull_design_list'),
    url(r'^hulls/new/$', views.hull_design_edit, name='hull_design_new'),
    url(r'^hulls/(?P<hull_id>\d+)/edit/$', views.hull_design_edit, name='hull_design_edit'),
    url(r'^api/account-lookup/$', views.account_lookup, name='account_lookup'),
    url(r'^help/$', views.help_index, name='help_index'),
    url(r'^help/colony/$', views.help_colony, name='help_colony'),
    url(r'^help/fleet-composition/$', views.help_fleet_composition, name='help_fleet_composition'),
    url(r'^help/research-labs/$', views.help_research_labs, name='help_research_labs'),
    url(r'^help/anomalies/$', views.help_anomalies, name='help_anomalies'),
    url(r'^help/secret-resources/$', views.help_secret_resources, name='help_secret_resources'),
    url(r'^help/space-combat/$', views.help_space_combat, name='help_space_combat'),
    url(r'^help/invasion/$', views.help_invasion, name='help_invasion'),
    url(r'^help/technology/$', views.help_technology, name='help_technology'),
    url(r'^help/version-history/$', views.help_version_history, name='help_version_history'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/$', views.starmap, name='game'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/join/$', views.join_game, name='join_game'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/spectate/$', views.spectate_starmap, name='spectate_game'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/spectate/confirm/$', views.spectate_game_confirm, name='spectate_game_confirm'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/turn-in/$', views.turn_in, name='turn_in'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/status/$', views.game_status, name='game_status'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/play/bootstrap/$', views.play_cli_bootstrap, name='play_cli_bootstrap'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/play/command/$', views.play_cli_command, name='play_cli_command'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/generate/$', views.generate_turn, name='generate_turn'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/debug/colonize/(?P<star_short_id>[0-9a-z]{12})/$', views.debug_colonize, name='debug_colonize'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/debug/create-fleet/$', views.debug_create_fleet, name='debug_create_fleet'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/debug/create-anomaly/(?P<fleet_short_id>[0-9a-z]{12})/$', views.debug_create_anomaly, name='debug_create_anomaly'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/debug/generate-report/(?P<object_short_id>[0-9a-z]{12})/$', views.admin_generate_report, name='admin_generate_report'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/production/add/$', views.add_production_order, name='add_production'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/production/remove/(?P<order_short_id>[0-9a-z]{12})/$', views.remove_production_order, name='remove_production'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/production/repeat/(?P<order_short_id>[0-9a-z]{12})/$', views.toggle_production_order_repeat, name='toggle_production_order_repeat'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/fleet-order/add/$', views.add_fleet_order, name='add_fleet_order'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/fleet-order/remove/(?P<order_short_id>[0-9a-z]{12})/$', views.remove_fleet_order, name='remove_fleet_order'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/fleet-order/repeat/(?P<order_short_id>[0-9a-z]{12})/$', views.toggle_fleet_order_repeat, name='toggle_fleet_order_repeat'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/objects-at/(?P<x>\d+)/(?P<y>\d+)/$', views.objects_at_location, name='objects_at_location'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/messages/$', views.message_history, name='message_history'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/research/$', views.research, name='research'),
    url(r'^(?P<game_short_id>[0-9a-z]{8})/rename/(?P<object_short_id>[0-9a-z]{12})/$', views.rename_object, name='rename_object'),
]
