from django.db import models, transaction
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import resolve, reverse
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
import os
import json
import random
import uuid
from urllib.parse import urlencode, urlparse

from dj4xol.objectdetails import DetailBuilder
from dj4xol.secret_resources import SECRET_RESOURCE_KEYS, get_secret_resource_label
from dj4xol.mineral_rules import ALL_RESOURCE_KEYS, known_resource_keys

from .models import (
    Game, Player, ServerSettings, ServerRace, ServerRaceType, Account, GameInvitation, Fleet,
    FleetOrders, Star, Salvage, Anomaly, Report, ResearchCategory, Technology,
    ResearchLevelPrerequisite, HullDesign, HullDesignSlot, random_anomaly_stability_init,
    Spectator, PlayerDiplomaticStance, PlayerStarMarker, profanity_filter_settings, server_setting_enabled,
    server_setting_int, DiplomaticContract, CustomHelpPage,
)
from .email_rollups import (
    send_message_rollup_for_account,
    send_generic_test_email_for_account,
    send_email_verification_for_account,
    send_game_deleted_email,
    send_game_join_email,
)
from .decorators import registration_required, player_only_view
from .play_cli_web import (
    build_bootstrap_transcript,
    enforce_browser_rate_limit,
    execute_browser_command,
)
from .turn import GameTurn
from .research import (
    build_research_screen_data, update_player_allocations, set_even_allocations,
    set_singular_allocation, get_global_research_max_level,
    get_starting_tech_balance_costs, build_production_cost_entries,
    get_player_available_production_orders, get_player_unlocked_technologies,
)
from .ai_players import (
    build_random_ai_race_template,
    normalize_ai_module_code,
    resolve_ai_slot_stance,
)
from .diplomacy import (
    STANCE_ALLIED,
    STANCE_CHOICES,
    STANCE_COLD,
    STANCE_HOSTILE,
    build_stance_map,
    build_pending_stance_map,
    combat_chance_modifier_percent,
    combat_chance_percent,
    encountered_players,
    has_encountered_player,
    normalise_stance,
    player_can_refuel_fleet,
    player_pending_default_stance,
    stance_effect_items,
    stance_label,
    stance_towards,
    update_player_stances,
)
from .diplomatic_contracts import (
    _resolve_report_target,
    accept_contract,
    build_player_message_feed,
    decline_contract,
    diplomatic_actions_locked,
    ensure_specific_colony_report,
    ensure_specific_fleet_report,
    extend_contract,
    format_contract_statement,
    format_contract_summary,
    mark_countered,
    pair_contracts,
    resource_label_for_player,
    revoke_contract,
)
from .technology_thumbnails import (
    get_technology_thumbnail_initial_index,
    get_technology_thumbnail_path,
    get_technology_thumbnail_paths,
)
from .technology_gate_rules import (
    describe_race_type_requirement,
    race_type_requirement_viewer_status,
)
from .ship_thumbnail_catalog import SHIP_THUMBNAILS_BY_CLASS
from .starmap import StarMap
from .factory import GameFactory
from .forms import (
    ServerRaceForm,
    NewGameForm,
    RegistrationForm,
    ChangeEmailForm,
    AccountPasswordChangeForm,
    JoinGameForm,
    PasswordResetRequestForm,
    PasswordResetSetForm,
    ServerSettingsForm,
    CustomHelpPageForm,
    CustomHelpPageBlockFormSet,
)
from .name_rules import validate_safe_public_text
from .player_labels import player_name_with_bracket
from .scanners import get_scanner_sources_for_player


RACE_TYPE_PERCENT_FIELDS = [
    ('population_growth_multiplier', 'Population Growth'),
    ('manufacturing_multiplier', 'Manufacturing'),
    ('combat_multiplier', 'Combat'),
    ('defence_multiplier', 'Defence'),
    ('bombardment_multiplier', 'Bombardment'),
    ('ground_force_multiplier', 'Ground Forces'),
    ('diplomacy_multiplier', 'Diplomacy'),
    ('scan_multiplier', 'Scanners'),
    ('shield_multiplier', 'Shields'),
    ('stealth_multiplier', 'Stealth'),
    ('terraforming_multiplier', 'Terraforming'),
    ('political_stability', 'Political Stability'),
    ('luck_multiplier', 'Luck'),
    ('research_multiplier', 'Research'),
    ('initiative_multiplier', 'Initiative'),
    ('cargo_multiplier', 'Cargo'),
]
RACE_TYPE_ADDITIVE_FIELDS = [
    ('warp_advantage', 'Warp Advantage'),
]
RACE_TYPE_INTEGER_FIELDS = [
    ('starting_colonies', 'Starting Colonies', 1),
    ('starting_economy', 'Starting Economy', 2),
    ('economy_offset', 'Economy Offset', 0),
    ('population_cap_multiplier', 'Population Cap', 1),
]
RACE_TYPE_POINT_FIELDS = [
    ('race_creation_points_balance', 'Race Balance Points'),
]
RACE_TYPE_BOOLEAN_FIELDS = [
    ('population_growth_uses_resources', 'Growth Uses Resources', True, False),
    ('starting_planet_has_stargate', 'Start With Stargate', True, False),
    ('ignores_radiation', 'Ignores Radiation', True, False),
    ('ignores_temperature', 'Ignores Temperature', True, False),
    ('ignores_gravity', 'Ignores Gravity', True, False),
    ('has_no_terraforming', 'No Terraforming', True, False),
    ('only_basic_terraforming', 'Only Basic Terraforming', True, False),
    ('has_advanced_mines', 'Advanced Mines', True, False),
    ('has_advanced_stargates', 'Advanced Stargates', True, False),
    ('has_advanced_remoteminers', 'Advanced Remote Miners', True, False),
    ('has_advanced_hulls', 'Advanced Hulls', True, False),
    ('has_superweapon', 'Superweapon', True, False),
    ('has_bombs', 'Bombs', False, True),
    ('has_metalurgy', 'Metallurgy', False, True),
    ('has_no_stealth', 'No Stealth Systems', True, False),
    ('has_generalised_research', 'Generalised Research', True, False),
    ('is_parasitic', 'Parasitic', True, False),
    ('is_cybernetic', 'Cybernetic', True, False),
    ('is_mechanical', 'Mechanical', True, False),
    ('is_energy_being', 'Energy Being', True, False),
]


def _format_signed_percent(value):
    try:
        percent = int(round((float(value) - 1.0) * 100.0))
    except (TypeError, ValueError):
        percent = 0
    return '%+d%%' % percent


def _race_type_detail_rows(race_type):
    rows = []
    if not race_type:
        return rows
    for field_name, label in RACE_TYPE_PERCENT_FIELDS:
        value = float(getattr(race_type, field_name, 1.0) or 1.0)
        if abs(value - 1.0) < 1e-9:
            continue
        rows.append({'name': label, 'value': _format_signed_percent(value)})
    for field_name, label, default in RACE_TYPE_INTEGER_FIELDS:
        value = int(getattr(race_type, field_name, default) or 0)
        if value == default:
            continue
        if field_name == 'economy_offset':
            rows.append({'name': label, 'value': '%+d' % value})
        elif field_name == 'population_cap_multiplier':
            rows.append({'name': label, 'value': '%dx' % value})
        else:
            rows.append({'name': label, 'value': str(value)})
    for field_name, label in RACE_TYPE_POINT_FIELDS:
        try:
            value = float(getattr(race_type, field_name, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if abs(value) < 1e-9:
            continue
        rows.append({'name': label, 'value': '%+.2f pts' % value})
    for field_name, label, active_value, default_value in RACE_TYPE_BOOLEAN_FIELDS:
        value = bool(getattr(race_type, field_name, default_value))
        if value != active_value:
            continue
        rows.append({'name': label, 'value': 'Yes'})
    for field_name, label in RACE_TYPE_ADDITIVE_FIELDS:
        try:
            value = float(getattr(race_type, field_name, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if abs(value) < 1e-9:
            continue
        rows.append({'name': label, 'value': '%+g' % value})
    return rows


def _race_type_special_technology_rows(race_type):
    rows = []
    if not race_type:
        return rows
    tech_type_labels = dict(Technology.TECH_TYPE_CHOICES)
    technologies = Technology.objects.select_related('category').filter(
        enabled=True,
    ).order_by('level', 'display_order', 'name', 'id')
    for tech in technologies:
        try:
            params = json.loads(getattr(tech, 'params_json', '') or '{}')
        except (TypeError, ValueError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        expression = params.get('race_type')
        if expression in (None, ''):
            continue
        status = race_type_requirement_viewer_status(expression, race_type)
        if status is None:
            continue
        rows.append({
            'name': tech.name,
            'level': int(getattr(tech, 'level', 0) or 0),
            'type': tech_type_labels.get(tech.tech_type, tech.tech_type),
            'thumbnail_path': get_technology_thumbnail_path(tech),
            'thumbnail_paths': get_technology_thumbnail_paths(tech),
            'thumbnail_initial_index': get_technology_thumbnail_initial_index(tech),
            'is_excluded': status == 'excluded',
        })
    return rows


def _race_type_behavior_map():
    return {
        race_type.code: {
            'description': race_type.description or '',
            'ignores_gravity': bool(getattr(race_type, 'ignores_gravity', False)),
            'ignores_temperature': bool(getattr(race_type, 'ignores_temperature', False)),
            'ignores_radiation': bool(getattr(race_type, 'ignores_radiation', False)),
            'race_creation_points_balance': float(
                getattr(race_type, 'race_creation_points_balance', 0.0) or 0.0
            ),
        }
        for race_type in ServerRaceType.objects.filter(enabled=True)
    }


def _account_onboarding_redirect_name(account):
    if not account:
        return None
    step = getattr(account, 'onboarding_step', Account.ONBOARDING_STEP_COMPLETE)
    if step == Account.ONBOARDING_STEP_THEME:
        return 'dj4xol:onboarding_theme'
    if step == Account.ONBOARDING_STEP_RACE:
        return 'dj4xol:onboarding_race'
    return None


class Dj4xolPasswordResetView(auth_views.PasswordResetView):
    form_class = PasswordResetRequestForm


class Dj4xolPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    form_class = PasswordResetSetForm


def _race_type_return_target(return_to):
    if return_to == 'onboarding_race':
        return ('dj4xol:onboarding_race', 'Back to Race Creation')
    if return_to == 'create_race':
        return ('dj4xol:create_race', 'Back to Race Creation')
    return (None, None)


def _build_player_movement_paths(game, player):
    """Build ordered movement segments for player's fleets.

    Each segment is chained from fleet position through queued movement
    destinations so the map can render planned routes.
    """
    if not player:
        return []

    movement_types = {'MOVE', 'INTERCEPT', 'PATROL', 'COLONISE', 'BOMB', 'REMOTEMINE', 'MERGE'}
    segments = []
    fleets = (
        player.fleets.filter(game=game)
        .prefetch_related(
            'orders',
            'orders__target_star',
            'orders__target_fleet',
            'orders__target_salvage',
        )
        .order_by('name', 'id')
    )
    for fleet in fleets:
        current_x = int(fleet.x)
        current_y = int(fleet.y)
        orders = sorted(
            [o for o in fleet.orders.all() if o.order_type in movement_types],
            key=lambda item: (int(item.position or 0), str(item.id)),
        )
        for order in orders:
            _, target_x, target_y, kind = order.get_actual_target()
            if kind in ('none', 'invalid'):
                continue
            if target_x is None or target_y is None:
                continue
            target_x = int(target_x)
            target_y = int(target_y)
            if target_x == current_x and target_y == current_y:
                continue
            segments.append({
                'fleet_short_id': fleet.short_id,
                'from_x': current_x,
                'from_y': current_y,
                'to_x': target_x,
                'to_y': target_y,
            })
            current_x, current_y = target_x, target_y
    return segments


def _build_selected_fleet_patrol_circles(selected_obj, player):
    """Return patrol circles for selected owned fleet orders."""
    if not selected_obj or not isinstance(selected_obj, Fleet):
        return []
    if not player or selected_obj.player != player:
        return []

    circles = []
    orders = selected_obj.orders.filter(order_type='PATROL').order_by('position', 'id')
    for order in orders:
        _, target_x, target_y, kind = order.get_actual_target()
        if kind in ('none', 'invalid') or target_x is None or target_y is None:
            continue
        try:
            radius = int(order.patrol_radius or 0)
        except (TypeError, ValueError):
            radius = 0
        if radius < 0:
            radius = 0
        circles.append({
            'center_x': int(target_x),
            'center_y': int(target_y),
            'radius': radius,
        })
    return circles


def _build_scanner_circles(game, player):
    if getattr(game, 'no_scanners', False):
        return [], []
    sources = get_scanner_sources_for_player(game, player) if player else []
    basic = []
    advanced = []
    for src in sources:
        basic_range = int(src.get('basic') or 0)
        adv_range = int(src.get('advanced') or 0)
        if basic_range > 0:
            basic.append({
                'center_x': int(src.get('x')),
                'center_y': int(src.get('y')),
                'radius': basic_range,
            })
        if adv_range > 0:
            advanced.append({
                'center_x': int(src.get('x')),
                'center_y': int(src.get('y')),
                'radius': adv_range,
            })
    return basic, advanced


def _player_explored_anomaly_ids(game, player):
    if not player:
        return set()
    return set(
        Report.objects.filter(
            game=game,
            player=player,
            target_type='anomaly',
        ).values_list('target_id', flat=True)
    )


def _build_wormhole_links(game, player):
    """Return visible wormhole link segments for map overlay rendering."""
    explored_ids = _player_explored_anomaly_ids(game, player)
    if not explored_ids:
        return []
    links = []
    seen = set()
    wormholes = Anomaly.objects.filter(
        game=game,
        anomaly_type=Anomaly.TYPE_WORMHOLE,
        wormhole_pair__isnull=False,
    ).select_related('wormhole_pair')
    for anomaly in wormholes:
        pair = anomaly.wormhole_pair
        if not pair:
            continue
        key = tuple(sorted([str(anomaly.id), str(pair.id)]))
        if key in seen:
            continue
        seen.add(key)
        if anomaly.id not in explored_ids or pair.id not in explored_ids:
            continue
        links.append({
            'a_short_id': anomaly.short_id,
            'b_short_id': pair.short_id,
            'ax': int(anomaly.x),
            'ay': int(anomaly.y),
            'bx': int(pair.x),
            'by': int(pair.y),
        })
    return links


def _setting_enabled(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _allow_self_signup():
    value = ServerSettings.get('allow_self_signup', None)
    if value is None:
        # Backward-compatible fallback.
        value = ServerSettings.get('server_allow_registration', 'True')
    return _setting_enabled(value, default=True)


def _spectator_mode_enabled():
    value = ServerSettings.get('enable_spectator_mode', None)
    return _setting_enabled(value, default=True)


def _debug_actions_enabled():
    value = ServerSettings.get('enable_debug_actions', 'False')
    return _setting_enabled(value, default=False)


def _game_list_status(game, player=None):
    if getattr(game, 'is_generating', False):
        return 'Generating...'
    if player and game.turn_scheme == 'QUORUM' and player.turned_in:
        return 'Turned in'
    return game.get_turn_scheme_short_display()


def _build_game_list_entries(games, player_by_game_id=None):
    entries = []
    player_by_game_id = player_by_game_id or {}
    for game in games:
        player = player_by_game_id.get(game.id)
        entries.append({
            'game': game,
            'status': _game_list_status(game, player=player),
        })
    return entries


def _play_cli_web_enabled():
    value = ServerSettings.get('enable_play_api', 'True')
    return _setting_enabled(value, default=True)


def _is_same_origin_request(request):
    origin = (request.META.get('HTTP_ORIGIN') or '').strip()
    if not origin:
        return False
    parsed = urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
        return False
    current_origin = '%s://%s' % (request.scheme, request.get_host())
    return origin.rstrip('/') == current_origin.rstrip('/')


def gamelist(request):
    """Index / landing page.

    - Authenticated + registered users see their game dashboard.
    - Anonymous users see a public landing page.
    """
    if not request.user.is_authenticated:
        return render(request, 'dj4xol/landing.html', _landing_context(request))

    if not hasattr(request.user, 'dj4xol_account'):
        return redirect('dj4xol:register')

    account = request.user.dj4xol_account
    onboarding_redirect = _account_onboarding_redirect_name(account)
    if onboarding_redirect:
        return redirect(onboarding_redirect)
    playing_players = list(
        Player.objects.filter(account=account, game__ended=False).select_related('game')
    )
    playing_game_ids = [player.game_id for player in playing_players]
    player_by_game_id = {
        player.game_id: player for player in playing_players
    }
    spectating_game_ids = set(
        Spectator.objects.filter(account=account).values_list('game_id', flat=True)
    )

    my_games = [player.game for player in playing_players]
    open_games = list(
        Game.objects.filter(public=True, ended=False).exclude(pk__in=playing_game_ids)
    )

    # Games I'm invited to (by account or email) that I haven't joined yet
    invited_games = list(Game.objects.filter(
        pk__in=GameInvitation.objects.filter(
            models.Q(account=account) | models.Q(email=account.email)
        ).values('game'),
        ended=False
    ).exclude(pk__in=playing_game_ids))

    return render(request, 'dj4xol/games.html', {
        'account': account,
        'my_game_entries': _build_game_list_entries(
            my_games, player_by_game_id=player_by_game_id
        ),
        'invited_game_entries': _build_game_list_entries(invited_games),
        'open_game_entries': _build_game_list_entries(open_games),
        'spectating_game_ids': spectating_game_ids,
        'spectator_mode_enabled': _spectator_mode_enabled(),
        'server_name': ServerSettings.get('server_name', 'dj4xol'),
        'server_tagline': ServerSettings.get('server_tagline', ''),
        'server_welcome': ServerSettings.get('server_welcome', ''),
    })


def _readme_bullets(section_title):
    """Extract markdown bullet lines from a README section."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    readme_path = os.path.join(repo_root, 'README.md')
    if not os.path.exists(readme_path):
        return []

    with open(readme_path, 'r') as f:
        lines = f.readlines()

    section_start = None
    section_header = '## %s' % section_title
    for idx, line in enumerate(lines):
        if line.strip() == section_header:
            section_start = idx + 1
            break
    if section_start is None:
        return []

    bullets = []
    for line in lines[section_start:]:
        stripped = line.strip()
        if stripped.startswith('## '):
            break
        if stripped.startswith('- '):
            bullets.append(stripped[2:].strip())
    return bullets


def _landing_context(request=None):
    now = timezone.now()
    weekly_cutoff = now - timedelta(days=7)

    active_games_count = (
        Game.objects.filter(ended=False)
        .filter(players__isnull=False)
        .distinct()
        .count()
    )
    weekly_active_players = Account.objects.filter(
        django_user__last_login__gte=weekly_cutoff
    ).count()

    feature_highlights = _readme_bullets('Current State')
    priorities = _readme_bullets('Current Priorities')
    future = _readme_bullets('Future Possibilities')

    if not feature_highlights:
        feature_highlights = [
            'Multi-game server with onboarding, invites, email updates, and spectator mode',
            'Race creation, colony economy, fleet planning, research progression, and turn reports',
            'Space combat, invasions, scanners, and the core turn-resolution loop',
            'Recent MVP extensions including anomalies, secret resources, and wormholes',
            'Open source web UI with Classic, LCARS, Win95, Haxxor, and Retro Arcade themes',
        ]
    if not priorities:
        priorities = [
            'Gameplay and tech tree progression balancing',
            'Diplomacy',
            'Ship design',
            'Trade contracts and negotiation',
            'Colony automation and quality-of-life tools',
        ]
    if not future:
        future = [
            'Expanded ship design and tech tooling',
            'More galaxy-generation modes',
            'Optional AI modules',
            'Endgame research and resources',
            'Enhanced combat resolution',
            'Colony stability and breakaways',
        ]

    canonical_url = '/4x/'
    if request is not None:
        canonical_url = request.build_absolute_uri('/4x/')

    return {
        'server_name': ServerSettings.get('server_name', 'dj4xol'),
        'server_tagline': ServerSettings.get('server_tagline', ''),
        'active_games_count': active_games_count,
        'weekly_active_players': weekly_active_players,
        'allow_self_signup': _allow_self_signup(),
        'feature_highlights': feature_highlights[:8],
        'github_url': ServerSettings.get(
            'server_github_url',
            'https://github.com/X-Trade/dj4xol'
        ),
        'roadmap_priorities': priorities[:8],
        'roadmap_future': future[:8],
        'canonical_url': canonical_url,
    }


def _gallery_context(request=None):
    canonical_url = '/4x/gallery/'
    if request is not None:
        canonical_url = request.build_absolute_uri('/4x/gallery/')

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gallery_dir = os.path.join(
        repo_root, 'dj4xol', 'static', 'dj4xol', 'home', 'images', 'gallery'
    )
    screenshots = []
    allowed_ext = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
    if os.path.isdir(gallery_dir):
        for filename in sorted(os.listdir(gallery_dir)):
            lower = filename.lower()
            if not lower.endswith(allowed_ext):
                continue
            label = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
            screenshots.append({
                'url': '/static/dj4xol/home/images/gallery/%s' % filename,
                'label': label.strip() or filename,
            })

    return {
        'server_name': ServerSettings.get('server_name', 'dj4xol'),
        'server_tagline': ServerSettings.get('server_tagline', ''),
        'canonical_url': canonical_url,
        'github_url': ServerSettings.get(
            'server_github_url',
            'https://github.com/X-Trade/dj4xol'
        ),
        'screenshots': screenshots,
    }


def gallery(request):
    return render(request, 'dj4xol/gallery.html', _gallery_context(request))

@registration_required()
def join_game(request, game_short_id):
    """Join a game with race selection."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    selected_theme = account.theme if account else 'classic'

    if Spectator.objects.filter(game=game, account=account).exists():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'You are already spectating this game and cannot join it.'
        }, status=403)

    if game.players.filter(account=account).exists():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'You are already playing in this game.'
        })

    # Check if invited
    is_invited = game.invitations.filter(
        models.Q(account=account) | models.Q(email=account.email)
    ).exists()

    # Must be joinable OR invited
    if not game.joinable and not is_invited:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game is not open for joining.'
        })

    human_player_count = game.players.filter(is_ai=False).count()
    if game.max_players and human_player_count >= game.max_players:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game is full.'
        })

    if request.method == 'POST':
        form = JoinGameForm(account, request.POST)
        if form.is_valid():
            player = GameFactory(game).join_player(account, form.cleaned_data['race'], invited=is_invited)
            if player:
                send_game_join_email(
                    game,
                    game.owner,
                    account,
                    via_invitation=is_invited,
                )
                # Clean up invitation
                game.invitations.filter(
                    models.Q(account=account) | models.Q(email=account.email)
                ).delete()
                if player.homeworld_id:
                    game_url = reverse('dj4xol:game', kwargs={'game_short_id': game.short_id})
                    return redirect('%s?%s' % (
                        game_url,
                        urlencode({
                            'x': int(player.homeworld.x),
                            'y': int(player.homeworld.y),
                            'sel': player.homeworld.short_id,
                        }),
                    ))
                return redirect('dj4xol:game', game_short_id=game.short_id)
            return render(request, 'dj4xol/forbidden.html', {
                'message': 'Unable to join game.'
            })
    else:
        form = JoinGameForm(account)

    race_refunds = {}
    try:
        from .research import get_starting_tech_balance_cost
    except ImportError:
        get_starting_tech_balance_cost = None
    if get_starting_tech_balance_cost:
        max_allowed = max(0, int(getattr(game, 'max_starting_tech_level', 0) or 0))
        for race in form.fields['race'].queryset:
            requested_level = max(0, int(getattr(race, 'starting_tech_level', 0) or 0))
            effective_level = min(requested_level, max_allowed)
            requested_cost = float(get_starting_tech_balance_cost(requested_level))
            effective_cost = float(get_starting_tech_balance_cost(effective_level))
            refunded_points = max(0.0, requested_cost - effective_cost)
            refund_points = int(round(refunded_points))
            if refund_points > 0:
                refund_destination = (
                    'research' if getattr(race, 'spend_leftover_points_on_research', False)
                    else 'minerals'
                )
            else:
                refund_destination = 'none'
            race_refunds[str(race.pk)] = {
                'starting_level': requested_level,
                'effective_level': effective_level,
                'refund_points': refund_points,
                'refund_destination': refund_destination,
            }

    player_count = human_player_count
    return render(request, 'dj4xol/join_game.html', {
        'form': form,
        'game': game,
        'selected_theme': selected_theme,
        'race_refunds_json': json.dumps(race_refunds),
        'player_count': player_count,
    })


