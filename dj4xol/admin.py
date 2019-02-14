from django.contrib import admin
from django.utils.html import format_html
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
try:
    from django.conf.urls import url
except ImportError:
    from django.urls import re_path as url

from .models import Player, Game
from .data import GameTurn


admin.site.register(Player)

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'owner', 'year', 'game_actions')
    readonly_fields = ('id', 'name', 'owner', 'year', 'game_actions')
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
