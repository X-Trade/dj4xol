"""testsite URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf.urls import url, include
from dj4xol import views as dj4xol_views

urlpatterns = [
    url(r'^$', dj4xol_views.gamelist, name='root'),
    url(r'^gallery/$', dj4xol_views.gallery, name='root_gallery'),
    url(r'^admin/', admin.site.urls),
    url(r'^4x/', include('dj4xol.urls', namespace='dj4xol')),
    url(
        r'^accounts/password_reset/$',
        dj4xol_views.Dj4xolPasswordResetView.as_view(),
        name='password_reset',
    ),
    url(
        r'^accounts/reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>.+)/$',
        dj4xol_views.Dj4xolPasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    url(r'^accounts/', include('django.contrib.auth.urls'))
]
