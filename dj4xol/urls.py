try:
    from django.conf.urls import url
except ImportError:
    from django.urls import re_path as url

from . import views


urlpatterns = [
    url(r'^(?P<game_id>[0-9]+)/$', views.starmap, name='map')
]