@registration_required()
def spectate_game_confirm(request, game_short_id):
    """Confirm spectator consent for a public game."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    selected_theme = account.theme if account else 'classic'

    if Player.objects.filter(game=game, account=account).exists():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'You are already playing in this game.'
        }, status=403)

    if not _spectator_mode_enabled():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Spectator mode is disabled on this server.'
        }, status=403)

    if not game.public:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game is not open for spectating.'
        }, status=403)

    spectator = Spectator.objects.filter(game=game, account=account).first()
    if spectator:
        return redirect('dj4xol:spectate_game', game_short_id=game.short_id)

    if request.method == 'POST':
        Spectator.objects.create(game=game, account=account)
        return redirect('dj4xol:spectate_game', game_short_id=game.short_id)

    return render(request, 'dj4xol/spectate_confirm.html', {
        'game': game,
        'selected_theme': selected_theme,
    })


@registration_required()
def spectate_starmap(request, game_short_id):
    """Read-only starmap for spectators."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    selected_theme = account.theme if account else 'classic'

    if Player.objects.filter(game=game, account=account).exists():
        return redirect('dj4xol:game', game_short_id=game.short_id)

    if not _spectator_mode_enabled():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Spectator mode is disabled on this server.'
        }, status=403)

    if not game.public:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game is not open for spectating.'
        }, status=403)

    spectator = Spectator.objects.filter(game=game, account=account).first()
    if not spectator:
        return redirect('dj4xol:spectate_game_confirm', game_short_id=game.short_id)

    is_admin_view = bool(request.user.is_staff or request.user.is_superuser)
    allow_foreign_orders_debug = bool(
        _debug_actions_enabled() and is_admin_view
    )
    x = request.GET.get('x', None)
    y = request.GET.get('y', None)
    selected = request.GET.get('sel', None)

    detail_mode = 'spectator_admin' if is_admin_view else 'spectator_basic'
    detail_builder = DetailBuilder(
        game,
        x,
        y,
        selected,
        player=None,
        viewer_account=account,
        detail_mode=detail_mode,
        allow_foreign_orders_debug=allow_foreign_orders_debug,
    )
    detail = detail_builder.build_detail()

    starmap_obj = StarMap(game, None, dest_mode=False, spectator=True)

    selected_object_type = ''
    selected_object_short_id = ''
    suppress_locate = bool(detail.get('suppress_locate')) if detail else False
    if detail and detail.get('selected_id'):
        selected_object_short_id = detail.get('selected_id') or ''
        if detail.get('is_star'):
            selected_object_type = 'star'
        elif detail.get('is_fleet'):
            selected_object_type = 'fleet'
        elif detail.get('is_salvage'):
            selected_object_type = 'salvage'
        elif detail.get('is_anomaly'):
            selected_object_type = 'anomaly'

    return render(request, 'dj4xol/spectator_starmap.html', {
        'game': game,
        'account': account,
        'starmap': starmap_obj,
        'detail': detail,
        'selection': {'x': x, 'y': y, 'sel': selected},
        'selected_object_type': selected_object_type,
        'selected_object_short_id': selected_object_short_id,
        'suppress_locate': suppress_locate,
        'user_theme': selected_theme,
        'movement_paths_json': json.dumps([]),
        'wormhole_links_json': json.dumps([]),
        'scanner_basic_json': json.dumps([]),
        'scanner_advanced_json': json.dumps([]),
        'selected_patrol_circles_json': json.dumps([]),
        'enable_debug_actions': False,
        'is_admin_view': is_admin_view,
    })

@player_only_view()
def starmap(request, game_short_id):
    """
    A rudimentary map viewer.
    """
    game = Game.objects.get(short_id=game_short_id)

    if game.is_generating:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Turn generation is in progress. Please check back later.'
        })

    account = request.user.dj4xol_account
    # Get the Player instance for this account in this game
    player = Player.objects.filter(game=game, account=account).first()

    url = request.path
    x = request.GET.get('x', None)
    y = request.GET.get('y', None)

    selected = request.GET.get('sel', None)
    allow_foreign_orders_debug = bool(
        _debug_actions_enabled() and (
            request.user.is_staff or request.user.is_superuser
        )
    )
    detail_builder = DetailBuilder(
        game,
        x,
        y,
        selected,
        player=player,
        allow_foreign_orders_debug=allow_foreign_orders_debug,
    )
    detail = detail_builder.build_detail()

    # Check for destination selection mode
    dest_mode = request.GET.get('mode') == 'select_destination'
    dest_fleet = request.GET.get('fleet', None)
    dest_warp = request.GET.get('warp', '5')

    # Check for chosen destination (returned from selection mode)
    dest_star_id = request.GET.get('dest_star', None)
    dest_fleet_id = request.GET.get('dest_fleet', None)
    dest_salvage_id = request.GET.get('dest_salvage', None)
    dest_anomaly_id = request.GET.get('dest_anomaly', None)
    dest_x = request.GET.get('dest_x', None)
    dest_y = request.GET.get('dest_y', None)

    # Look up destination name if specified
    dest_name = None
    dest_location = None
    dest_selected_target = None
    if dest_star_id:
        dest_star = Star.objects.filter(short_id=dest_star_id, game=game).first()
        if dest_star:
            dest_name = dest_star.name
            dest_location = (dest_star.x, dest_star.y)
            dest_selected_target = f'star:{dest_star.short_id}'
    elif dest_fleet_id:
        dest_obj = Fleet.objects.filter(short_id=dest_fleet_id, game=game).first()
        if dest_obj:
            dest_name = dest_obj.name
            dest_location = (dest_obj.x, dest_obj.y)
            dest_selected_target = f'fleet:{dest_obj.short_id}'
    elif dest_salvage_id:
        dest_obj = Salvage.objects.filter(short_id=dest_salvage_id, game=game).first()
        if dest_obj:
            dest_name = dest_obj.name
            dest_location = (dest_obj.x, dest_obj.y)
            dest_selected_target = f'salvage:{dest_obj.short_id}'
    elif dest_anomaly_id:
        dest_obj = Anomaly.objects.filter(short_id=dest_anomaly_id, game=game).first()
        if dest_obj:
            dest_name = dest_obj.name
            dest_location = (dest_obj.x, dest_obj.y)
            dest_selected_target = f'anomaly:{dest_obj.short_id}'
    elif dest_x and dest_y:
        try:
            dest_location = (int(dest_x), int(dest_y))
            dest_selected_target = 'space'
        except (TypeError, ValueError):
            dest_location = None
            dest_selected_target = None

    destination_targets = None
    if dest_location:
        exclude_fleet_id = None
        if detail_builder.selected_obj and isinstance(detail_builder.selected_obj, Fleet):
            exclude_fleet_id = detail_builder.selected_obj.id
        destination_targets = detail_builder.get_destination_targets(
            dest_location[0],
            dest_location[1],
            selected_target=dest_selected_target,
            exclude_fleet_id=exclude_fleet_id,
        )

    # Pass dest_mode to StarMap for modified link rendering
    starmap_obj = StarMap(game, player, dest_mode=dest_mode)

    # Get messages for this player, priority first then most recent
    # Filter to messages since messages_seen_year (or all if never seen)
    if player:
        messages = build_player_message_feed(player, limit=1000, include_seen_filter=True)
        # Update last_seen_year for next turn generation
        player.last_seen_year = game.year
        player.save(update_fields=['last_seen_year'])
    else:
        messages = []

    # Get player's homeworld for home button
    homeworld = player.homeworld if player else None
    movement_paths = _build_player_movement_paths(game, player)
    wormhole_links = _build_wormhole_links(game, player)
    scanner_basic, scanner_advanced = _build_scanner_circles(game, player)
    selected_fleet_short_id = None
    selected_object_type = ''
    selected_object_short_id = ''
    suppress_locate = bool(detail.get('suppress_locate')) if detail else False
    selected_patrol_circles = []
    if detail and detail.get('selected_id'):
        selected_object_short_id = detail.get('selected_id') or ''
        if detail.get('is_star'):
            selected_object_type = 'star'
        elif detail.get('is_fleet'):
            selected_object_type = 'fleet'
        elif detail.get('is_salvage'):
            selected_object_type = 'salvage'
        elif detail.get('is_anomaly'):
            selected_object_type = 'anomaly'
    if detail and detail.get('is_fleet') and detail.get('is_owned'):
        selected_fleet_short_id = detail.get('fleet_short_id')
        selected_patrol_circles = _build_selected_fleet_patrol_circles(
            detail_builder.selected_obj, player
        )

    return render(request, 'dj4xol/main.html', {
        'game': game,
        'player': player,
        'starmap': starmap_obj,
        'detail': detail,
        'messages': messages,
        'is_owner': account == game.owner,
        'selection': {'x': x, 'y': y, 'sel': selected},
        'homeworld': homeworld,
        'dest_mode': dest_mode,
        'dest_fleet': dest_fleet,
        'dest_warp': dest_warp,
        'dest_star_id': dest_star_id,
        'dest_fleet_id': dest_fleet_id,
        'dest_salvage_id': dest_salvage_id,
        'dest_anomaly_id': dest_anomaly_id,
        'dest_name': dest_name,
        'dest_x': dest_x,
        'dest_y': dest_y,
        'destination_targets': destination_targets,
        'movement_paths_json': json.dumps(movement_paths),
        'wormhole_links_json': json.dumps(wormhole_links),
        'scanner_basic_json': json.dumps(scanner_basic),
        'scanner_advanced_json': json.dumps(scanner_advanced),
        'selected_fleet_short_id': selected_fleet_short_id or '',
        'selected_object_type': selected_object_type,
        'selected_object_short_id': selected_object_short_id,
        'suppress_locate': suppress_locate,
        'selected_patrol_circles_json': json.dumps(selected_patrol_circles),
        'enable_debug_actions': _debug_actions_enabled(),
        'play_cli_web_enabled': _play_cli_web_enabled(),
    })


@player_only_view()
def turn_in(request, game_short_id):
    """Mark player as turned in for quorum-based games."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()

    if game.turn_scheme != 'QUORUM':
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game does not use quorum-based turns.'
        })

    if game.is_generating:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Turn generation is already in progress.'
        })

    player.turned_in = True
    player.save()

    # Check if quorum is met and generate turn
    turn = GameTurn(game)
    if turn.check_quorum():
        turn.generate_turn()

    return _redirect_preserving_selection(request, game)


@player_only_view()
def generate_turn(request, game_short_id):
    """Generate turn for owner-controlled games."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account

    if game.turn_scheme != 'OWNER':
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game does not use owner-triggered turns.'
        })

    if account != game.owner:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Only the game owner can generate turns.'
        })

    if game.is_generating:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Turn generation is already in progress.'
        })

    GameTurn(game).generate_turn()
    return _redirect_preserving_selection(request, game)


@player_only_view()
def debug_colonize(request, game_short_id, star_short_id):
    """Debug: instantly colonize a star with 1000 colonists."""
    from .models import Star
    game = Game.objects.get(short_id=game_short_id)
    if not _debug_actions_enabled():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Debug actions are disabled.'
        })
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    star = Star.objects.get(short_id=star_short_id, game=game)

    star.player = player
    star.colonists = 1000
    star.save()

    return _redirect_preserving_selection(request, game)


@player_only_view()
def debug_create_fleet(request, game_short_id):
    """Debug: create a fleet at the current x/y location."""
    from .models import Fleet
    game = Game.objects.get(short_id=game_short_id)
    if not _debug_actions_enabled():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Debug actions are disabled.'
        })
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return _redirect_preserving_selection(request, game)

    x = int(request.POST.get('x') or request.GET.get('x') or 0)
    y = int(request.POST.get('y') or request.GET.get('y') or 0)

    fleet = Fleet.objects.create(
        game=game,
        player=player,
        name=f"Fleet {game.fleets.count() + 1}",
        x=x,
        y=y,
    )

    return _redirect_preserving_selection(request, game)


def _spawn_random_anomaly_at(game, x, y):
    anomaly_type = random.choice([
        Anomaly.TYPE_NEBULA,
        Anomaly.TYPE_COMET,
        Anomaly.TYPE_RIFT,
        Anomaly.TYPE_BLACK_HOLE,
        Anomaly.TYPE_WORMHOLE,
    ])
    labels = {
        Anomaly.TYPE_NEBULA: 'Nebula',
        Anomaly.TYPE_COMET: 'Comet',
        Anomaly.TYPE_RIFT: 'Rift',
        Anomaly.TYPE_BLACK_HOLE: 'Black Hole',
        Anomaly.TYPE_WORMHOLE: 'Wormhole',
    }
    if anomaly_type == Anomaly.TYPE_WORMHOLE:
        from .models import random_wormhole_stability_init
        base_index = game.anomalys.count() + 1
        wormhole_name = '%s %s' % (labels.get(anomaly_type, 'Anomaly'), base_index)
        wormhole_pair_name = '%s %s' % (labels.get(anomaly_type, 'Anomaly'), base_index + 1)
        endpoint = Anomaly.objects.create(
            game=game,
            x=int(x),
            y=int(y),
            anomaly_type=anomaly_type,
            name=wormhole_name,
            heading=random.random() * 360.0,
            stability=random_wormhole_stability_init(),
        )
        pair = endpoint
        max_x = max(1, int(game.map_size_x) - 1)
        max_y = max(1, int(game.map_size_y) - 1)
        occupied = set(game.stars.values_list('x', 'y'))
        occupied.update(game.fleets.values_list('x', 'y'))
        occupied.update(game.salvages.values_list('x', 'y'))
        occupied.update(game.anomalys.values_list('x', 'y'))
        for _ in range(120):
            px = random.randint(1, max_x)
            py = random.randint(1, max_y)
            if (px, py) in occupied:
                continue
            pair = Anomaly.objects.create(
                game=game,
                x=px,
                y=py,
                anomaly_type=anomaly_type,
                name=wormhole_pair_name,
                heading=random.random() * 360.0,
                stability=random_wormhole_stability_init(),
            )
            break
        if pair.id == endpoint.id:
            endpoint.delete()
            return Anomaly.objects.create(
                game=game,
                x=int(x),
                y=int(y),
                anomaly_type=Anomaly.TYPE_RIFT,
                name='Rift %s' % (game.anomalys.count() + 1),
                heading=random.random() * 360.0,
                stability=random_anomaly_stability_init(),
            )
        endpoint.wormhole_pair = pair
        endpoint.save(update_fields=['wormhole_pair'])
        pair.wormhole_pair = endpoint
        pair.save(update_fields=['wormhole_pair'])
        return endpoint
    return Anomaly.objects.create(
        game=game,
        x=int(x),
        y=int(y),
        anomaly_type=anomaly_type,
        name='%s %s' % (labels.get(anomaly_type, 'Anomaly'), game.anomalys.count() + 1),
        heading=random.random() * 360.0,
        stability=random_anomaly_stability_init(),
    )


