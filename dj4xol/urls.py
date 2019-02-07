try:
    from django.conf.urls import url
except ImportError:
    from django.urls import re_path as url

from . import views


urlpatterns = [
    url(r'^$', views.starmap, name='map')
]

