from django.contrib import admin, messages
from django.utils.html import format_html
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from datetime import datetime
try:
    from django.conf.urls import url
except ImportError:
    from django.urls import re_path as url

from .models import (
    Account, Player, Game, ServerSettings, ServerRaceType,
    DefaultResearchLevelRequirement, ResearchCategory, ResearchLevelRequirement,
    Technology, PlayerResearch,
)
from .research import copy_default_requirements_to_category, ensure_default_level_requirements
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

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('pk', 'django_user', 'full_name', 'alias', 'email')

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing account
            return ('pk', 'django_user')
        return ()  # Creating new account - allow django_user selection

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('pk', 'short_id', 'game', 'account', 'name')
    readonly_fields = ('pk',)
    list_select_related = ('game', 'account')

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('pk', 'name', 'owner', 'year', 'game_actions')
    readonly_fields = ('pk', 'year', 'game_actions')
    list_select_related = ('owner',)

    def get_urls(self):
        urls = super().get_urls()
        extra_urls = [url(r'^(?P<game_id>.+)/generate/$',
            self.admin_site.admin_view(self.generate_turn_view),
            name='generate-turn')]
        return extra_urls + urls

    def game_actions(self, obj):
        return format_html('<a class="button" href="{}">Generate</a>',
            reverse('admin:generate-turn', args=[obj.pk]))

    game_actions.short_description = 'Actions'
    game_actions.allow_tags = True

    def generate_turn_view(self, request, game_id):
        GameTurn(Game.objects.get(pk=game_id)).generate_turn()
        url = reverse('admin:dj4xol_game_change', args=[game_id],
            current_app=self.admin_site.name)
        return HttpResponseRedirect(url)


class TechnologyInline(admin.TabularInline):
    model = Technology
    extra = 0
    fields = (
        'level', 'name', 'tech_type', 'enabled', 'display_order', 'params_json'
    )


class ResearchLevelRequirementInline(admin.TabularInline):
    model = ResearchLevelRequirement
    extra = 0
    fields = (
        'level', 'rp_cost', 'ironium_cost', 'boranium_cost', 'germanium_cost'
    )
    ordering = ('level',)


@admin.register(ResearchCategory)
class ResearchCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'display_order', 'enabled')
    list_filter = ('enabled',)
    search_fields = ('code', 'name')
    inlines = [TechnologyInline, ResearchLevelRequirementInline]
    actions = ['sync_requirements_from_defaults']

    def save_model(self, request, obj, form, change):
        super(ResearchCategoryAdmin, self).save_model(request, obj, form, change)
        ensure_default_level_requirements()
        copy_default_requirements_to_category(obj)

    def sync_requirements_from_defaults(self, request, queryset):
        ensure_default_level_requirements()
        count = 0
        for category in queryset:
            copy_default_requirements_to_category(
                category, ensure_defaults=False, overwrite_existing=True
            )
            count += 1
        self.message_user(
            request,
            'Synced research level requirements from defaults for %s categor%s.' % (
                count, 'y' if count == 1 else 'ies'
            ),
            level=messages.SUCCESS
        )
    sync_requirements_from_defaults.short_description = (
        'Sync selected category requirements from default table'
    )


@admin.register(Technology)
class TechnologyAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'level', 'tech_type', 'enabled', 'display_order'
    )
    list_filter = ('category', 'tech_type', 'enabled')
    search_fields = ('name', 'description')


@admin.register(PlayerResearch)
class PlayerResearchAdmin(admin.ModelAdmin):
    list_display = (
        'player_display', 'category', 'current_level', 'stored_rp', 'allocation_percent'
    )
    list_filter = ('category', 'player__game')
    search_fields = (
        'player__name',
        'player__short_id',
        'player__account__alias',
        'player__account__django_user__username',
        'category__name',
    )
    list_select_related = ('player__account', 'player__account__django_user', 'player__game', 'category')

    @staticmethod
    def _format_player_label(player):
        account = player.account.alias if player.account_id else 'No account'
        game_name = player.game.name if player.game_id else 'No game'
        return '%s | %s | %s | %s' % (player.name, account, game_name, player.short_id)

    def player_display(self, obj):
        return self._format_player_label(obj.player)
    player_display.short_description = 'Player'
    player_display.admin_order_field = 'player__name'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super(PlayerResearchAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'player':
            field.queryset = field.queryset.select_related('account', 'game')
            field.label_from_instance = self._format_player_label
        return field


@admin.register(DefaultResearchLevelRequirement)
class DefaultResearchLevelRequirementAdmin(admin.ModelAdmin):
    list_display = (
        'level', 'rp_cost', 'ironium_cost', 'boranium_cost', 'germanium_cost'
    )
    ordering = ('level',)