@player_only_view()
def debug_create_anomaly(request, game_short_id, fleet_short_id):
    """Debug: spawn a random anomaly directly on the selected fleet."""
    game = Game.objects.get(short_id=game_short_id)
    if not _debug_actions_enabled():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Debug actions are disabled.'
        })
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if not player:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'No player found for this game.'
        })
    if player.turned_in:
        return _redirect_preserving_selection(request, game)
    fleet = Fleet.objects.filter(
        game=game,
        short_id=fleet_short_id,
        player=player,
    ).first()
    if fleet is None:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Fleet not found.'
        })

    _spawn_random_anomaly_at(game, fleet.x, fleet.y)
    return _redirect_preserving_selection(request, game)


@player_only_view()
def admin_generate_report(request, game_short_id, object_short_id):
    """Admin utility: generate/update a report for selected star or fleet."""
    if request.method != 'POST':
        return _redirect_preserving_selection(request, Game.objects.get(short_id=game_short_id))

    if not _debug_actions_enabled():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Debug actions are disabled.'
        })

    if not request.user.is_staff:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Staff access required.'
        })

    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if not player:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'No player found for this game.'
        })

    target_obj = Star.objects.filter(game=game, short_id=object_short_id).first()
    target_type = 'star'
    if target_obj is None:
        target_obj = Fleet.objects.filter(game=game, short_id=object_short_id).first()
        target_type = 'fleet'
    if target_obj is None:
        target_obj = Salvage.objects.filter(game=game, short_id=object_short_id).first()
        target_type = 'salvage'
    if target_obj is None:
        target_obj = Anomaly.objects.filter(game=game, short_id=object_short_id).first()
        target_type = 'anomaly'
    if target_obj is None:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Object not found in this game.'
        })

    turn = GameTurn(game)
    report_data = turn._build_report_data(player, target_obj, target_type)
    report, _created = Report.objects.update_or_create(
        player=player,
        target_type=target_type,
        target_id=target_obj.id,
        defaults={
            'game': game,
            'year': game.year,
        }
    )
    report.set_report_data(report_data)
    report.save()

    return _redirect_preserving_selection(request, game)


def _redirect_preserving_selection(request, game, suppress_autolocate=False):
    """Redirect to game view (or explicit target), preserving selection when relevant."""
    from django.urls import reverse
    return_to = request.POST.get('return_to') or request.GET.get('return_to')
    if return_to == 'research':
        url = reverse('dj4xol:research', kwargs={'game_short_id': game.short_id})
        category = request.POST.get('category') or request.GET.get('category')
        if category:
            url = '%s?%s' % (url, urlencode({'category': category}))
        return redirect(url)
    if return_to == 'diplomacy':
        url = reverse('dj4xol:diplomacy', kwargs={'game_short_id': game.short_id})
        target = request.POST.get('target') or request.GET.get('target')
        if target:
            url = '%s?%s' % (url, urlencode({'target': target}))
        return redirect(url)

    url = reverse('dj4xol:game', kwargs={'game_short_id': game.short_id})
    params = {k: request.POST.get(k) or request.GET.get(k)
              for k in ['x', 'y', 'sel'] if request.POST.get(k) or request.GET.get(k)}
    if suppress_autolocate:
        params['no_locate'] = '1'
    if params:
        url = f"{url}?{urlencode(params)}"
    return redirect(url)


@player_only_view()
def add_production_order(request, game_short_id):
    """Add a production order to a star."""
    from .models import Star, ProductionOrder
    from .micromanager_rules import (
        ADMINISTRATION_ONE_OFF_ORDER_TYPES,
        ADMINISTRATION_ORDER_TYPE,
        DYSON_SPHERE_ORDER_TYPE,
        REMOVE_ADMINISTRATION_ORDER_TYPE,
    )
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return _redirect_preserving_selection(request, game)

    star_short_id = request.POST.get('star')
    order_type = request.POST.get('order_type')
    quantity = int(request.POST.get('quantity', 1))
    repeat = request.POST.get('repeat') == 'on'

    if order_type:
        star = Star.objects.get(short_id=star_short_id, game=game, player=player)
        allowed = {
            entry['value'] for entry in get_player_available_production_orders(player, star)
        }
        if order_type not in allowed:
            return _redirect_preserving_selection(request, game)
        if order_type == ADMINISTRATION_ORDER_TYPE:
            if star.has_administration:
                return _redirect_preserving_selection(request, game)
            if star.production_orders.filter(
                order_type=ADMINISTRATION_ORDER_TYPE
            ).exists():
                return _redirect_preserving_selection(request, game)
            quantity = 1
            repeat = False
        elif order_type == REMOVE_ADMINISTRATION_ORDER_TYPE:
            if not star.has_administration:
                return _redirect_preserving_selection(request, game)
            if star.production_orders.filter(
                order_type=REMOVE_ADMINISTRATION_ORDER_TYPE
            ).exists():
                return _redirect_preserving_selection(request, game)
            quantity = 1
            repeat = False
        elif order_type == DYSON_SPHERE_ORDER_TYPE:
            if bool(getattr(star, 'has_dyson_sphere', False)):
                return _redirect_preserving_selection(request, game)
            if star.production_orders.filter(
                order_type=DYSON_SPHERE_ORDER_TYPE
            ).exists():
                return _redirect_preserving_selection(request, game)
            quantity = 1
            repeat = False

        micromanager_orders = list(star.production_orders.filter(
            added_by_micromanager=True
        ).order_by('-position', '-id'))
        if micromanager_orders:
            insert_pos = micromanager_orders[-1].position
            for existing in micromanager_orders:
                existing.position = int(existing.position or 0) + 1
                existing.save(update_fields=['position'])
        else:
            insert_pos = star.production_orders.aggregate(
                max_pos=models.Max('position')
            )['max_pos'] or 0
            insert_pos += 1
        ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type=order_type,
            position=insert_pos,
            quantity=max(1, quantity),
            repeat=repeat,
            added_by_micromanager=False,
        )

    return _redirect_preserving_selection(request, game)


@player_only_view()
def remove_production_order(request, game_short_id, order_short_id):
    """Remove a production order."""
    from .models import ProductionOrder
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return _redirect_preserving_selection(request, game)

    order = ProductionOrder.objects.get(short_id=order_short_id, game=game, star__player=player)
    order.delete()

    return _redirect_preserving_selection(request, game)


@player_only_view()
def toggle_production_order_repeat(request, game_short_id, order_short_id):
    """Toggle repeat flag for a production order."""
    from .models import ProductionOrder
    from .micromanager_rules import ADMINISTRATION_ONE_OFF_ORDER_TYPES

    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return _redirect_preserving_selection(request, game)

    order = ProductionOrder.objects.get(
        short_id=order_short_id, game=game, star__player=player
    )
    if order.order_type in ADMINISTRATION_ONE_OFF_ORDER_TYPES:
        return _redirect_preserving_selection(request, game)
    order.repeat = not bool(order.repeat)
    order.save(update_fields=['repeat'])
    return _redirect_preserving_selection(request, game)


@player_only_view()
def add_fleet_order(request, game_short_id):
    """Add a movement or transfer order to a fleet."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return _redirect_preserving_selection(
            request,
            game,
            suppress_autolocate=True,
        )

    fleet_short_id = request.POST.get('fleet')
    order_type = request.POST.get('order_type', 'MOVE')
    repeat = request.POST.get('repeat') == 'on'
    edit_order_short_id = (request.POST.get('edit_order') or '').strip().lower()

    # Verify fleet belongs to player
    fleet = Fleet.objects.get(short_id=fleet_short_id, game=game, player=player)

    if edit_order_short_id:
        order = FleetOrders.objects.get(
            short_id=edit_order_short_id,
            game=game,
            fleet=fleet,
        )
        if order.order_type in {'MOVE', 'INTERCEPT'} or order_type in {'MOVE', 'INTERCEPT'}:
            return _redirect_preserving_selection(
                request,
                game,
                suppress_autolocate=True,
            )
        order.order_type = order_type
        order.repeat = repeat
        order.warpfactor = 0
        order.original_warpfactor = None
        order.overmax_risk_checked = False
        order.x = None
        order.y = None
        order.target_kind = None
        order.target_short_id = None
        order.target_star = None
        order.target_fleet = None
        order.target_salvage = None
        order.transfer_type = None
        order.transfer_ironium = 0
        order.transfer_boranium = 0
        order.transfer_germanium = 0
        order.transfer_resource_x = 0
        order.transfer_resource_y = 0
        order.transfer_resource_z = 0
        order.transfer_colonists = 0
        order.transfer_fuel = 0.0
        order.transfer_player = None
        order.patrol_radius = 0
        order.intercept_speed = 5
        order.patrol_generated = False
        order.bomb_until = 'COLONISTS_ZERO'
        order.mine_until_full = True
        order.remotemine_focus = ''
        order.added_by_micromanager = False
    else:
        # Create order based on type
        order = FleetOrders(game=game, fleet=fleet, order_type=order_type, repeat=repeat)
    
    if order_type in ['MOVE', 'INTERCEPT']:
        target_star_id = request.POST.get('target_star')
        target_fleet_id = request.POST.get('target_fleet')
        target_salvage_id = request.POST.get('target_salvage')
        target_anomaly_id = request.POST.get('target_anomaly')
        target_x = request.POST.get('target_x')
        target_y = request.POST.get('target_y')
        default_warpfactor = fleet.max_safe_warp
        if order_type == 'MOVE':
            try:
                cloaked_warp = int(getattr(fleet, 'max_cloaked_warp', -1) or 0)
            except (TypeError, ValueError):
                cloaked_warp = -1
            if cloaked_warp > 0:
                default_warpfactor = min(int(fleet.max_safe_warp or 0), cloaked_warp)
        warpfactor = int(request.POST.get('warpfactor', default_warpfactor))
        warpfactor = max(0, min(14, warpfactor))
        if warpfactor == 14 and (order_type == 'INTERCEPT' or not fleet.has_wormhole_drive):
            warpfactor = 13
        order.warpfactor = warpfactor
        order.original_warpfactor = warpfactor
        order.overmax_risk_checked = False

        if target_star_id:
            order.target_star = Star.objects.get(short_id=target_star_id, game=game)
        elif target_fleet_id:
            order.target_fleet = Fleet.objects.get(short_id=target_fleet_id, game=game)
        elif target_salvage_id:
            order.target_salvage = Salvage.objects.get(short_id=target_salvage_id, game=game)
        elif target_anomaly_id:
            order.target_kind = 'OBJECT'
            order.target_short_id = target_anomaly_id
        elif target_x and target_y:
            order.x = int(target_x)
            order.y = int(target_y)

        if order_type == 'INTERCEPT' and not order.target_fleet and not order.target_short_id:
            order.order_type = 'MOVE'

    elif order_type == 'REFUEL':
        target_fleet_id = request.POST.get('target_fleet')
        if not target_fleet_id:
            return _redirect_preserving_selection(
                request,
                game,
                suppress_autolocate=True,
            )
        try:
            order.target_fleet = Fleet.objects.get(short_id=target_fleet_id, game=game)
        except Fleet.DoesNotExist:
            return _redirect_preserving_selection(
                request,
                game,
                suppress_autolocate=True,
            )
        if order.target_fleet_id == fleet.id:
            return _redirect_preserving_selection(
                request,
                game,
                suppress_autolocate=True,
            )
        if not player_can_refuel_fleet(
            fleet.player,
            order.target_fleet.player,
            stance_map=build_stance_map(fleet.player),
        ):
            return _redirect_preserving_selection(
                request,
                game,
                suppress_autolocate=True,
            )
        try:
            requested_fuel = float(request.POST.get('transfer_fuel', 0) or 0.0)
        except (TypeError, ValueError):
            requested_fuel = 0.0
        order.transfer_fuel = max(0.0, requested_fuel)
        order.target_star = None
        order.target_salvage = None
        order.target_kind = None
        order.target_short_id = None
        order.x = None
        order.y = None

    elif order_type == 'PATROL':
        target_star_id = request.POST.get('target_star')
        target_fleet_id = request.POST.get('target_fleet')
        target_salvage_id = request.POST.get('target_salvage')
        target_anomaly_id = request.POST.get('target_anomaly')
        target_x = request.POST.get('target_x')
        target_y = request.POST.get('target_y')
        patrol_target = request.POST.get('patrol_target', '')

        order.patrol_radius = int(request.POST.get('patrol_radius', 15))
        intercept_speed = int(request.POST.get('intercept_speed', fleet.max_safe_warp))
        intercept_speed = max(0, min(14, intercept_speed))
        if intercept_speed == 14:
            intercept_speed = 13
        order.intercept_speed = intercept_speed

        if patrol_target and ':' in patrol_target:
            target_type, target_id = patrol_target.split(':', 1)
            if target_type == 'star':
                order.target_star = Star.objects.get(short_id=target_id, game=game)
            elif target_type == 'fleet':
                order.target_fleet = Fleet.objects.get(short_id=target_id, game=game)
            elif target_type == 'salvage':
                order.target_salvage = Salvage.objects.get(short_id=target_id, game=game)
            elif target_type == 'anomaly':
                order.target_kind = 'OBJECT'
                order.target_short_id = target_id
        elif patrol_target in ['empty', 'space'] and target_x and target_y:
            order.x = int(target_x)
            order.y = int(target_y)
        elif target_star_id:
            order.target_star = Star.objects.get(short_id=target_star_id, game=game)
        elif target_fleet_id:
            order.target_fleet = Fleet.objects.get(short_id=target_fleet_id, game=game)
        elif target_salvage_id:
            order.target_salvage = Salvage.objects.get(short_id=target_salvage_id, game=game)
        elif target_anomaly_id:
            order.target_kind = 'OBJECT'
            order.target_short_id = target_anomaly_id
        elif target_x and target_y:
            order.x = int(target_x)
            order.y = int(target_y)

    
    elif order_type == 'TRANSFER':
        transfer_type = request.POST.get('transfer_type', 'LOAD')
        transfer_target = request.POST.get('transfer_target', '')

        order.transfer_type = transfer_type
        order.transfer_ironium = int(request.POST.get('transfer_ironium', 0))
        order.transfer_boranium = int(request.POST.get('transfer_boranium', 0))
        order.transfer_germanium = int(request.POST.get('transfer_germanium', 0))
        order.transfer_resource_x = int(request.POST.get('transfer_resource_x', 0))
        order.transfer_resource_y = int(request.POST.get('transfer_resource_y', 0))
        order.transfer_resource_z = int(request.POST.get('transfer_resource_z', 0))
        order.transfer_colonists = int(request.POST.get('transfer_colonists', 0))

        # Parse transfer target: "star:abc123", "fleet:def456", or "salvage:ghi789"
        if transfer_target and ':' in transfer_target:
            target_type, target_id = transfer_target.split(':', 1)
            if target_type == 'star':
                order.target_star = Star.objects.get(short_id=target_id, game=game)
            elif target_type == 'fleet':
                order.target_fleet = Fleet.objects.get(short_id=target_id, game=game, player=player)
            elif target_type == 'salvage':
                order.target_salvage = Salvage.objects.get(short_id=target_id, game=game)
        else:
            target_x = request.POST.get('target_x', '')
            target_y = request.POST.get('target_y', '')
            if target_x and target_y:
                order.x = int(target_x)
                order.y = int(target_y)

    elif order_type == 'GIVE':
        order.repeat = False
        transfer_player_short_id = (request.POST.get('transfer_player', '') or '').strip().lower()
        if transfer_player_short_id:
            target_player = Player.objects.filter(
                short_id=transfer_player_short_id,
                game=game,
                defeated=False,
            ).first()
            if not target_player:
                return _redirect_preserving_selection(
                    request,
                    game,
                    suppress_autolocate=True,
                )
            if target_player.id == player.id:
                return _redirect_preserving_selection(
                    request,
                    game,
                    suppress_autolocate=True,
                )
            if not has_encountered_player(player, target_player):
                return _redirect_preserving_selection(
                    request,
                    game,
                    suppress_autolocate=True,
                )
            order.transfer_player = target_player

    elif order_type == 'COLONISE':
        # Colonise orders always have repeat=False (fleet is destroyed)
        order.repeat = False
        colonise_target = request.POST.get('colonise_target', '')

        # Colonise target must be a star
        if colonise_target:
            order.target_star = Star.objects.get(short_id=colonise_target, game=game)

    elif order_type == 'BOMB':
        # Bombardment persists and executes each year while queued.
        if not fleet.has_bombs:
            return _redirect_preserving_selection(
                request,
                game,
                suppress_autolocate=True,
            )
        bomb_until = (request.POST.get('bomb_until', 'COLONISTS_ZERO') or '').strip().upper()
        if bomb_until == 'CONTINUOUS':
            bomb_until = 'ONCE'
        if bomb_until not in {'COLONISTS_ZERO', 'DEFENSES_ZERO', 'ONCE'}:
            bomb_until = 'COLONISTS_ZERO'
        order.bomb_until = bomb_until
        bomb_target = request.POST.get('bomb_target', '')
        if bomb_target:
            order.target_star = Star.objects.get(short_id=bomb_target, game=game)

    elif order_type == 'REMOTEMINE':
        if not fleet.has_miners:
            return _redirect_preserving_selection(
                request,
                game,
                suppress_autolocate=True,
            )
        mine_until_full_raw = (request.POST.get('mine_until_full', '1') or '').strip().lower()
        order.mine_until_full = mine_until_full_raw not in {'0', 'false', 'off', 'no'}
        remotemine_target = request.POST.get('remotemine_target', '')
        if remotemine_target:
            order.target_star = Star.objects.get(short_id=remotemine_target, game=game)
        focus_raw = (request.POST.get('remotemine_focus', '') or '').strip()
        focus_keys = []
        if focus_raw:
            focus_keys = [
                key.strip().lower()
                for key in focus_raw.replace(';', ',').split(',')
                if key.strip()
            ]
            focus_keys = [key for key in focus_keys if key in ALL_RESOURCE_KEYS]
        if str(fleet.has_miners).strip().upper() == 'LARGE' and focus_keys:
            if order.target_star:
                allowed = set(known_resource_keys(player, order.target_star))
                focus_keys = [key for key in focus_keys if key in allowed]
            order.remotemine_focus = ','.join(focus_keys)
        else:
            order.remotemine_focus = ''

    elif order_type == 'MERGE':
        # Merge orders always have repeat=False (fleet is deleted on merge)
        order.repeat = False
        merge_target = request.POST.get('merge_target', '')

        # Merge target must be a fleet belonging to the same player
        if merge_target:
            order.target_fleet = Fleet.objects.get(
                short_id=merge_target, game=game, player=player
            )

    elif order_type == 'SCUTTLE':
        # Scuttle orders always have repeat=False (fleet is destroyed)
        order.repeat = False

    target_obj, target_x, target_y, target_kind = order.get_actual_target()
    if target_kind in ('star', 'fleet', 'salvage', 'anomaly') and target_obj is not None:
        order.target_kind = 'OBJECT'
        order.target_short_id = target_obj.short_id
        order.x = target_x
        order.y = target_y
    elif target_kind == 'space':
        order.target_kind = 'SPACE'
        order.target_short_id = None
        order.x = target_x
        order.y = target_y
    else:
        order.target_kind = None
        order.target_short_id = None

    order.save()

    return _redirect_preserving_selection(
        request,
        game,
        suppress_autolocate=True,
    )


@player_only_view()
def remove_fleet_order(request, game_short_id, order_short_id):
    """Remove a fleet movement order."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return _redirect_preserving_selection(request, game)

    # Verify order's fleet belongs to player
    order = FleetOrders.objects.get(short_id=order_short_id, game=game, fleet__player=player)
    order.delete()

    return _redirect_preserving_selection(request, game)


