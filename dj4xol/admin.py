from django.contrib import admin
from django.utils.html import format_html
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from datetime import datetime
try:
    from django.conf.urls import url
except ImportError:
    from django.urls import re_path as url

from .models import Player, Game, ServerSettings, ServerRaceType
from .turn import GameTurn

@admin.register(ServerRaceType)
class ServerRaceTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'enabled')

@admin.register(ServerSettings)
class ServerAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'description', 'modified')
    readonly_fields = ('key', 'description', 'modified', 'modified_by')
    
    def save_model(self, request, obj, form, change):
        obj.modified_by = request.user
        obj.modified = datetime.now()
        obj.save()

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('pk', 'django_user', 'full_name', 'alias', 'email')
    readonly_fields = ('pk', 'django_user')

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('pk', 'name', 'owner', 'year', 'game_actions')
    readonly_fields = ('pk', 'year', 'game_actions')
    list_select_related = ('owner',)

    def get_urls(self):
        urls = super().get_urls()
        extra_urls = [url( r'^(?P<game_id>.+)/generate/$',
            self.admin_site.admin_view(self.generate_turn),
            name='generate-turn')]
        return extra_urls + urls

    def game_actions(self, obj):
        return format_html('<a class="button" href="{}">Generate</a>',
            reverse('admin:generate-turn', args=[obj.pk]))

    game_actions.short_description = 'Actions'
    game_actions.allow_tags = True

    def generate_turn(self, request, game_id):
        GameTurn(Game.objects.get(pk=game_id)).generate()
        url = reverse('admin:dj4xol_game_change', args=[game_id],
            current_app=self.admin_site.name)
        return HttpResponseRedirect(url)