@player_only_view()
def toggle_fleet_order_repeat(request, game_short_id, order_short_id):
    """Toggle repeat flag for a fleet order."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return _redirect_preserving_selection(request, game)

    order = FleetOrders.objects.get(short_id=order_short_id, game=game, fleet__player=player)
    if order.order_type in ['COLONISE', 'MERGE', 'SCUTTLE', 'GIVE']:
        return _redirect_preserving_selection(request, game)

    order.repeat = not bool(order.repeat)
    order.save(update_fields=['repeat'])
    return _redirect_preserving_selection(request, game)


@registration_required()
def delete_owned_game(request, game_short_id):
    """Delete a game from the owner's profile list."""
    account = request.user.dj4xol_account
    game = get_object_or_404(Game, short_id=game_short_id, owner=account)
    if request.method == 'POST':
        notified_account_ids = set()
        for player_account in Account.objects.filter(
            players__game=game
        ).exclude(pk=account.pk).distinct():
            if player_account.pk in notified_account_ids:
                continue
            notified_account_ids.add(player_account.pk)
            send_game_deleted_email(game, account, player_account)
        game.delete()
    return redirect('dj4xol:profile')


def _can_publish_public_races(user):
    if user and user.is_staff:
        return True
    return server_setting_enabled('allow_player_public_races', False)


def _public_server_races_available():
    return ServerRace.objects.filter(public=True, owner__isnull=True).exists()


def _render_race_form_page(request, account, race=None):
    selected_theme = account.theme if account else 'classic'
    show_public = _can_publish_public_races(request.user)
    selected_race_type = request.GET.get('race_type')
    is_edit_mode = race is not None
    if request.method == 'POST':
        form = ServerRaceForm(
            request.POST,
            instance=race,
            show_public=show_public,
        )
        if form.is_valid():
            saved_race = form.save(commit=False)
            saved_race.owner = None if (request.user.is_staff and saved_race.public) else account
            saved_race.save()
            if account and getattr(account, 'onboarding_step', Account.ONBOARDING_STEP_COMPLETE) != Account.ONBOARDING_STEP_COMPLETE:
                account.onboarding_step = Account.ONBOARDING_STEP_COMPLETE
                account.save(update_fields=['onboarding_step'])
            return redirect('dj4xol:profile' if is_edit_mode else 'dj4xol:index')
    else:
        form = ServerRaceForm(
            instance=race,
            show_public=show_public,
            selected_race_type=selected_race_type,
        )
    max_level = get_global_research_max_level()
    return render(request, 'dj4xol/create_race.html', {
        'form': form,
        'selected_theme': selected_theme,
        'race_type_behaviors_json': json.dumps(_race_type_behavior_map()),
        'race_type_browser_url': '%s?%s' % (
            reverse('dj4xol:help_race_types'),
            urlencode({'return_to': 'create_race'}),
        ),
        'starting_tech_costs_json': json.dumps(
            get_starting_tech_balance_costs(max_level=max_level)
        ),
        'is_edit_mode': is_edit_mode,
        'page_title': 'Edit Race' if is_edit_mode else 'Create Race',
        'form_heading': 'Edit Custom Race' if is_edit_mode else 'Create New Race',
        'submit_label': 'Save Race' if is_edit_mode else 'Create Race',
        'cancel_url': reverse('dj4xol:profile' if is_edit_mode else 'dj4xol:index'),
    })


@registration_required()
def create_race(request):
    """Create a new custom race template."""
    account = request.user.dj4xol_account
    return _render_race_form_page(request, account)


@registration_required()
def edit_race(request, race_short_id):
    """Edit a custom race template owned by the current account."""
    account = request.user.dj4xol_account
    race = get_object_or_404(ServerRace, short_id=race_short_id, owner=account)
    return _render_race_form_page(request, account, race=race)


@registration_required()
def delete_race(request, race_short_id):
    """Delete a custom race template owned by the current account."""
    account = request.user.dj4xol_account
    race = get_object_or_404(ServerRace, short_id=race_short_id, owner=account)
    if request.method == 'POST':
        race.delete()
    return redirect('dj4xol:profile')


@registration_required()
def create_game(request):
    """Create a new game."""
    account = request.user.dj4xol_account
    selected_theme = account.theme if account else 'classic'
    if request.method == 'POST':
        form = NewGameForm(account, request.POST)
        if form.is_valid():
            d = form.cleaned_data
            factory = GameFactory()
            factory.game.name = d['name']
            factory.game.description = d.get('description') or ''
            factory.game.year = d['starting_year']
            factory.game.public = d.get('public', False)
            factory.game.joinable = d.get('joinable', False)
            factory.game.max_players = d.get('max_players')
            factory.game.turn_scheme = d['turn_scheme']
            factory.game.years_per_turn = d['years_per_turn']
            factory.game.research_cost_multiplier = d.get('research_cost_multiplier', 1.0)
            factory.game.warp_speed_multiplier = d.get('warp_speed_multiplier', 1.0)
            factory.game.random_events = d.get('random_events', False)
            factory.game.anomalies_enabled = d.get('anomalies_enabled', False)
            factory.game.anomaly_spawn_rate = d.get('anomaly_spawn_rate', 'NORMAL') or 'NORMAL'
            factory.game.no_scanners = d.get('no_scanners', False)
            factory.game.max_starting_tech_level = int(
                d.get('max_starting_tech_level') or 5
            )
            if d.get('join_open_years'):
                factory.game.join_until_year = d['starting_year'] + d['join_open_years']
            factory.set_map_size(d['map_size_x'], d['map_size_y'])
            factory.set_owner(account)
            factory.create_stars(
                d['num_stars'],
                clusters=d.get('clusters', False),
                spiral_arms=d.get('spiral_arms', False),
                systems=d.get('systems', False),
                improved_names=d.get('improved_star_names', False),
            )
            game = factory.save()
            factory.join_player(account, d['race'])
            ai_slots = list(form.parse_ai_player_slots())
            ai_created = 0
            for slot in ai_slots:
                race_for_slot = slot.get('race') or d['race']
                stance_for_slot = resolve_ai_slot_stance(
                    slot.get('default_diplomatic_stance')
                )
                starting_tech_override = slot.get('starting_tech_level')
                if bool(slot.get('race_random')):
                    race_for_slot = build_random_ai_race_template(
                        max_starting_tech_level=int(
                            d.get('max_starting_tech_level') or 5
                        ),
                    )
                    # Random race generation chooses its own balanced starting tech profile.
                    starting_tech_override = None
                ai_player = factory.join_player(
                    None,
                    race_for_slot,
                    invited=True,
                    is_ai=True,
                    ai_module=slot.get('module_code'),
                    starting_tech_level_override=starting_tech_override,
                    default_diplomatic_stance=stance_for_slot,
                )
                if ai_player is not None:
                    ai_created += 1
            if ai_created < len(ai_slots):
                messages.warning(
                    request,
                    'Only %s of %s AI players could be added to this game.'
                    % (ai_created, len(ai_slots)),
                )
            _create_invitations(game, form.parse_invitations(), inviter=account)
            return redirect('dj4xol:game', game_short_id=game.short_id)
    else:
        form = NewGameForm(account)
    return render(request, 'dj4xol/create_game.html', {
        'form': form,
        'selected_theme': selected_theme,
        'ai_slot_editor_payload_json': json.dumps(form.ai_slot_editor_payload()),
    })


def _parse_hull_slot_payload(raw_slots, hull):
    """Parse + validate slot payload JSON for hull layout editor."""
    errors = []
    try:
        payload = json.loads(raw_slots or '[]')
    except (TypeError, ValueError):
        return [], ['Invalid slot JSON payload.']

    if not isinstance(payload, list):
        return [], ['Slot payload must be a list.']

    valid_types = {code for code, _label in _hull_slot_tech_type_choices()}
    valid_item_counts = {1, 2, 4, 8, 16}
    valid_max_levels = set(_hull_slot_level_choices())
    clean_slots = []
    occupied = set()
    max_x = (int(hull.grid_columns) * 2) - 2
    max_y = (int(hull.grid_rows) * 2) - 2

    for idx, slot in enumerate(payload):
        if not isinstance(slot, dict):
            errors.append('Slot #%s is invalid.' % (idx + 1))
            continue

        try:
            x = int(slot.get('x'))
            y = int(slot.get('y'))
            item_count = int(slot.get('item_count'))
            max_tech_level = int(slot.get('max_tech_level'))
        except (TypeError, ValueError):
            errors.append('Slot #%s has non-numeric values.' % (idx + 1))
            continue

        tech_type = str(slot.get('tech_type') or '').strip().upper()
        if tech_type not in valid_types:
            errors.append('Slot #%s has invalid technology type.' % (idx + 1))
            continue
        if item_count not in valid_item_counts:
            errors.append('Slot #%s item count must be one of 1, 2, 4, 8, 16.' % (idx + 1))
            continue
        if max_tech_level not in valid_max_levels:
            errors.append('Slot #%s max tech level is invalid.' % (idx + 1))
            continue
        if x < 0 or y < 0 or x > max_x or y > max_y:
            errors.append('Slot #%s is outside the blueprint bounds.' % (idx + 1))
            continue

        # Slot occupies 2x2 cells in subgrid coordinates.
        footprint = {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}
        if occupied.intersection(footprint):
            errors.append('Slot #%s overlaps another slot.' % (idx + 1))
            continue
        occupied.update(footprint)

        clean_slots.append({
            'x': x,
            'y': y,
            'tech_type': tech_type,
            'item_count': item_count,
            'max_tech_level': max_tech_level,
            'display_order': idx,
        })

    return clean_slots, errors


def _hull_slot_level_choices():
    """Valid slot max levels sourced from configured default level costs."""
    max_level = get_global_research_max_level()
    costs = get_starting_tech_balance_costs(max_level=max_level)
    levels = sorted({int(level) for level in costs.keys() if int(level) >= 0})
    return levels or [0]


def _hull_slot_tech_type_choices():
    disallowed = {'HULL', 'INFRASTRUCTURE'}
    return [
        (code, label)
        for code, label in HullDesignSlot.SLOT_TECH_TYPE_CHOICES
        if code not in disallowed
    ]


def _hull_thumbnail_class_choices(current_value=None):
    classes = sorted([
        key for key in SHIP_THUMBNAILS_BY_CLASS.keys()
        if key and not str(key).startswith('_')
    ])
    if current_value:
        current_value = str(current_value).strip().lower()
        if current_value and current_value not in classes:
            classes.insert(0, current_value)
    return classes


def _hull_thumbnail_paths_by_class(classes):
    result = {}
    for cls in classes:
        result[str(cls)] = list(SHIP_THUMBNAILS_BY_CLASS.get(str(cls), []))
    return result


def _hull_modifier_to_display(value):
    """Convert backend log-coefficient to editor/display units (+10 == 1.0)."""
    try:
        return float(value) * 10.0
    except (TypeError, ValueError):
        return 0.0


def _hull_modifier_from_display(value):
    """Convert editor/display units to backend log-coefficient."""
    return float(value) / 10.0


def _unique_hull_design_name(base_name, technology=None, exclude_hull_id=None):
    """Return a globally unique hull design name."""
    base_name = (base_name or 'Hull').strip() or 'Hull'
    base_name = base_name[:64]
    qs = HullDesign.objects.all()
    if exclude_hull_id is not None:
        qs = qs.exclude(pk=exclude_hull_id)
    if not qs.filter(name=base_name).exists():
        return base_name

    suffix = getattr(technology, 'short_id', '') or 'hull'
    suffix = str(suffix).strip()[:12] or 'hull'
    trimmed = base_name[: max(1, 64 - len(suffix) - 3)].rstrip()
    candidate = '%s [%s]' % (trimmed, suffix)
    if not qs.filter(name=candidate).exists():
        return candidate

    idx = 2
    while True:
        extra = ' %s' % idx
        trimmed = base_name[: max(1, 64 - len(extra))].rstrip()
        candidate = '%s%s' % (trimmed, extra)
        if not qs.filter(name=candidate).exists():
            return candidate
        idx += 1


def _apply_hull_defaults_from_technology(hull, technology, force_name=False):
    """Seed an unsaved hull design from an existing HULL technology."""
    params = _safe_tech_params(technology)
    if force_name or not getattr(hull, 'name', '').strip():
        hull.name = _unique_hull_design_name(
            getattr(technology, 'name', '') or 'Hull',
            technology=technology,
            exclude_hull_id=getattr(hull, 'pk', None),
        )
    hull.thumbnail_class = (
        str(params.get('hull_thumbnail_class') or '').strip().lower() or
        hull.thumbnail_class or
        'scout'
    )
    try:
        hull.offense_offset = float(params.get('offense_level', 0.0) or 0.0)
    except (TypeError, ValueError):
        hull.offense_offset = 0.0
    try:
        hull.defense_offset = float(params.get('defense_level', 0.0) or 0.0)
    except (TypeError, ValueError):
        hull.defense_offset = 0.0
    try:
        hull.speed_advantage = float(params.get('warp_advantage', 0.0) or 0.0)
    except (TypeError, ValueError):
        hull.speed_advantage = 0.0
    try:
        hull.cargo_capacity = int(params.get('max_cargo_capacity', 0) or 0)
    except (TypeError, ValueError):
        hull.cargo_capacity = 0
    try:
        hull.fuel_capacity = int(params.get('max_fuel', 100) or 100)
    except (TypeError, ValueError):
        hull.fuel_capacity = 100
    hull.enabled = bool(getattr(technology, 'enabled', True))


def _sync_hull_technology_from_design(technology, hull):
    """Persist hull-design gameplay values back onto the linked HULL tech."""
    params = _safe_tech_params(technology)
    params['max_cargo_capacity'] = int(hull.cargo_capacity or 0)
    params['max_fuel'] = int(hull.fuel_capacity or 0)
    params['hull_thumbnail_class'] = (
        str(hull.thumbnail_class or '').strip().lower() or 'scout'
    )
    params['offense_level'] = float(hull.offense_offset or 0.0)
    params['defense_level'] = float(hull.defense_offset or 0.0)
    params['warp_advantage'] = float(hull.speed_advantage or 0.0)
    technology.params_json = json.dumps(params, sort_keys=True)


def _backfill_hull_designs_for_hull_techs():
    """Ensure existing HULL tech cards each have a linked hull design."""
    hull_techs = Technology.objects.filter(
        tech_type='HULL',
    ).select_related('hull_design')
    for technology in hull_techs:
        if getattr(technology, 'hull_design', None):
            continue
        hull = HullDesign.objects.filter(
            technology__isnull=True,
            name=technology.name,
        ).order_by('id').first()
        if hull is None:
            hull = HullDesign(technology=technology)
            _apply_hull_defaults_from_technology(
                hull,
                technology,
                force_name=True,
            )
        else:
            hull.technology = technology
        hull.full_clean()
        hull.save()
        _sync_hull_technology_from_design(technology, hull)
        technology.save(update_fields=['params_json'])


def _unlinked_hull_technologies(current_technology=None):
    """Return HULL tech cards not currently attached to a hull design."""
    qs = Technology.objects.filter(tech_type='HULL', hull_design__isnull=True)
    if current_technology is not None and getattr(current_technology, 'pk', None):
        qs = Technology.objects.filter(
            models.Q(tech_type='HULL', hull_design__isnull=True) |
            models.Q(pk=current_technology.pk)
        )
    return list(
        qs.select_related('category').order_by(
            'category__display_order',
            'category__name',
            'level',
            'display_order',
            'name',
        )
    )


@staff_member_required
def hull_design_list(request):
    """Staff-only list of hull designs."""
    account = getattr(request.user, 'dj4xol_account', None)
    return render(request, 'dj4xol/hull_design_list.html', {
        'user_theme': account.theme if account else 'classic',
        'hulls': HullDesign.objects.select_related(
            'technology',
            'technology__category',
        ).prefetch_related('slots').order_by(
            'technology__level',
            'technology__category__display_order',
            'technology__display_order',
            'technology__name',
            'name',
        ),
        'unlinked_hull_techs': _unlinked_hull_technologies(),
    })


@staff_member_required
def hull_design_edit(request, hull_id=None):
    """Staff-only hull layout editor prototype."""
    account = getattr(request.user, 'dj4xol_account', None)
    selected_theme = account.theme if account else 'classic'
    hull = get_object_or_404(HullDesign, pk=hull_id) if hull_id is not None else HullDesign()
    technology = getattr(hull, 'technology', None)
    if technology is None:
        tech_id = request.GET.get('technology')
        if tech_id:
            technology = Technology.objects.filter(
                pk=tech_id,
                tech_type='HULL',
                hull_design__isnull=True,
            ).select_related('category').first()
            if technology is not None:
                _apply_hull_defaults_from_technology(
                    hull,
                    technology,
                    force_name=not bool(hull_id),
                )
        if technology is None:
            technology = Technology(tech_type='HULL', enabled=True)
    errors = []
    thumbnail_class_choices = _hull_thumbnail_class_choices(hull.thumbnail_class)
    offense_offset_display = _hull_modifier_to_display(hull.offense_offset)
    defense_offset_display = _hull_modifier_to_display(hull.defense_offset)
    speed_advantage_display = float(hull.speed_advantage or 0.0)
    tech_categories = list(
        ResearchCategory.objects.filter(enabled=True).order_by(
            'display_order',
            'name',
        )
    )

    if request.method == 'POST':
        technology_id = (request.POST.get('technology_id') or '').strip()
        if technology_id:
            technology = Technology.objects.filter(
                pk=technology_id,
                tech_type='HULL',
            ).select_related('category').first()
            if technology is None:
                errors.append('Selected hull technology could not be found.')
            else:
                try:
                    linked_hull = technology.hull_design
                except Exception:
                    linked_hull = None
                if linked_hull is not None and linked_hull.pk != hull.pk:
                    errors.append('That hull technology already has a hull design.')
        else:
            technology = Technology(tech_type='HULL')

        hull.name = (request.POST.get('name') or '').strip()
        hull.thumbnail_class = (request.POST.get('thumbnail_class') or '').strip().lower()
        hull.enabled = bool(request.POST.get('enabled'))
        try:
            offense_offset_display = float(request.POST.get('offense_offset') or 0)
            defense_offset_display = float(request.POST.get('defense_offset') or 0)
            speed_advantage_display = float(request.POST.get('speed_advantage') or 0)
            hull.offense_offset = _hull_modifier_from_display(offense_offset_display)
            hull.defense_offset = _hull_modifier_from_display(defense_offset_display)
            hull.speed_advantage = speed_advantage_display
            hull.ironium_cost = int(request.POST.get('ironium_cost') or 0)
            hull.boranium_cost = int(request.POST.get('boranium_cost') or 0)
            hull.germanium_cost = int(request.POST.get('germanium_cost') or 0)
            hull.resource_x_cost = int(request.POST.get('resource_x_cost') or 0)
            hull.resource_y_cost = int(request.POST.get('resource_y_cost') or 0)
            hull.resource_z_cost = int(request.POST.get('resource_z_cost') or 0)
            hull.cargo_capacity = int(request.POST.get('cargo_capacity') or 0)
            hull.fuel_capacity = int(request.POST.get('fuel_capacity') or 100)
            hull.cargo_hold_grid_width = int(request.POST.get('cargo_hold_grid_width') or 0)
            hull.cargo_hold_grid_height = int(request.POST.get('cargo_hold_grid_height') or 0)
            # Hull editor currently uses a fixed 8x8 grid for all designs.
            hull.grid_columns = 8
            hull.grid_rows = 8
        except (TypeError, ValueError):
            errors.append('Numeric hull fields contain invalid values.')

        if technology is not None:
            category_id = (request.POST.get('tech_category') or '').strip()
            tech_name = (request.POST.get('tech_name') or '').strip()
            technology.name = tech_name
            technology.description = (request.POST.get('tech_description') or '').strip()
            technology.tech_type = 'HULL'
            technology.enabled = bool(request.POST.get('tech_enabled'))
            try:
                technology.level = int(request.POST.get('tech_level') or 0)
                technology.display_order = int(
                    request.POST.get('tech_display_order') or 0
                )
            except (TypeError, ValueError):
                errors.append('Technology level/order values are invalid.')
            technology.category = ResearchCategory.objects.filter(
                pk=category_id
            ).first()
            if technology.category is None:
                errors.append('Hull technology category is required.')
            if not technology.name:
                errors.append('Hull technology name is required.')

        if not errors:
            try:
                hull.full_clean()
            except Exception as exc:
                if hasattr(exc, 'messages'):
                    errors.extend(exc.messages)
                else:
                    errors.append(str(exc))
        if technology is not None and not errors:
            try:
                technology.full_clean()
            except Exception as exc:
                if hasattr(exc, 'messages'):
                    errors.extend(exc.messages)
                else:
                    errors.append(str(exc))

        if hull.thumbnail_class not in set(thumbnail_class_choices):
            errors.append('Thumbnail class is invalid.')

        slot_payload = request.POST.get('slots_json', '[]')
        clean_slots, slot_errors = _parse_hull_slot_payload(slot_payload, hull)
        errors.extend(slot_errors)
        if not any(slot.get('tech_type') == 'PROPULSION' for slot in clean_slots):
            errors.append('At least one propulsion slot is required.')

        if not errors:
            technology.save()
            hull.technology = technology
            hull.save()
            _sync_hull_technology_from_design(technology, hull)
            technology.save(update_fields=['params_json'])
            HullDesignSlot.objects.filter(hull=hull).delete()
            for slot in clean_slots:
                HullDesignSlot.objects.create(hull=hull, **slot)
            return redirect('dj4xol:hull_design_edit', hull_id=hull.id)

        initial_slots = slot_payload
    else:
        slots = [
            {
                'x': slot.x,
                'y': slot.y,
                'tech_type': slot.tech_type,
                'item_count': slot.item_count,
                'max_tech_level': slot.max_tech_level,
            }
            for slot in hull.slots.all().order_by('display_order', 'id')
        ] if hull.pk else []
        initial_slots = json.dumps(slots)

    return render(request, 'dj4xol/hull_design_edit.html', {
        'selected_theme': selected_theme,
        'hull': hull,
        'technology': technology,
        'errors': errors,
        'secret_resource_labels': {
            key: get_secret_resource_label(key, True)
            for key in SECRET_RESOURCE_KEYS
        },
        'initial_slots_json': initial_slots,
        'tech_type_choices_json': json.dumps([
            {'value': code, 'label': label}
            for code, label in _hull_slot_tech_type_choices()
        ]),
        'item_count_choices_json': json.dumps([1, 2, 4, 8, 16]),
        'max_tech_level_choices_json': json.dumps(_hull_slot_level_choices()),
        'thumbnail_class_choices': thumbnail_class_choices,
        'tech_categories': tech_categories,
        'available_hull_techs': _unlinked_hull_technologies(technology),
        'thumbnail_paths_by_class_json': json.dumps(
            _hull_thumbnail_paths_by_class(thumbnail_class_choices)
        ),
        'offense_offset_display': offense_offset_display,
        'defense_offset_display': defense_offset_display,
        'speed_advantage_display': speed_advantage_display,
    })


@registration_required()
def help_exploration(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_exploration.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_colonising(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_colonising.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_colony_management(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_colony_management.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_mining_salvage(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_mining_salvage.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_colony(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_colony.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_fleet_composition(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_fleet_composition.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_research_labs(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_research_labs.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_anomalies(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_anomalies.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_secret_resources(request):
    account = request.user.dj4xol_account
    from .secret_resources import SECRET_RESOURCE_KEYS, get_secret_resource_label
    resource_labels = []
    for key in SECRET_RESOURCE_KEYS:
        discovered = bool(getattr(account, f'discovered_{key}', False)) if account else False
        resource_labels.append({
            'key': key,
            'label': get_secret_resource_label(key, discovered),
        })
    return render(request, 'dj4xol/help_secret_resources.html', {
        'user_theme': account.theme if account else 'classic',
        'resource_labels': resource_labels,
    })


@registration_required()
def help_space_combat(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_space_combat.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_diplomacy(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_diplomacy.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_race_types(request):
    account = request.user.dj4xol_account
    race_types = list(
        ServerRaceType.objects.filter(enabled=True).order_by('display_order', 'name', 'code')
    )
    selected_code = request.GET.get('race_type')
    selected_race_type = next(
        (race_type for race_type in race_types if race_type.code == selected_code),
        race_types[0] if race_types else None,
    )
    return_to = request.GET.get('return_to')
    return_url_name, return_label = _race_type_return_target(return_to)
    use_type_url = None
    if selected_race_type is not None and return_url_name is not None:
        use_type_url = '%s?%s' % (
            reverse(return_url_name),
            urlencode({'race_type': selected_race_type.code}),
        )
    return render(request, 'dj4xol/help_race_types.html', {
        'user_theme': account.theme if account else 'classic',
        'race_types': race_types,
        'selected_race_type': selected_race_type,
        'effect_rows': _race_type_detail_rows(selected_race_type),
        'special_technology_rows': _race_type_special_technology_rows(selected_race_type),
        'return_url_name': return_url_name,
        'return_label': return_label,
        'use_type_url': use_type_url,
        'return_to': return_to,
    })


@registration_required()
def help_invasion(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_invasion.html', {
        'user_theme': account.theme if account else 'classic',
    })


def _published_custom_help_pages():
    return list(
        CustomHelpPage.objects.filter(published=True).prefetch_related('blocks')
    )


def _custom_help_page_editor_url(page):
    base_url = reverse('dj4xol:help_pages_cms')
    if not page:
        return '%s?page=new' % base_url
    return '%s?page=%s' % (base_url, page.id)


@registration_required()
def custom_help_page(request, slug):
    account = request.user.dj4xol_account
    page = get_object_or_404(
        CustomHelpPage.objects.filter(published=True).prefetch_related('blocks'),
        slug=slug,
    )
    return render(request, 'dj4xol/help_custom_page.html', {
        'user_theme': account.theme if account else 'classic',
        'help_page': page,
    })


@registration_required()
def help_index(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_index.html', {
        'user_theme': account.theme if account else 'classic',
        'custom_help_pages': _published_custom_help_pages(),
    })


@registration_required()
def help_version_history(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_version_history.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_pages_cms(request):
    if not request.user.is_staff:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Staff access is required.',
        }, status=403)

    account = request.user.dj4xol_account
    pages = list(CustomHelpPage.objects.all().prefetch_related('blocks'))
    selected_token = request.GET.get('page') or request.POST.get('page_id')
    selected_page = None
    if selected_token and selected_token != 'new':
        try:
            selected_page = next(
                page for page in pages if page.id == int(selected_token)
            )
        except (StopIteration, TypeError, ValueError):
            selected_page = None
    elif not selected_token and pages:
        selected_page = pages[0]

    preview_page = selected_page
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        if action == 'delete_page':
            if selected_page is None:
                messages.warning(request, 'Select a help page to delete first.')
                return redirect(_custom_help_page_editor_url(None))
            page_title = selected_page.title
            selected_page.delete()
            messages.success(
                request,
                'Deleted help page "%s".' % page_title,
            )
            remaining_page = CustomHelpPage.objects.order_by(
                'nav_order', 'title', 'id'
            ).first()
            return redirect(_custom_help_page_editor_url(remaining_page))

        page_form = CustomHelpPageForm(request.POST, instance=selected_page)
        preview_page = page_form.instance
        block_formset = CustomHelpPageBlockFormSet(
            request.POST,
            instance=selected_page or CustomHelpPage(),
            prefix='blocks',
        )
        if page_form.is_valid():
            page = page_form.save()
            preview_page = page
            block_formset = CustomHelpPageBlockFormSet(
                request.POST,
                instance=page,
                prefix='blocks',
            )
            if block_formset.is_valid():
                with transaction.atomic():
                    block_formset.save()
                messages.success(request, 'Help page saved.')
                return redirect(_custom_help_page_editor_url(page))
            messages.error(
                request,
                'Help page details were saved, but block errors still need attention.',
            )
        else:
            messages.error(request, 'Please correct the highlighted help page fields.')
    else:
        page_form = CustomHelpPageForm(instance=selected_page)
        block_formset = CustomHelpPageBlockFormSet(
            instance=selected_page or CustomHelpPage(),
            prefix='blocks',
        )

    pages = list(CustomHelpPage.objects.all().prefetch_related('blocks'))
    return render(request, 'dj4xol/help_page_cms.html', {
        'user_theme': account.theme if account else 'classic',
        'pages': pages,
        'selected_page': selected_page,
        'page_form': page_form,
        'block_formset': block_formset,
        'preview_page': preview_page,
        'public_preview_url': (
            reverse('dj4xol:custom_help_page', args=[preview_page.slug])
            if preview_page and preview_page.pk and preview_page.published
            else None
        ),
    })


def _format_tech_param_key(key):
    labels = {
        'max_warp_speed': 'Maximum Warp',
        'max_cargo_capacity': 'Cargo Capacity',
        'max_fuel': 'Fuel Capacity',
        'fuel_efficiency': 'Fuel Efficiency',
        'overmax_fuel_penalty': 'Overmax Fuel Penalty',
        'wormhole_destruction_chance': 'Wormhole Destruction Chance',
        'hull_thumbnail_class': 'Hull Class',
        'warp_advantage': 'Warp Advantage',
        'offense_level': 'Offense Level',
        'defense_level': 'Defense Level',
        'colony_defense_level': 'Colony Defense Level',
        'max_cloaked_warp': 'Max Cloaked Warp',
        'advanced_cloak': 'Advanced Cloak',
        'terraforming_rate': 'Terraforming Rate',
        'race_type': 'Race Type',
    }
    return labels.get(key, key.replace('_', ' ').title())


def _format_tech_param_value(key, value):
    if key in ('offense_level', 'defense_level', 'colony_defense_level', 'warp_advantage'):
        try:
            scaled = int(round(float(value) * 10))
            return '{:+d}'.format(scaled)
        except (TypeError, ValueError):
            return value
    if key in ('fuel_efficiency', 'overmax_fuel_penalty'):
        try:
            return '{}%'.format(int(round(float(value) * 100)))
        except (TypeError, ValueError):
            return value
    if key == 'wormhole_destruction_chance':
        try:
            return '{}%'.format(int(round(float(value) * 100)))
        except (TypeError, ValueError):
            return value
    if key == 'hull_thumbnail_class':
        text = str(value or '').strip()
        if not text:
            return value
        return text.replace('_', ' ').title()
    if key == 'terraforming_rate':
        try:
            return '{}%'.format(int(round(float(value) * 100.0)))
        except (TypeError, ValueError):
            return value
    if key == 'advanced_cloak':
        return 'Yes' if bool(value) else 'No'
    if key == 'race_type':
        return describe_race_type_requirement(value)
    return value


def _should_show_tech_param(key, value):
    if key in ('thumbnail_path', 'thumbnail_class', 'thumbnail_cycle', 'thumbnail_paths'):
        return False
    if key == 'advanced_scanner_range':
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return True
    if key == 'advanced_cloak':
        return bool(value)
    if key == 'production_cost_overrides':
        return False
    return True


def _safe_tech_params(tech):
    try:
        data = json.loads(tech.params_json or '{}')
    except (TypeError, ValueError):
        return {}
    if isinstance(data, dict):
        return data
    return {}


@registration_required()
def help_technology(request):
    """Browse technology unlocks by category and level."""
    account = request.user.dj4xol_account
    resource_labels = {
        key: get_secret_resource_label(
            key,
            bool(getattr(account, f'discovered_{key}', False)) if account else False,
        )
        for key in SECRET_RESOURCE_KEYS
    }
    categories = list(
        ResearchCategory.objects.filter(enabled=True).order_by('display_order', 'name')
    )
    selected_category = None
    selected_category_id = request.GET.get('category')
    if selected_category_id:
        try:
            selected_category = next(
                c for c in categories if c.id == int(selected_category_id)
            )
        except (StopIteration, TypeError, ValueError):
            selected_category = None

    min_level = None
    min_level_raw = request.GET.get('min_level')
    if min_level_raw:
        try:
            min_level = max(0, int(min_level_raw))
        except (TypeError, ValueError):
            min_level = None

    max_level = None
    max_level_raw = request.GET.get('max_level')
    if max_level_raw:
        try:
            max_level = max(0, int(max_level_raw))
        except (TypeError, ValueError):
            max_level = None

    tech_type = (request.GET.get('tech_type') or '').strip().upper()
    valid_types = {code for code, _ in Technology.TECH_TYPE_CHOICES}
    if tech_type not in valid_types:
        tech_type = ''

    q = (request.GET.get('q') or '').strip()

    filter_qs = Technology.objects.filter(enabled=True).select_related(
        'category',
        'hull_design',
    )
    if min_level is not None:
        filter_qs = filter_qs.filter(level__gte=min_level)
    if max_level is not None:
        filter_qs = filter_qs.filter(level__lte=max_level)
    if tech_type:
        filter_qs = filter_qs.filter(tech_type=tech_type)
    if q:
        filter_qs = filter_qs.filter(
            models.Q(name__icontains=q) |
            models.Q(description__icontains=q)
        )

    category_counts = {
        row['category_id']: row['count']
        for row in (
            filter_qs.order_by()
            .values('category_id')
            .annotate(count=models.Count('id'))
        )
    }
    for category in categories:
        category.tech_count = category_counts.get(category.id, 0)
    all_count = filter_qs.count()

    tech_qs = filter_qs
    if selected_category is not None:
        tech_qs = tech_qs.filter(category=selected_category)
    tech_rows = list(
        tech_qs.order_by(
            'level',
            'category__display_order',
            'category__name',
            'display_order',
            'name',
        )
    )
    prereq_map = {}
    for prereq in ResearchLevelPrerequisite.objects.select_related(
        'category', 'requires_category'
    ):
        key = (prereq.category_id, prereq.level)
        prereq_map.setdefault(key, []).append(prereq)
    for tech in tech_rows:
        params = _safe_tech_params(tech)
        tech.thumbnail_path = get_technology_thumbnail_path(tech)
        tech.thumbnail_paths = get_technology_thumbnail_paths(tech)
        tech.thumbnail_initial_index = get_technology_thumbnail_initial_index(tech)
        tech.params_display = [
            {
                'label': _format_tech_param_key(key),
                'value': _format_tech_param_value(key, value),
            }
            for key, value in params.items()
            if _should_show_tech_param(key, value)
        ]
        tech.params_display += build_production_cost_entries(params, resource_labels=resource_labels)
        tech.prerequisites = [
            {
                'category': prereq.requires_category,
                'min_level': prereq.min_level,
            }
            for prereq in prereq_map.get((tech.category_id, tech.level), [])
        ]

    tech_type_choices = sorted(
        Technology.TECH_TYPE_CHOICES,
        key=lambda choice: choice[1].lower(),
    )
    return render(request, 'dj4xol/help_technology.html', {
        'user_theme': account.theme if account else 'classic',
        'categories': categories,
        'selected_category': selected_category,
        'selected_category_id': selected_category.id if selected_category else None,
        'min_level': min_level,
        'max_level': max_level,
        'selected_tech_type': tech_type,
        'tech_type_choices': tech_type_choices,
        'search_query': q,
        'all_count': all_count,
        'tech_rows': tech_rows,
    })


def _create_invitations(game, invitations, inviter=None):
    """Create GameInvitation records from parsed invitation list."""
    from .email_rollups import send_game_invite_email
    for inv_type, value in invitations:
        if inv_type == 'email':
            # Check if account exists with this email
            try:
                acct = Account.objects.get(email=value)
                invite, created = GameInvitation.objects.get_or_create(game=game, account=acct)
                if created:
                    send_game_invite_email(
                        game,
                        acct.email,
                        inviter_name=getattr(inviter, 'alias', None),
                    )
            except Account.DoesNotExist:
                invite, created = GameInvitation.objects.get_or_create(game=game, email=value)
                if created:
                    send_game_invite_email(
                        game,
                        value,
                        inviter_name=getattr(inviter, 'alias', None),
                    )
        else:
            # Alias/username lookup
            try:
                acct = Account.objects.get(alias__iexact=value)
                invite, created = GameInvitation.objects.get_or_create(game=game, account=acct)
                if created:
                    send_game_invite_email(
                        game,
                        acct.email,
                        inviter_name=getattr(inviter, 'alias', None),
                    )
                continue
            except Account.DoesNotExist:
                pass
            try:
                acct = Account.objects.get(django_user__username__iexact=value)
                invite, created = GameInvitation.objects.get_or_create(game=game, account=acct)
                if created:
                    send_game_invite_email(
                        game,
                        acct.email,
                        inviter_name=getattr(inviter, 'alias', None),
                    )
            except Account.DoesNotExist:
                pass  # Silently ignore invalid aliases/usernames


@registration_required()
def account_lookup(request):
    """Lookup account aliases/usernames for invite suggestions.

    Security: never return or echo email addresses.
    """
    if request.method != 'GET':
        return JsonResponse({'results': []})

    query = (request.GET.get('q') or '').strip()
    if not query:
        return JsonResponse({'results': []})

    is_email_query = '@' in query
    if not is_email_query and len(query) < 2:
        return JsonResponse({'results': []})

    results = []
    seen_aliases = set()

    if is_email_query:
        # Exact email match only; do not support partial email search.
        acct = Account.objects.select_related('django_user').filter(email__iexact=query).first()
        if acct:
            results.append({
                'alias': acct.alias,
                'username': acct.django_user.username,
                'value': acct.alias,
                'label': f'{acct.alias} ({acct.django_user.username})',
                'match': 'email',
            })
            seen_aliases.add(acct.alias.lower())

    accounts = Account.objects.select_related('django_user').filter(
        models.Q(alias__icontains=query) | models.Q(django_user__username__icontains=query)
    ).order_by('alias')[:10]

    for acct in accounts:
        alias_key = (acct.alias or '').lower()
        if alias_key in seen_aliases:
            continue
        username = acct.django_user.username
        label = acct.alias if acct.alias == username else f'{acct.alias} ({username})'
        results.append({
            'alias': acct.alias,
            'username': username,
            'value': acct.alias,
            'label': label,
            'match': 'alias_or_username',
        })
        seen_aliases.add(alias_key)

    return JsonResponse({'results': results})


@player_only_view()
def message_history(request, game_short_id):
    """View full message history for a player."""
    from django.core.paginator import Paginator
    from .models import GameMessage

    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()

    if not player:
        return render(request, 'dj4xol/message_history.html', {
            'game': game,
            'player': None,
            'page_obj': None,
        })

    messages_qs = player.messages.order_by('-year', '-priority', '-id')

    # Filter by year
    year_filter = request.GET.get('year')
    if year_filter:
        try:
            messages_qs = messages_qs.filter(year=int(year_filter))
        except ValueError:
            pass

    # Filter by category
    category_filter = request.GET.get('category')
    if category_filter:
        messages_qs = messages_qs.filter(category=category_filter)

    # Filter by priority
    priority_only = request.GET.get('priority') == '1'
    if priority_only:
        messages_qs = messages_qs.filter(priority=True)

    # Get available years and categories for filter dropdowns
    all_years = player.messages.values_list('year', flat=True).distinct().order_by('-year')
    categories = GameMessage.CATEGORY_CHOICES

    # Paginate
    from django.core.paginator import EmptyPage, PageNotAnInteger
    paginator = Paginator(messages_qs, 50)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return render(request, 'dj4xol/message_history.html', {
        'game': game,
        'player': player,
        'page_obj': page_obj,
        'all_years': all_years,
        'categories': categories,
        'current_year': year_filter,
        'current_category': category_filter,
        'priority_only': priority_only,
        'user_theme': account.theme if account else 'classic',
        'is_owner': account == game.owner,
    })


@player_only_view()
def research(request, game_short_id):
    """Research budget and allocation view."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()

    if not player:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'You are not a player in this game.'
        })

    selected_category = (
        request.POST.get('category') or request.GET.get('category')
    )
    if request.method == 'POST' and not player.turned_in:
        if player.singular_research:
            next_field_mode = str(request.POST.get('singular_next_field') or '').strip().lower()
            valid_modes = {choice[0] for choice in Player.SINGULAR_RESEARCH_NEXT_FIELD_CHOICES}
            if (
                next_field_mode in valid_modes and
                player.singular_research_next_field != next_field_mode
            ):
                player.singular_research_next_field = next_field_mode
                player.save(update_fields=['singular_research_next_field'])
            focus_category = request.POST.get('focus_category') or selected_category
            set_singular_allocation(player, focus_category)
        elif request.POST.get('alloc_action') == 'even':
            set_even_allocations(player)
        else:
            requested = {}
            for key in request.POST:
                if key.startswith('alloc_'):
                    requested[key[6:]] = request.POST.get(key)
            update_player_allocations(player, requested)
        url = reverse('dj4xol:research', kwargs={'game_short_id': game.short_id})
        if selected_category:
            url = '%s?%s' % (url, urlencode({'category': selected_category}))
        return redirect(url)

    data = build_research_screen_data(player, selected_category)
    return render(request, 'dj4xol/research.html', {
        'game': game,
        'player': player,
        'is_owner': account == game.owner,
        'budget': data['budget'],
        'research_rows': data['rows'],
        'selected_category': data['selected_category'],
        'selected_research': data['selected_research'],
        'current_level_number': data['current_level_number'],
        'next_level_number': data['next_level_number'],
        'next_level_cost': data['next_level_cost'],
        'next_level_rp_current': data['next_level_rp_current'],
        'next_level_rp_met': data['next_level_rp_met'],
        'next_level_progress_percent': data['next_level_progress_percent'],
        'next_level_rp_per_year': data['next_level_rp_per_year'],
        'next_level_eta_years': data['next_level_eta_years'],
        'next_level_requirements': data['next_level_requirements'],
        'next_level_resource_rows': data['next_level_resource_rows'],
        'next_level_prerequisites': data['next_level_prerequisites'],
        'next_level_blocked': data['next_level_blocked'],
        'next_level_items': data['next_level_items'],
        'recently_unlocked_items': data['recently_unlocked_items'],
        'singular_research': player.singular_research,
        'singular_research_next_field': player.singular_research_next_field,
        'singular_research_next_field_choices': Player.SINGULAR_RESEARCH_NEXT_FIELD_CHOICES,
        'user_theme': account.theme if account else 'classic',
    })


def _diplomacy_redirect_url(game_short_id, target=None, extra=None):
    params = {}
    if target:
        params['target'] = target
    if extra:
        params.update(extra)
    base = reverse('dj4xol:diplomacy', kwargs={'game_short_id': game_short_id})
    if not params:
        return base
    return '%s?%s' % (base, urlencode(params))


def _diplomacy_known_resource_choices(player):
    keys = ['ironium', 'boranium', 'germanium', 'colonists']
    for key in SECRET_RESOURCE_KEYS:
        if bool(getattr(player, 'discovered_%s' % key, False)):
            keys.append(key)
    return [(key, resource_label_for_player(player, key)) for key in keys]


def _diplomacy_request_clause_choices():
    return [
        (DiplomaticContract.CLAUSE_NOTHING, 'do nothing'),
        (DiplomaticContract.CLAUSE_TECHNOLOGY, 'grant us technology'),
        (DiplomaticContract.CLAUSE_REPORT, 'grant us report'),
        (DiplomaticContract.CLAUSE_STANCE, 'set their stance to'),
        (DiplomaticContract.CLAUSE_SPECIFIC_COLONY, 'give us colony'),
        (DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD, 'deliver resources'),
        (DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET, 'give us a fleet carrying'),
        (DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT, 'give us a fleet of'),
    ]


def _diplomacy_offer_clause_choices():
    return [
        (DiplomaticContract.CLAUSE_NOTHING, 'do nothing'),
        (DiplomaticContract.CLAUSE_VAGUE_THREAT, 'make vague threats'),
        (DiplomaticContract.CLAUSE_TECHNOLOGY, 'grant them technology'),
        (DiplomaticContract.CLAUSE_REPORT, 'grant them report'),
        (DiplomaticContract.CLAUSE_STANCE, 'set our stance to'),
        (DiplomaticContract.CLAUSE_SPECIFIC_COLONY, 'give them colony'),
        (DiplomaticContract.CLAUSE_SPECIFIC_FLEET, 'give them'),
    ]


def _diplomacy_offer_condition_choices():
    return [
        (DiplomaticContract.CONDITION_EXCHANGE, 'in exchange'),
        (DiplomaticContract.CONDITION_OR_ELSE, 'or else'),
    ]


def _diplomacy_contract_progress(contract, viewer):
    if contract.request_clause_type in (
        DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
        DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
    ):
        parts = []
        for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z', 'colonists'):
            required = int(getattr(contract, 'request_%s' % key, 0) or 0)
            if required <= 0:
                continue
            delivered = int(getattr(contract, 'progress_%s' % key, 0) or 0)
            label = resource_label_for_player(viewer, key)
            unit = 'kt'
            parts.append('%s/%s%s %s' % (delivered, required, unit, label))
        return ', '.join(parts)
    if contract.request_clause_type == DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT:
        return '%s/%s ships' % (
            int(getattr(contract, 'progress_ship_count', 0) or 0),
            int(getattr(contract, 'request_ship_count', 0) or 0),
        )
    return ''


def _diplomacy_player_display_name(player_obj):
    return player_name_with_bracket(
        player_obj,
        name=getattr(player_obj, 'name', None),
        unknown_name='Unknown race',
        unknown_label='Unknown',
    )


def _diplomacy_group_technologies(technologies):
    tech_type_labels = dict(Technology.TECH_TYPE_CHOICES)
    groups = []
    grouped = {}
    for technology in technologies:
        key = technology.tech_type or 'OTHER'
        grouped.setdefault(key, []).append(technology)
    for tech_type, label in Technology.TECH_TYPE_CHOICES:
        techs = grouped.get(tech_type, [])
        if techs:
            groups.append({
                'label': label,
                'items': sorted(techs, key=lambda tech: (tech.level, tech.category.name, tech.display_order, tech.name)),
            })
    return groups


def _diplomacy_known_target_colony_choices(player, target_player):
    if not player or not target_player:
        return []
    known_star_ids = []
    for report in Report.objects.filter(
        game=player.game,
        player=player,
        target_type='star',
    ).order_by('id'):
        try:
            data = report.get_report_data()
        except Exception:
            continue
        if data.get('player_name') == target_player.name:
            known_star_ids.append(report.target_id)
    if not known_star_ids:
        return []
    stars = list(
        target_player.stars.filter(id__in=known_star_ids).order_by('id')
    )
    return stars


def _diplomacy_star_choice_label(star, owner, viewer):
    label = getattr(star, 'name', 'Unknown Colony')
    if getattr(owner, 'homeworld_id', None) and star.id == owner.homeworld_id:
        if viewer is not None and getattr(viewer, 'id', None) == getattr(owner, 'id', None):
            label = '%s (home)' % label
        else:
            label = '%s (their home)' % label
    return label


def _diplomacy_sort_stars_with_homeworld_first(owner, stars):
    homeworld_id = getattr(owner, 'homeworld_id', None)
    return sorted(
        list(stars or []),
        key=lambda star: (0 if homeworld_id and star.id == homeworld_id else 1, star.id),
    )


def _diplomacy_report_item_label(target_type, target, owner=None, viewer=None):
    target_type = str(target_type or '').lower()
    if target_type == 'star':
        if target is None:
            return 'Unknown Colony'
        return _diplomacy_star_choice_label(target, owner, viewer)
    if target_type == 'anomaly':
        return getattr(target, 'name', None) or 'Unknown Anomaly'
    if target_type == 'salvage':
        return getattr(target, 'name', None) or 'Unknown Ancient Debris'
    return 'Unknown report'


def _diplomacy_colony_choice_rows(owner, stars, viewer=None):
    rows = []
    for star in _diplomacy_sort_stars_with_homeworld_first(owner, stars):
        rows.append({
            'id': star.id,
            'label': _diplomacy_star_choice_label(star, owner, viewer),
        })
    return rows


def _diplomacy_report_choice_groups(report_owner, viewer=None):
    groups = []
    if not report_owner:
        return groups

    colony_items = [
        {
            'id': 'star:%s' % star.id,
            'label': _diplomacy_report_item_label('star', star, owner=report_owner, viewer=viewer or report_owner),
        }
        for star in _diplomacy_sort_stars_with_homeworld_first(
            report_owner,
            report_owner.stars.order_by('id'),
        )
    ]
    anomaly_items = []
    ancient_debris_items = []
    seen = {item['id'] for item in colony_items}
    reports = Report.objects.filter(
        game=report_owner.game,
        player=report_owner,
        target_type__in=['star', 'anomaly', 'salvage'],
    ).order_by('target_type', 'year', 'id')
    for report in reports:
        data = report.get_report_data()
        tier = str(data.get('report_tier') or '').lower()
        item_id = '%s:%s' % (report.target_type, report.target_id)
        if item_id in seen:
            continue
        if report.target_type == 'star':
            continue
        if report.target_type == 'anomaly':
            if tier not in ('advanced', 'encounter'):
                continue
            anomaly = _resolve_report_target(report_owner.game, 'anomaly', report.target_id)
            if anomaly is None:
                continue
            anomaly_items.append({
                'id': item_id,
                'label': _diplomacy_report_item_label('anomaly', anomaly),
            })
            seen.add(item_id)
            continue
        if report.target_type == 'salvage':
            if tier not in ('advanced', 'encounter'):
                continue
            salvage = _resolve_report_target(report_owner.game, 'salvage', report.target_id)
            if salvage is None:
                continue
            if data.get('salvage_type') == 'ANCIENT_DEBRIS':
                ancient_debris_items.append({
                    'id': item_id,
                    'label': _diplomacy_report_item_label('salvage', salvage, viewer=viewer or report_owner),
                })
            seen.add(item_id)
    if colony_items:
        groups.append({'label': 'Colonies', 'items': colony_items})
    if anomaly_items:
        groups.append({'label': 'Anomalies', 'items': anomaly_items})
    if ancient_debris_items:
        groups.append({'label': 'Ancient Debris', 'items': ancient_debris_items})
    return groups


def _diplomacy_request_report_choice_groups(requesting_player, target_player):
    if not requesting_player or not target_player:
        return []
    groups = []
    colony_items = [
        {
            'id': 'star:%s' % star.id,
            'label': _diplomacy_report_item_label('star', star, owner=target_player, viewer=requesting_player),
        }
        for star in _diplomacy_sort_stars_with_homeworld_first(
            target_player,
            _diplomacy_known_target_colony_choices(requesting_player, target_player),
        )
    ]
    if colony_items:
        groups.append({'label': 'Colonies', 'items': colony_items})
    other_groups = _diplomacy_report_choice_groups(target_player, viewer=requesting_player)
    for group in other_groups:
        if group['label'] != 'Colonies':
            groups.append(group)
    return groups


def _diplomacy_build_compose_state(player, selected_player, request_obj=None, counter_contract=None):
    state = {
        'temperature': DiplomaticContract.TEMPERATURE_PROPOSE,
        'offer_condition_type': DiplomaticContract.CONDITION_EXCHANGE,
        'request_clause_type': DiplomaticContract.CLAUSE_NOTHING,
        'offer_clause_type': DiplomaticContract.CLAUSE_NOTHING,
        'request_technology': '',
        'request_report_target': '',
        'offer_technology': '',
        'offer_report_target': '',
        'request_stance': 'NEUTRAL',
        'offer_stance': 'NEUTRAL',
        'request_ship_count': '',
        'offer_fleet': '',
        'offer_fleet_include_report': '1',
        'request_suggested_star': '',
        'request_star': '',
        'offer_star': '',
        'deadline_years': '24',
        'extend_on_accept_years': '0',
        'resources': {
            'ironium': '',
            'boranium': '',
            'germanium': '',
            'resource_x': '',
            'resource_y': '',
            'resource_z': '',
            'colonists': '',
        },
    }
    if counter_contract is not None:
        state['temperature'] = counter_contract.temperature
        state['offer_condition_type'] = counter_contract.offer_condition_type
    if request_obj is not None and request_obj.method == 'POST':
        state['temperature'] = request_obj.POST.get('temperature', state['temperature'])
        state['offer_condition_type'] = request_obj.POST.get('offer_condition_type', state['offer_condition_type'])
        state['request_clause_type'] = request_obj.POST.get('request_clause_type', state['request_clause_type'])
        state['offer_clause_type'] = request_obj.POST.get('offer_clause_type', state['offer_clause_type'])
        state['request_technology'] = request_obj.POST.get('request_technology', '')
        state['request_report_target'] = request_obj.POST.get('request_report_target', '')
        state['offer_technology'] = request_obj.POST.get('offer_technology', '')
        state['offer_report_target'] = request_obj.POST.get('offer_report_target', '')
        state['request_stance'] = request_obj.POST.get('request_stance', state['request_stance'])
        state['offer_stance'] = request_obj.POST.get('offer_stance', state['offer_stance'])
        state['request_ship_count'] = request_obj.POST.get('request_ship_count', '')
        state['offer_fleet'] = request_obj.POST.get('offer_fleet', '')
        state['offer_fleet_include_report'] = '1' if request_obj.POST.get('offer_fleet_include_report') else ''
        state['request_suggested_star'] = request_obj.POST.get('request_suggested_star', '')
        state['request_star'] = request_obj.POST.get('request_star', '')
        state['offer_star'] = request_obj.POST.get('offer_star', '')
        state['deadline_years'] = request_obj.POST.get('deadline_years', state['deadline_years'])
        state['extend_on_accept_years'] = request_obj.POST.get('extend_on_accept_years', state['extend_on_accept_years'])
        for key in state['resources']:
            state['resources'][key] = request_obj.POST.get('request_%s' % key, '')
    elif counter_contract is not None:
        state['offer_fleet_include_report'] = (
            '1' if bool(getattr(counter_contract, 'offer_fleet_include_report', True)) else ''
        )
    return state


def _diplomacy_parse_contract(player, target_player, post_data, available_offer_techs,
                               available_request_techs, available_request_stars,
                               available_offer_stars, available_request_reports,
                               available_offer_reports, counter_from=None):
    errors = []
    temperature = post_data.get('temperature', DiplomaticContract.TEMPERATURE_PROPOSE)
    valid_temperatures = {choice[0] for choice in DiplomaticContract.TEMPERATURE_CHOICES}
    if temperature not in valid_temperatures:
        temperature = DiplomaticContract.TEMPERATURE_PROPOSE

    def parse_int(name, default=0):
        raw = (post_data.get(name) or '').strip()
        if raw == '':
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            errors.append('%s must be a whole number.' % name.replace('_', ' ').title())
            return default
        if value < 0:
            errors.append('%s must not be negative.' % name.replace('_', ' ').title())
            return default
        return value

    contract = DiplomaticContract(
        game=player.game,
        sender=player,
        recipient=target_player,
        status=DiplomaticContract.STATUS_SENT,
        sent_year=player.game.year,
        temperature=temperature,
        countered_from=counter_from,
    )
    offer_condition_type = post_data.get('offer_condition_type', DiplomaticContract.CONDITION_EXCHANGE)
    valid_offer_conditions = {choice[0] for choice in DiplomaticContract.CONDITION_CHOICES}
    if offer_condition_type not in valid_offer_conditions:
        offer_condition_type = DiplomaticContract.CONDITION_EXCHANGE
    contract.offer_condition_type = offer_condition_type

    deadline_years = max(1, parse_int('deadline_years', 24))
    contract.expires_year = int(player.game.year or 0) + deadline_years
    contract.extend_on_accept_years = parse_int('extend_on_accept_years', 0)

    request_clause = post_data.get('request_clause_type', DiplomaticContract.CLAUSE_NOTHING)
    request_clause_values = {value for value, _label in _diplomacy_request_clause_choices()}
    if request_clause not in request_clause_values:
        request_clause = DiplomaticContract.CLAUSE_NOTHING
    contract.request_clause_type = request_clause

    offer_clause = post_data.get('offer_clause_type', DiplomaticContract.CLAUSE_NOTHING)
    offer_clause_values = {value for value, _label in _diplomacy_offer_clause_choices()}
    if offer_clause not in offer_clause_values:
        offer_clause = DiplomaticContract.CLAUSE_NOTHING
    contract.offer_clause_type = offer_clause

    if request_clause == DiplomaticContract.CLAUSE_TECHNOLOGY:
        request_tech_id = post_data.get('request_technology')
        if not request_tech_id:
            errors.append('Requested technology is required.')
        elif request_tech_id not in available_request_techs:
            errors.append('Requested technology is not available for this negotiation.')
        else:
            contract.request_technology = available_request_techs[request_tech_id]
    elif request_clause == DiplomaticContract.CLAUSE_REPORT:
        request_report_target = post_data.get('request_report_target')
        if not request_report_target:
            errors.append('Requested report is required.')
        elif request_report_target not in available_request_reports:
            errors.append('Requested report is not available for this negotiation.')
        else:
            target_type, target_id = available_request_reports[request_report_target]
            contract.request_report_target_type = target_type
            contract.request_report_target_id = target_id
    elif request_clause == DiplomaticContract.CLAUSE_STANCE:
        contract.request_stance = normalise_stance(post_data.get('request_stance'))
    elif request_clause == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        request_star_id = post_data.get('request_star')
        if not request_star_id:
            errors.append('Requested colony is required.')
        elif request_star_id not in available_request_stars:
            errors.append('Requested colony is not available for this negotiation.')
        else:
            contract.request_star = available_request_stars[request_star_id]
    elif request_clause == DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT:
        contract.request_ship_count = max(1, parse_int('request_ship_count', 0))
        if contract.request_ship_count <= 0:
            errors.append('Requested fleet ship count must be at least 1.')
    elif request_clause in (
        DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
        DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
    ):
        resource_total = 0
        for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z', 'colonists'):
            value = parse_int('request_%s' % key, 0)
            if key in SECRET_RESOURCE_KEYS and not bool(getattr(player, 'discovered_%s' % key, False)):
                value = 0
            setattr(contract, 'request_%s' % key, value)
            resource_total += value
        if resource_total <= 0:
            errors.append('Requested resources must include at least one positive quantity.')
        if (
            request_clause == DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD and
            int(getattr(contract, 'request_colonists', 0) or 0) > 0
        ):
            errors.append('Colonists must currently be requested on a transferred fleet, not by direct world delivery.')
        if request_clause == DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD:
            suggested_star_id = post_data.get('request_suggested_star')
            if suggested_star_id:
                contract.request_suggested_star = player.stars.filter(id=suggested_star_id).first()
                if contract.request_suggested_star is None:
                    errors.append('Suggested destination must be one of your colonies.')

    if offer_clause == DiplomaticContract.CLAUSE_TECHNOLOGY:
        offer_tech_id = post_data.get('offer_technology')
        if not offer_tech_id:
            errors.append('Offered technology is required.')
        elif offer_tech_id not in available_offer_techs:
            errors.append('You cannot offer a technology you do not currently have.')
        else:
            contract.offer_technology = available_offer_techs[offer_tech_id]
    elif offer_clause == DiplomaticContract.CLAUSE_REPORT:
        offer_report_target = post_data.get('offer_report_target')
        if not offer_report_target:
            errors.append('Offered report is required.')
        elif offer_report_target not in available_offer_reports:
            errors.append('You cannot offer a report you do not currently have.')
        else:
            target_type, target_id = available_offer_reports[offer_report_target]
            contract.offer_report_target_type = target_type
            contract.offer_report_target_id = target_id
    elif offer_clause == DiplomaticContract.CLAUSE_STANCE:
        contract.offer_stance = normalise_stance(post_data.get('offer_stance'))
    elif offer_clause == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        offer_star_id = post_data.get('offer_star')
        if not offer_star_id:
            errors.append('Offered colony is required.')
        elif offer_star_id not in available_offer_stars:
            errors.append('Offered colony must be one of your current colonies.')
        else:
            contract.offer_star = available_offer_stars[offer_star_id]
    elif offer_clause == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
        offer_fleet_id = post_data.get('offer_fleet')
        if not offer_fleet_id:
            errors.append('Offered fleet is required.')
        else:
            contract.offer_fleet = player.fleets.filter(id=offer_fleet_id).first()
            if contract.offer_fleet is None:
                errors.append('Offered fleet must be one of your current fleets.')
        contract.offer_fleet_include_report = bool(post_data.get('offer_fleet_include_report'))

    if (
        contract.request_clause_type == DiplomaticContract.CLAUSE_NOTHING and
        contract.offer_clause_type == DiplomaticContract.CLAUSE_NOTHING
    ):
        errors.append('A contract must include at least one clause.')

    if not errors:
        try:
            contract.full_clean()
        except ValidationError as exc:
            for values in exc.message_dict.values():
                errors.extend(values)
    return contract, errors


@player_only_view()
def diplomacy(request, game_short_id):
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player is None:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Only joined players can use diplomacy.'
        })
    contact_players = encountered_players(player)
    selected_target = request.POST.get('target') or request.GET.get('target') or 'default'
    selected_contract_short_id = request.POST.get('contract_id') or request.GET.get('contract')
    compose_requested = (request.POST.get('action') == 'send_contract') or (request.GET.get('compose') == '1')
    counter_short_id = request.POST.get('counter_from') or request.GET.get('counter')
    contract_errors = []
    contract_notice = ''

    selected_player = None
    if selected_target and selected_target != 'default':
        selected_player = next(
            (other for other in contact_players if other.short_id == selected_target),
            None,
        )
    if selected_target != 'default' and selected_player is None:
        selected_target = 'default'

    can_compose_negotiation = bool(
        selected_player is not None and
        not bool(getattr(selected_player, 'defeated', False))
    )

    locked, lock_reason = diplomatic_actions_locked(player)

    if request.method == 'POST':
        action = request.POST.get('action') or 'stances'
        if action == 'stances':
            if locked:
                contract_errors.append(lock_reason)
            else:
                stance_updates = {}
                for other in contact_players:
                    key = 'stance_%s' % other.short_id
                    if key in request.POST:
                        stance_updates[other.short_id] = request.POST.get(key)
                update_player_stances(
                    player,
                    request.POST.get('stance_default'),
                    stance_updates,
                )
                return redirect(_diplomacy_redirect_url(game.short_id, target=selected_target))
        elif action == 'toggle_reveal_cloaked':
            if selected_player is None:
                contract_errors.append('Select a discovered race first.')
            elif locked:
                contract_errors.append(lock_reason)
            else:
                default_stance = player_pending_default_stance(player)
                row, _created = PlayerDiplomaticStance.objects.get_or_create(
                    player=player,
                    target_player=selected_player,
                    defaults={
                        'stance': default_stance,
                        'pending_stance': default_stance,
                    },
                )
                current_stance = normalise_stance(
                    getattr(row, 'pending_stance', None) or getattr(row, 'stance', None)
                )
                row.reveal_cloaked_fleets = bool(
                    request.POST.get('reveal_cloaked_fleets')
                ) and current_stance == STANCE_ALLIED
                row.save(update_fields=['reveal_cloaked_fleets'])
                return redirect(_diplomacy_redirect_url(game.short_id, target=selected_target))
        elif action in ('accept_contract', 'decline_contract', 'revoke_contract', 'extend_contract'):
            contract = DiplomaticContract.objects.filter(
                game=game,
                short_id=request.POST.get('contract_id'),
            ).select_related('sender', 'recipient').first()
            if action == 'accept_contract':
                ok, result = accept_contract(contract, player)
            elif action == 'decline_contract':
                ok, result = decline_contract(contract, player)
            elif action == 'extend_contract':
                ok, result = extend_contract(contract, player, request.POST.get('extend_years'))
            else:
                ok, result = revoke_contract(contract, player)
            if ok:
                return redirect(_diplomacy_redirect_url(game.short_id, target=selected_target))
            contract_errors.append(result)
        elif action == 'send_contract':
            compose_requested = True
            if selected_player is None:
                defeated_target = None
                if selected_target and selected_target != 'default':
                    defeated_target = Player.objects.filter(
                        game=game,
                        short_id=selected_target,
                        defeated=True,
                    ).first()
                if defeated_target is not None:
                    contract_errors.append('Cannot negotiate with defeated races.')
                else:
                    contract_errors.append('Select a discovered race before drafting a negotiation.')
            elif bool(getattr(selected_player, 'defeated', False)):
                contract_errors.append('Cannot negotiate with defeated races.')
            elif locked:
                contract_errors.append(lock_reason)
            else:
                max_requests = max(1, server_setting_int('max_diplomatic_requests_per_race_per_turn', 2))
                sent_count = DiplomaticContract.objects.filter(
                    game=game,
                    sender=player,
                    recipient=selected_player,
                    sent_year=game.year,
                ).count()
                if sent_count >= max_requests:
                    contract_errors.append(
                        'You have already sent the maximum of %s diplomatic request%s to %s this turn.'
                        % (
                            max_requests,
                            '' if max_requests == 1 else 's',
                            selected_player.name,
                        )
                    )
                counter_contract = None
                if counter_short_id:
                    counter_contract = DiplomaticContract.objects.filter(
                        game=game,
                        short_id=counter_short_id,
                    ).select_related('sender', 'recipient').first()
                    if counter_contract is None:
                        contract_errors.append('Countered contract not found.')
                    elif counter_contract.recipient_id != player.id or counter_contract.sender_id != selected_player.id:
                        contract_errors.append('You can only counter an incoming contract from the selected race.')
                available_offer_techs = {
                    str(tech.id): tech for tech in get_player_unlocked_technologies(player)
                }
                available_request_techs = {
                    str(tech.id): tech for tech in get_player_unlocked_technologies(selected_player)
                } if selected_player is not None else {}
                available_request_stars = {
                    str(star.id): star for star in _diplomacy_known_target_colony_choices(player, selected_player)
                } if selected_player is not None else {}
                available_offer_stars = {
                    str(star.id): star for star in player.stars.order_by('id')
                }
                available_request_reports = {
                    item['id']: tuple(item['id'].split(':', 1))
                    for group in _diplomacy_request_report_choice_groups(player, selected_player)
                    for item in group['items']
                } if selected_player is not None else {}
                available_offer_reports = {
                    item['id']: tuple(item['id'].split(':', 1))
                    for group in _diplomacy_report_choice_groups(player)
                    for item in group['items']
                }
                if not contract_errors:
                    contract, parse_errors = _diplomacy_parse_contract(
                        player,
                        selected_player,
                        request.POST,
                        available_offer_techs,
                        available_request_techs,
                        available_request_stars,
                        available_offer_stars,
                        available_request_reports,
                        available_offer_reports,
                        counter_from=counter_contract,
                    )
                    contract_errors.extend(parse_errors)
                    if not contract_errors:
                        contract.save()
                        if contract.offer_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
                            ensure_specific_fleet_report(contract)
                        if contract.offer_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
                            ensure_specific_colony_report(contract)
                        if counter_contract is not None:
                            mark_countered(counter_contract, contract)
                        return redirect(
                            _diplomacy_redirect_url(
                                game.short_id,
                                target=selected_target,
                                extra={'contract': contract.short_id},
                            )
                        )

    pending_default_stance = player_pending_default_stance(player)
    pending_stance_map = build_pending_stance_map(player)
    own_stance_map = {
        other.id: pending_stance_map.get(other.id, pending_default_stance)
        for other in contact_players
    }
    rows = [{
        'short_id': 'default',
        'name': 'Default',
        'stance': pending_default_stance,
        'selected': selected_target == 'default',
        'is_default': True,
    }]
    for other in contact_players:
        rows.append({
            'short_id': other.short_id,
            'name': other.name,
            'stance': own_stance_map[other.id],
            'selected': selected_target == other.short_id,
            'is_default': False,
            'is_defeated': bool(getattr(other, 'defeated', False)),
        })

    contract_rows = []
    counter_contract = None
    if selected_player is not None:
        if counter_short_id:
            counter_contract = DiplomaticContract.objects.filter(
                game=game,
                short_id=counter_short_id,
                sender=selected_player,
                recipient=player,
            ).first()
            if counter_contract is not None:
                compose_requested = True
        for contract in pair_contracts(player, selected_player):
            if contract.offer_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET and contract.recipient_id == player.id:
                ensure_specific_fleet_report(contract)
            if contract.offer_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY and contract.recipient_id == player.id:
                ensure_specific_colony_report(contract)
            progress = _diplomacy_contract_progress(contract, player)
            if contract.status == DiplomaticContract.STATUS_SENT and contract.recipient_id == player.id:
                status_label = 'Received'
            else:
                status_label = contract.get_status_display()
            contract_rows.append({
                'short_id': contract.short_id,
                'summary_html': format_contract_statement(
                    contract,
                    viewer=player,
                    include_links=True,
                    include_sender_account=False,
                    emphasize_actions=True,
                ),
                'status': status_label,
                'status_raw': contract.status,
                'request_clause_type': contract.request_clause_type,
                'expires_year': int(contract.expires_year or 0),
                'progress': progress,
                'is_incoming': contract.recipient_id == player.id,
                'is_outgoing': contract.sender_id == player.id,
                'selected': selected_contract_short_id == contract.short_id,
                'can_accept': (contract.recipient_id == player.id and contract.status == DiplomaticContract.STATUS_SENT and not locked),
                'can_decline': (contract.recipient_id == player.id and contract.status == DiplomaticContract.STATUS_SENT and not locked),
                'can_counter': (contract.recipient_id == player.id and contract.status == DiplomaticContract.STATUS_SENT and not locked),
                'can_revoke': (contract.sender_id == player.id and contract.status == DiplomaticContract.STATUS_SENT and not locked),
                'can_extend': (contract.sender_id == player.id and contract.status == DiplomaticContract.STATUS_SENT and not locked),
                'accept_homeworld_warning': bool(
                    contract.recipient_id == player.id and
                    contract.status == DiplomaticContract.STATUS_SENT and
                    contract.request_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY and
                    getattr(contract, 'request_star_id', None) == getattr(player, 'homeworld_id', None)
                ),
            })

    if selected_player:
        stance_row = PlayerDiplomaticStance.objects.filter(
            player=player,
            target_player=selected_player,
        ).first()
        their_stance = stance_towards(selected_player, player)
        our_stance = own_stance_map.get(selected_player.id, pending_default_stance)
        combat_chance_base = combat_chance_percent(our_stance, their_stance)
        combat_modifier = combat_chance_modifier_percent(player, selected_player)
        detail = {
            'name': _diplomacy_player_display_name(selected_player),
            'is_defeated': bool(getattr(selected_player, 'defeated', False)),
            'their_stance': stance_label(their_stance),
            'our_stance': stance_label(our_stance),
            'combat_chance_base': combat_chance_base,
            'combat_modifier': '%+d%%' % combat_modifier,
            'our_stance_raw': our_stance,
            'effects': stance_effect_items(our_stance),
            'is_default': False,
            'delivery_warning': our_stance in (STANCE_HOSTILE, STANCE_COLD),
            'colony_transfer_warning': True,
            'show_reveal_cloaked_toggle': our_stance == STANCE_ALLIED,
            'reveal_cloaked_fleets_checked': bool(
                stance_row and getattr(stance_row, 'reveal_cloaked_fleets', False)
            ),
        }
    else:
        detail = {
            'name': 'Default Stance',
            'is_defeated': False,
            'their_stance': None,
            'our_stance': stance_label(pending_default_stance),
            'our_stance_raw': pending_default_stance,
            'combat_chance': None,
            'effects': stance_effect_items(pending_default_stance),
            'is_default': True,
            'delivery_warning': False,
            'colony_transfer_warning': False,
        }

    compose_state = _diplomacy_build_compose_state(
        player,
        selected_player,
        request_obj=request if compose_requested or request.method == 'POST' else None,
        counter_contract=counter_contract,
    )
    offer_clause_choices = _diplomacy_offer_clause_choices()
    resource_choices = _diplomacy_known_resource_choices(player)
    resource_rows = [
        {
            'key': key,
            'label': label,
            'value': compose_state.get('resources', {}).get(key, ''),
        }
        for key, label in resource_choices
    ]
    offer_technologies = get_player_unlocked_technologies(player) if player else []
    request_technologies = get_player_unlocked_technologies(selected_player) if selected_player else []
    offer_technology_groups = _diplomacy_group_technologies(offer_technologies)
    request_technology_groups = _diplomacy_group_technologies(request_technologies)
    offer_report_groups = _diplomacy_report_choice_groups(player, viewer=player)
    request_report_groups = _diplomacy_request_report_choice_groups(player, selected_player)
    fleet_choices = list(player.fleets.order_by('name', 'id')) if player else []
    owned_colony_choices = _diplomacy_colony_choice_rows(
        player,
        list(player.stars.order_by('id')) if player else [],
        viewer=player,
    )
    request_colony_choices = _diplomacy_colony_choice_rows(
        selected_player,
        _diplomacy_known_target_colony_choices(player, selected_player),
        viewer=player,
    )

    return render(request, 'dj4xol/diplomacy.html', {
        'game': game,
        'player': player,
        'is_owner': account == game.owner,
        'rows': rows,
        'selected_target': selected_target,
        'detail': detail,
        'stance_choices': STANCE_CHOICES,
        'user_theme': account.theme if account else 'classic',
        'contracts': contract_rows,
        'compose_open': bool(compose_requested and can_compose_negotiation),
        'can_compose_negotiation': can_compose_negotiation,
        'compose_state': compose_state,
        'compose_errors': contract_errors,
        'compose_notice': contract_notice,
        'temperature_choices': DiplomaticContract.TEMPERATURE_CHOICES,
        'offer_condition_choices': _diplomacy_offer_condition_choices(),
        'request_clause_choices': _diplomacy_request_clause_choices(),
        'offer_clause_choices': offer_clause_choices,
        'request_technology_groups': request_technology_groups,
        'offer_technology_groups': offer_technology_groups,
        'request_report_groups': request_report_groups,
        'offer_report_groups': offer_report_groups,
        'fleet_choices': fleet_choices,
        'owned_colony_choices': owned_colony_choices,
        'request_colony_choices': request_colony_choices,
        'resource_rows': resource_rows,
        'diplomacy_locked': locked,
        'diplomacy_lock_reason': lock_reason,
        'counter_contract': counter_contract,
        'counter_contract_summary': (
            format_contract_summary(counter_contract, viewer=player, include_links=False)
            if counter_contract is not None else ''
        ),
    })


def signup(request):
    """Legacy signup endpoint; onboarding registration is now unified."""
    return redirect('dj4xol:register')


def register(request):
    """Complete 4x profile registration, optionally creating Django user."""
    allow_self_signup = _allow_self_signup()

    # Anonymous users may only proceed when self-sign-up is enabled.
    if not request.user.is_authenticated and not allow_self_signup:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Self-sign-up is disabled on this server.'
        })

    # Check if already registered
    if request.user.is_authenticated and hasattr(request.user, 'dj4xol_account'):
        return redirect(_account_onboarding_redirect_name(request.user.dj4xol_account) or 'dj4xol:index')
    if request.method == 'POST':
        form = RegistrationForm(request.user, request.POST)
        if form.is_valid():
            account = form.save()
            if not request.user.is_authenticated and form.user:
                login(request, form.user)
            sent, reason = send_email_verification_for_account(account)
            if sent:
                messages.success(
                    request,
                    'Verification email sent. Please check your inbox.',
                )
            else:
                messages.warning(
                    request,
                    'Verification email not sent: %s.' % reason,
                )
            return redirect(_account_onboarding_redirect_name(form.instance) or 'dj4xol:index')
    else:
        form = RegistrationForm(request.user)
    return render(request, 'dj4xol/onboarding_profile.html', {
        'form': form,
        'show_user_form': not request.user.is_authenticated,
    })


@login_required
def onboarding_theme(request):
    """Step 2: choose theme during onboarding."""
    if not hasattr(request.user, 'dj4xol_account'):
        return redirect('dj4xol:register')
    account = request.user.dj4xol_account
    if getattr(account, 'onboarding_step', Account.ONBOARDING_STEP_COMPLETE) == Account.ONBOARDING_STEP_COMPLETE:
        return redirect('dj4xol:index')
    if request.method == 'POST':
        theme = request.POST.get('theme', 'classic')
        valid_themes = [t[0] for t in Account.THEME_CHOICES]
        if theme in valid_themes:
            account.theme = theme
            account.onboarding_step = Account.ONBOARDING_STEP_RACE
            account.save(update_fields=['theme', 'onboarding_step'])
            return redirect('dj4xol:onboarding_race')
    return render(request, 'dj4xol/onboarding_theme.html', {
        'theme_choices': Account.THEME_CHOICES,
        'selected_theme': account.theme,
    })


@login_required
def onboarding_race(request):
    """Step 3: create first race during onboarding."""
    if not hasattr(request.user, 'dj4xol_account'):
        return redirect('dj4xol:register')
    account = request.user.dj4xol_account
    if getattr(account, 'onboarding_step', Account.ONBOARDING_STEP_COMPLETE) == Account.ONBOARDING_STEP_COMPLETE:
        return redirect('dj4xol:index')
    if ServerRace.objects.filter(owner=account).exists():
        account.onboarding_step = Account.ONBOARDING_STEP_COMPLETE
        account.save(update_fields=['onboarding_step'])
        return redirect('dj4xol:index')
    show_public = _can_publish_public_races(request.user)
    can_skip_race_creation = _public_server_races_available()
    selected_race_type = request.GET.get('race_type')
    if request.method == 'POST':
        if request.POST.get('action') == 'skip':
            if can_skip_race_creation:
                account.onboarding_step = Account.ONBOARDING_STEP_COMPLETE
                account.save(update_fields=['onboarding_step'])
                return redirect('dj4xol:index')
            return redirect('dj4xol:onboarding_race')
        form = ServerRaceForm(request.POST, show_public=show_public)
        if form.is_valid():
            race = form.save(commit=False)
            race.owner = None if (request.user.is_staff and race.public) else account
            race.save()
            account.onboarding_step = Account.ONBOARDING_STEP_COMPLETE
            account.save(update_fields=['onboarding_step'])
            return redirect('dj4xol:index')
    else:
        form = ServerRaceForm(
            show_public=show_public,
            selected_race_type=selected_race_type,
        )
    max_level = get_global_research_max_level()
    return render(request, 'dj4xol/onboarding_race.html', {
        'form': form,
        'selected_theme': account.theme,
        'race_type_behaviors_json': json.dumps(_race_type_behavior_map()),
        'can_skip_race_creation': can_skip_race_creation,
        'race_type_browser_url': '%s?%s' % (
            reverse('dj4xol:help_race_types'),
            urlencode({'return_to': 'onboarding_race'}),
        ),
        'starting_tech_costs_json': json.dumps(
            get_starting_tech_balance_costs(max_level=max_level)
        ),
    })


@registration_required()
def profile(request):
    """View user's account profile."""
    account = request.user.dj4xol_account
    change_email_form = ChangeEmailForm(
        account,
        initial={'email': account.email},
    )
    change_password_form = AccountPasswordChangeForm(request.user)
    change_email_open = False
    change_password_open = False

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'change_email':
            change_email_form = ChangeEmailForm(account, request.POST)
            change_email_open = True
            if change_email_form.is_valid():
                new_email = change_email_form.cleaned_data['email']
                with transaction.atomic():
                    account.email = new_email
                    account.email_verified = False
                    account.email_verification_key = uuid.uuid4().hex
                    account.save(update_fields=[
                        'email',
                        'email_verified',
                        'email_verification_key',
                    ])
                    account.django_user.email = new_email
                    account.django_user.save(update_fields=['email'])
                sent, reason = send_email_verification_for_account(account)
                if sent:
                    messages.success(
                        request,
                        'Email address updated. Verification email sent.',
                    )
                else:
                    messages.warning(
                        request,
                        'Email address updated, but verification email was not sent: %s.'
                        % reason,
                    )
                return redirect('dj4xol:profile')
            messages.error(
                request,
                'Please correct the highlighted email field.',
            )
        elif action == 'change_password':
            change_password_form = AccountPasswordChangeForm(
                request.user,
                request.POST,
            )
            change_password_open = True
            if change_password_form.is_valid():
                user = change_password_form.save()
                update_session_auth_hash(request, user)
                messages.success(
                    request,
                    'Password updated.',
                )
                return redirect('dj4xol:profile')
            messages.error(
                request,
                'Please correct the highlighted password fields.',
            )

    # Get games the user is playing in
    playing = list(
        Player.objects.filter(account=account, game__ended=False).select_related('game')
    )
    games_playing = [p.game for p in playing]
    player_by_game_id = {
        player.game_id: player for player in playing
    }

    # Get races owned by the user
    races = ServerRace.objects.filter(owner=account)

    # Get games owned by the user
    games_owned = list(Game.objects.filter(owner=account, ended=False))

    return render(request, 'dj4xol/profile.html', {
        'account': account,
        'games_playing_entries': _build_game_list_entries(
            games_playing, player_by_game_id=player_by_game_id
        ),
        'games_owned_entries': _build_game_list_entries(games_owned),
        'races': races,
        'theme_choices': Account.THEME_CHOICES,
        'change_email_form': change_email_form,
        'change_email_open': change_email_open,
        'change_password_form': change_password_form,
        'change_password_open': change_password_open,
    })


def verify_email(request, key):
    account = Account.objects.filter(email_verification_key=key).first()
    if not key or not account:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Invalid or expired verification link.',
        }, status=404)

    if not account.email_verified:
        account.email_verified = True
        account.save(update_fields=['email_verified'])

    current_user = getattr(request, 'user', None)
    current_account = getattr(current_user, 'dj4xol_account', None)
    if current_user is None or not current_user.is_authenticated or current_account == account:
        backend = settings.AUTHENTICATION_BACKENDS[0]
        account.django_user.backend = backend
        login(request, account.django_user, backend=backend)
        messages.success(request, 'Email address verified.')
        return redirect('dj4xol:profile')

    messages.success(
        request,
        'Email address verified for %s.' % (account.alias or account.django_user.username),
    )
    return redirect('dj4xol:index')


@registration_required()
def server_settings(request):
    """Staff-only themed editor for key server settings."""
    if not request.user.is_staff:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Staff access is required.',
        }, status=403)

    if request.method == 'POST':
        form = ServerSettingsForm(request.POST)
        if form.is_valid():
            form.save(user=request.user)
            messages.success(request, 'Server settings updated.')
            return redirect('dj4xol:server_settings')
    else:
        form = ServerSettingsForm(initial=ServerSettingsForm.initial_from_settings())

    return render(request, 'dj4xol/server_settings.html', {
        'form': form,
        'form_sections': list(form.iter_sections()),
        'selected_theme': request.user.dj4xol_account.theme,
        'server_name': ServerSettings.get('server_name', 'dj4xol'),
        'server_tagline': ServerSettings.get('server_tagline', ''),
    })


@registration_required()
def update_theme(request):
    """Update user's theme preference."""
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    account = request.user.dj4xol_account
    theme = request.POST.get('theme', 'classic')

    # Validate theme choice
    valid_themes = [t[0] for t in Account.THEME_CHOICES]
    if theme not in valid_themes:
        return JsonResponse({'error': 'Invalid theme'}, status=400)

    account.theme = theme
    account.save(update_fields=['theme'])

    return JsonResponse({'success': True, 'theme': theme})


@registration_required()
def update_email_preferences(request):
    """Update account email preference checkboxes."""
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    account = request.user.dj4xol_account
    account.email_game_updates = bool(request.POST.get('email_game_updates'))
    account.email_newsletter = bool(request.POST.get('email_newsletter'))
    account.email_html_enabled = bool(request.POST.get('email_html_enabled'))
    rollups_raw = request.POST.get('email_game_rollups_per_day')
    if not account.email_game_updates:
        account.email_game_rollups_per_day = 0
    else:
        try:
            rollups = int(rollups_raw)
        except (TypeError, ValueError):
            rollups = 1
        account.email_game_rollups_per_day = max(1, min(4, rollups))
    account.save(update_fields=[
        'email_game_updates',
        'email_game_rollups_per_day',
        'email_newsletter',
        'email_html_enabled',
    ])

    return JsonResponse({
        'success': True,
        'email_game_updates': account.email_game_updates,
        'email_game_rollups_per_day': account.email_game_rollups_per_day,
        'email_newsletter': account.email_newsletter,
        'email_html_enabled': account.email_html_enabled,
    })


@registration_required()
def resend_email_verification(request):
    if request.method != 'POST':
        return redirect('dj4xol:profile')

    account = request.user.dj4xol_account
    if account.email_verified:
        messages.success(request, 'Email address already verified.')
        return redirect('dj4xol:profile')

    sent, reason = send_email_verification_for_account(account)
    if sent:
        messages.success(request, 'Verification email sent.')
    else:
        messages.warning(request, 'Verification email not sent: %s.' % reason)
    return redirect('dj4xol:profile')


@registration_required()
def send_unverified_email_verifications(request):
    if not request.user.is_staff:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Staff access is required.',
        }, status=403)

    if request.method != 'POST':
        return redirect('dj4xol:server_settings')

    sent_count = 0
    failed_count = 0
    accounts = Account.objects.filter(email_verified=False).exclude(email='')
    for account in accounts.iterator():
        sent, reason = send_email_verification_for_account(account)
        if sent:
            sent_count += 1
        else:
            failed_count += 1

    total_count = sent_count + failed_count
    if total_count == 0:
        messages.success(request, 'No unverified accounts with email addresses.')
    elif failed_count:
        messages.warning(
            request,
            'Sent verification email to %s unverified account%s; %s failed.' % (
                sent_count,
                '' if sent_count == 1 else 's',
                failed_count,
            ),
        )
    else:
        messages.success(
            request,
            'Sent verification email to %s unverified account%s.' % (
                sent_count,
                '' if sent_count == 1 else 's',
            ),
        )
    return redirect('dj4xol:server_settings')


@staff_member_required
def test_email_rollup(request):
    """Trigger a one-off rollup email for the current staff account."""
    account = request.user.dj4xol_account
    sent, reason = send_message_rollup_for_account(
        account,
        ignore_frequency=True,
        dry_run=False,
    )
    if sent:
        messages.success(request, 'Test rollup email sent.')
    else:
        messages.warning(request, f'Test rollup not sent: {reason}.')
    return redirect('dj4xol:index')


@staff_member_required
def test_generic_email(request):
    """Trigger a one-off generic text email for the current staff account."""
    account = request.user.dj4xol_account
    sent, reason = send_generic_test_email_for_account(
        account,
        dry_run=False,
    )
    if sent:
        messages.success(request, 'Generic test email sent.')
    else:
        messages.warning(request, f'Generic test email not sent: {reason}.')
    return redirect('dj4xol:index')


def unsubscribe_email(request, key):
    if not key:
        return render(request, 'dj4xol/email_preferences_unsubscribe.html', {
            'account': Account(email_game_updates=False, email_game_rollups_per_day=0),
            'status_message': 'Invalid or expired unsubscribe link.',
        })

    account = Account.objects.filter(email_unsubscribe_key=key).first()
    status_message = None
    if not account:
        return render(request, 'dj4xol/email_preferences_unsubscribe.html', {
            'account': Account(email_game_updates=False, email_game_rollups_per_day=0),
            'status_message': 'Invalid or expired unsubscribe link.',
        })

    if request.method == 'POST':
        email_updates = bool(request.POST.get('email_game_updates'))
        account.email_game_updates = email_updates
        account.email_newsletter = bool(request.POST.get('email_newsletter'))
        if not email_updates:
            account.email_game_rollups_per_day = 0
        else:
            try:
                rollups = int(request.POST.get('email_game_rollups_per_day'))
            except (TypeError, ValueError):
                rollups = 1
            account.email_game_rollups_per_day = max(1, min(4, rollups))
        account.save(update_fields=[
            'email_game_updates',
            'email_game_rollups_per_day',
            'email_newsletter',
        ])
        status_message = 'Preferences updated.'

    return render(request, 'dj4xol/email_preferences_unsubscribe.html', {
        'account': account,
        'status_message': status_message,
    })


@player_only_view()
def objects_at_location(request, game_short_id, x, y):
    """API endpoint to get objects at specific coordinates."""
    from django.http import JsonResponse
    
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    
    try:
        x, y = int(x), int(y)
    except ValueError:
        return JsonResponse({'error': 'Invalid coordinates'}, status=400)
    
    # Use DetailBuilder to get objects at location
    builder = DetailBuilder(game, x, y, None, player=player)
    builder.find_all_at_coordinates(x, y)
    objects = builder.get_objects_here()
    
    return JsonResponse({'objects': objects})


@player_only_view()
def game_status(request, game_short_id):
    """Return current game year and player turn-in status."""
    from django.http import JsonResponse
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    return JsonResponse({'year': game.year, 'turned_in': player.turned_in})


@player_only_view()
def play_cli_bootstrap(request, game_short_id):
    """Return the initial Play CLI transcript for the web terminal overlay."""
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)
    if not _play_cli_web_enabled():
        return JsonResponse({'error': 'Play API disabled'}, status=404)
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    return JsonResponse({
        'ok': True,
        'lines': build_bootstrap_transcript(game, player),
        'close_overlay': False,
    })


@player_only_view()
def play_cli_command(request, game_short_id):
    """Execute a browser Play CLI command via authenticated JSON."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if not _play_cli_web_enabled():
        return JsonResponse({'error': 'Play API disabled'}, status=404)
    if not _is_same_origin_request(request):
        return JsonResponse({'error': 'Origin mismatch'}, status=403)
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()

    if not enforce_browser_rate_limit(game, account):
        return JsonResponse({
            'ok': False,
            'lines': ['Play CLI rate limit exceeded. Please wait a moment and try again.'],
            'close_overlay': False,
        }, status=429)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    result = execute_browser_command(game, player, payload.get('command'))
    return JsonResponse(result)


@player_only_view()
def rename_object(request, game_short_id, object_short_id):
    """Rename a star or fleet owned by the player."""
    from django.http import JsonResponse
    from .models import Star, Fleet

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()

    new_name = request.POST.get('name', '').strip()
    if not new_name:
        return JsonResponse({'error': 'Name is required'}, status=400)
    if len(new_name) > 30:
        return JsonResponse({'error': 'Name must be 30 characters or less'}, status=400)
    profanity_filter = profanity_filter_settings()
    try:
        new_name = validate_safe_public_text(
            new_name,
            'Name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
    except ValidationError as exc:
        return JsonResponse({'error': exc.messages[0]}, status=400)

    # Try to find the object (star or fleet) and verify ownership
    obj = None
    obj = Star.objects.filter(short_id=object_short_id, game=game).first()
    if obj:
        if obj.player != player:
            return JsonResponse({'error': 'You do not own this star'}, status=403)
    else:
        obj = Fleet.objects.filter(short_id=object_short_id, game=game).first()
        if obj:
            if obj.player != player:
                return JsonResponse({'error': 'You do not own this fleet'}, status=403)
        else:
            return JsonResponse({'error': 'Object not found'}, status=404)

    obj.name = new_name
    obj.save()

    return JsonResponse({'success': True, 'name': new_name})


@player_only_view()
def set_star_marker(request, game_short_id, star_short_id):
    """Create, update, or clear the player's personal marker for a star location."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player is None:
        return JsonResponse({'error': 'Player not found'}, status=404)

    star = Star.objects.filter(short_id=star_short_id, game=game).first()
    if star is None:
        return JsonResponse({'error': 'Star not found'}, status=404)

    stars_at_location = list(Star.objects.filter(game=game, x=star.x, y=star.y))
    def marker_star_sort_key(candidate):
        owner = getattr(candidate, 'player', None)
        owner_priority = 0 if owner == player else (1 if owner else 2)
        homeworld_priority = -1 if player.homeworld_id == getattr(candidate, 'id', None) else 0
        return (
            owner_priority,
            homeworld_priority,
            str(getattr(candidate, 'short_id', '') or ''),
            int(getattr(candidate, 'id', 0) or 0),
        )

    primary_star = sorted(
        stars_at_location or [star],
        key=marker_star_sort_key,
    )[0]
    star = primary_star

    marker_type = (request.POST.get('marker_type', '') or '').strip().upper()
    marker_color = (request.POST.get('marker_color', '') or '').strip().upper()
    if marker_type == 'CLEAR':
        marker_type = ''
    if not marker_color:
        marker_color = PlayerStarMarker.COLOR_BLUE
    if marker_color == PlayerStarMarker.COLOR_WHITE:
        marker_color = PlayerStarMarker.COLOR_BLUE
    valid_types = {PlayerStarMarker.TYPE_CIRCLE, PlayerStarMarker.TYPE_X}
    valid_colors = PlayerStarMarker.COLOR_VALUES
    if marker_type and marker_type not in valid_types:
        return JsonResponse({'error': 'Invalid marker type'}, status=400)
    if marker_color not in valid_colors:
        return JsonResponse({'error': 'Invalid marker colour'}, status=400)

    location_markers = PlayerStarMarker.objects.filter(
        player=player,
        star__in=stars_at_location,
    )
    if not marker_type:
        location_markers.delete()
    else:
        location_markers.exclude(star=star).delete()
        PlayerStarMarker.objects.update_or_create(
            player=player,
            star=star,
            defaults={
                'marker_type': marker_type,
                'marker_color': marker_color,
            },
        )

    return JsonResponse({
        'success': True,
        'marker_type': marker_type,
        'marker_color': marker_color,
    })
