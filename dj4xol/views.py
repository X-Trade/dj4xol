from django.db import models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.urls import resolve
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
import json

from dj4xol.objectdetails import DetailBuilder

from .models import (
    Game, Player, ServerSettings, ServerRace, Account, GameInvitation, Fleet,
    FleetOrders, Star, ResearchCategory, Technology,
)
from .decorators import registration_required, player_only_view
from .turn import GameTurn
from .research import (
    build_research_screen_data, update_player_allocations, set_even_allocations,
    set_singular_allocation, get_global_research_max_level,
    get_starting_tech_balance_costs,
)
from .technology_thumbnails import (
    get_technology_thumbnail_initial_index,
    get_technology_thumbnail_path,
    get_technology_thumbnail_paths,
)
from .starmap import StarMap
from .factory import GameFactory
from .forms import ServerRaceForm, NewGameForm, RegistrationForm, JoinGameForm


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


@registration_required()
def gamelist(request):
    """Index of all games the user can see."""
    account = request.user.dj4xol_account
    playing_game_ids = Player.objects.filter(account=account).values('game')

    my_games = Game.objects.filter(pk__in=playing_game_ids, ended=False)
    open_games = Game.objects.filter(public=True, joinable=True, ended=False).exclude(pk__in=playing_game_ids)

    # Games I'm invited to (by account or email) that I haven't joined yet
    invited_games = Game.objects.filter(
        pk__in=GameInvitation.objects.filter(
            models.Q(account=account) | models.Q(email=account.email)
        ).values('game'),
        ended=False
    ).exclude(pk__in=playing_game_ids)

    return render(request, 'dj4xol/games.html', {
        'account': account,
        'my_games': my_games,
        'invited_games': invited_games,
        'open_games': open_games,
        'server_name': ServerSettings.get('server_name', 'dj4xol'),
        'server_tagline': ServerSettings.get('server_tagline', ''),
        'server_welcome': ServerSettings.get('server_welcome', ''),
    })

@registration_required()
def join_game(request, game_short_id):
    """Join a game with race selection."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account

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

    if game.max_players and game.players.count() >= game.max_players:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game is full.'
        })

    if request.method == 'POST':
        form = JoinGameForm(account, request.POST)
        if form.is_valid():
            player = GameFactory(game).join_player(account, form.cleaned_data['race'], invited=is_invited)
            if player:
                # Clean up invitation
                game.invitations.filter(
                    models.Q(account=account) | models.Q(email=account.email)
                ).delete()
                return redirect('dj4xol:game', game_short_id=game.short_id)
            return render(request, 'dj4xol/forbidden.html', {
                'message': 'Unable to join game.'
            })
    else:
        form = JoinGameForm(account)

    return render(request, 'dj4xol/join_game.html', {
        'form': form,
        'game': game
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
    detail_builder = DetailBuilder(game, x, y, selected, player=player)
    detail = detail_builder.build_detail()

    # Check for destination selection mode
    dest_mode = request.GET.get('mode') == 'select_destination'
    dest_fleet = request.GET.get('fleet', None)
    dest_warp = request.GET.get('warp', '5')

    # Check for chosen destination (returned from selection mode)
    dest_star_id = request.GET.get('dest_star', None)
    dest_fleet_id = request.GET.get('dest_fleet', None)
    dest_salvage_id = request.GET.get('dest_salvage', None)
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
        from .models import Salvage
        dest_obj = Fleet.objects.filter(short_id=dest_fleet_id, game=game).first()
        if dest_obj:
            dest_name = dest_obj.name
            dest_location = (dest_obj.x, dest_obj.y)
            dest_selected_target = f'fleet:{dest_obj.short_id}'
    elif dest_salvage_id:
        from .models import Salvage
        dest_obj = Salvage.objects.filter(short_id=dest_salvage_id, game=game).first()
        if dest_obj:
            dest_name = dest_obj.name
            dest_location = (dest_obj.x, dest_obj.y)
            dest_selected_target = f'salvage:{dest_obj.short_id}'
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
        messages_qs = player.messages.order_by('-priority', '-year', '-id')
        if player.messages_seen_year is not None:
            messages_qs = messages_qs.filter(year__gte=player.messages_seen_year)
        messages = messages_qs[:1000]
        # Update last_seen_year for next turn generation
        player.last_seen_year = game.year
        player.save(update_fields=['last_seen_year'])
    else:
        messages = []

    # Get player's homeworld for home button
    homeworld = player.homeworld if player else None

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
        'dest_name': dest_name,
        'dest_x': dest_x,
        'dest_y': dest_y,
        'destination_targets': destination_targets,
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


def _redirect_preserving_selection(request, game):
    """Redirect to game view (or explicit target), preserving game selection when relevant."""
    from django.urls import reverse
    from urllib.parse import urlencode
    return_to = request.POST.get('return_to') or request.GET.get('return_to')
    if return_to == 'research':
        url = reverse('dj4xol:research', kwargs={'game_short_id': game.short_id})
        return redirect(url)

    url = reverse('dj4xol:game', kwargs={'game_short_id': game.short_id})
    params = {k: request.POST.get(k) or request.GET.get(k)
              for k in ['x', 'y', 'sel'] if request.POST.get(k) or request.GET.get(k)}
    if params:
        url = f"{url}?{urlencode(params)}"
    return redirect(url)


@player_only_view()
def add_production_order(request, game_short_id):
    """Add a production order to a star."""
    from .models import Star, ProductionOrder
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
        # Calculate next position
        max_pos = star.production_orders.aggregate(
            max_pos=models.Max('position'))['max_pos'] or 0
        ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type=order_type,
            position=max_pos + 1,
            quantity=max(1, quantity),
            repeat=repeat,
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
def add_fleet_order(request, game_short_id):
    """Add a movement or transfer order to a fleet."""
    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return _redirect_preserving_selection(request, game)

    fleet_short_id = request.POST.get('fleet')
    order_type = request.POST.get('order_type', 'MOVE')
    repeat = request.POST.get('repeat') == 'on'

    # Verify fleet belongs to player
    fleet = Fleet.objects.get(short_id=fleet_short_id, game=game, player=player)

    # Create order based on type
    order = FleetOrders(game=game, fleet=fleet, order_type=order_type, repeat=repeat)
    
    if order_type in ['MOVE', 'INTERCEPT']:
        from .models import Salvage
        target_star_id = request.POST.get('target_star')
        target_fleet_id = request.POST.get('target_fleet')
        target_salvage_id = request.POST.get('target_salvage')
        target_x = request.POST.get('target_x')
        target_y = request.POST.get('target_y')
        warpfactor = int(request.POST.get('warpfactor', fleet.max_safe_warp))
        order.warpfactor = warpfactor

        if target_star_id:
            order.target_star = Star.objects.get(short_id=target_star_id, game=game)
        elif target_fleet_id:
            order.target_fleet = Fleet.objects.get(short_id=target_fleet_id, game=game)
        elif target_salvage_id:
            order.target_salvage = Salvage.objects.get(short_id=target_salvage_id, game=game)
        elif target_x and target_y:
            order.x = int(target_x)
            order.y = int(target_y)

        if order_type == 'INTERCEPT' and not order.target_fleet:
            order.order_type = 'MOVE'
    
    elif order_type == 'PATROL':
        from .models import Salvage
        target_star_id = request.POST.get('target_star')
        target_fleet_id = request.POST.get('target_fleet')
        target_salvage_id = request.POST.get('target_salvage')
        target_x = request.POST.get('target_x')
        target_y = request.POST.get('target_y')
        patrol_target = request.POST.get('patrol_target', '')

        order.patrol_radius = int(request.POST.get('patrol_radius', 15))
        order.intercept_speed = int(request.POST.get('intercept_speed', fleet.max_safe_warp))

        if patrol_target and ':' in patrol_target:
            target_type, target_id = patrol_target.split(':', 1)
            if target_type == 'star':
                order.target_star = Star.objects.get(short_id=target_id, game=game)
            elif target_type == 'fleet':
                order.target_fleet = Fleet.objects.get(short_id=target_id, game=game)
        elif patrol_target in ['empty', 'space'] and target_x and target_y:
            order.x = int(target_x)
            order.y = int(target_y)
        elif target_star_id:
            order.target_star = Star.objects.get(short_id=target_star_id, game=game)
        elif target_fleet_id:
            order.target_fleet = Fleet.objects.get(short_id=target_fleet_id, game=game)
        elif target_salvage_id:
            order.target_salvage = Salvage.objects.get(short_id=target_salvage_id, game=game)
        elif target_x and target_y:
            order.x = int(target_x)
            order.y = int(target_y)

    
    elif order_type == 'TRANSFER':
        from .models import Salvage
        transfer_type = request.POST.get('transfer_type', 'LOAD')
        transfer_target = request.POST.get('transfer_target', '')

        order.transfer_type = transfer_type
        order.transfer_ironium = int(request.POST.get('transfer_ironium', 0))
        order.transfer_boranium = int(request.POST.get('transfer_boranium', 0))
        order.transfer_germanium = int(request.POST.get('transfer_germanium', 0))
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

    elif order_type == 'COLONISE':
        # Colonise orders always have repeat=False (fleet is destroyed)
        order.repeat = False
        colonise_target = request.POST.get('colonise_target', '')

        # Colonise target must be a star
        if colonise_target:
            order.target_star = Star.objects.get(short_id=colonise_target, game=game)

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

    order.save()

    return _redirect_preserving_selection(request, game)


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


@registration_required()
def create_race(request):
    """Create a new custom race template."""
    account = request.user.dj4xol_account
    selected_theme = account.theme if account else 'classic'
    if request.method == 'POST':
        form = ServerRaceForm(request.POST)
        if form.is_valid():
            race = form.save(commit=False)
            race.owner = account
            race.save()
            return redirect('dj4xol:index')
    else:
        form = ServerRaceForm()
    max_level = get_global_research_max_level()
    return render(request, 'dj4xol/create_race.html', {
        'form': form,
        'selected_theme': selected_theme,
        'starting_tech_costs_json': json.dumps(
            get_starting_tech_balance_costs(max_level=max_level)
        ),
    })


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
            factory.game.random_events = d.get('random_events', False)
            factory.game.max_starting_tech_level = int(
                d.get('max_starting_tech_level') or 5
            )
            if d.get('join_open_years'):
                factory.game.join_until_year = d['starting_year'] + d['join_open_years']
            factory.set_map_size(d['map_size_x'], d['map_size_y'])
            factory.set_owner(account)
            factory.create_stars(d['num_stars'], clusters=d.get('clusters', False), systems=d.get('systems', False))
            game = factory.save()
            factory.join_player(account, d['race'])
            _create_invitations(game, form.parse_invitations())
            return redirect('dj4xol:game', game_short_id=game.short_id)
    else:
        form = NewGameForm(account)
    return render(request, 'dj4xol/create_game.html', {
        'form': form,
        'selected_theme': selected_theme,
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
def help_space_combat(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_space_combat.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_invasion(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_invasion.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_index(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_index.html', {
        'user_theme': account.theme if account else 'classic',
    })


@registration_required()
def help_version_history(request):
    account = request.user.dj4xol_account
    return render(request, 'dj4xol/help_version_history.html', {
        'user_theme': account.theme if account else 'classic',
    })


def _format_tech_param_key(key):
    labels = {
        'max_warp_speed': 'Maximum Warp',
        'max_cargo_capacity': 'Cargo Capacity',
        'max_fuel': 'Fuel Capacity',
        'fuel_efficiency': 'Fuel Efficiency',
        'overmax_fuel_penalty': 'Overmax Fuel Penalty',
        'hull_thumbnail_class': 'Hull Class',
        'offense_level': 'Offense Level',
        'defense_level': 'Defense Level',
        'colony_defense_level': 'Colony Defense Level',
    }
    return labels.get(key, key.replace('_', ' ').title())


def _format_tech_param_value(key, value):
    if key in ('offense_level', 'defense_level', 'colony_defense_level'):
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
    if key == 'hull_thumbnail_class':
        text = str(value or '').strip()
        if not text:
            return value
        return text.replace('_', ' ').title()
    return value


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

    filter_qs = Technology.objects.filter(enabled=True).select_related('category')
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
        ]

    return render(request, 'dj4xol/help_technology.html', {
        'user_theme': account.theme if account else 'classic',
        'categories': categories,
        'selected_category': selected_category,
        'selected_category_id': selected_category.id if selected_category else None,
        'min_level': min_level,
        'max_level': max_level,
        'selected_tech_type': tech_type,
        'tech_type_choices': Technology.TECH_TYPE_CHOICES,
        'search_query': q,
        'all_count': all_count,
        'tech_rows': tech_rows,
    })


def _create_invitations(game, invitations):
    """Create GameInvitation records from parsed invitation list."""
    for inv_type, value in invitations:
        if inv_type == 'email':
            # Check if account exists with this email
            try:
                acct = Account.objects.get(email=value)
                GameInvitation.objects.get_or_create(game=game, account=acct)
            except Account.DoesNotExist:
                GameInvitation.objects.get_or_create(game=game, email=value)
        else:
            # Alias/username lookup
            try:
                acct = Account.objects.get(alias__iexact=value)
                GameInvitation.objects.get_or_create(game=game, account=acct)
                continue
            except Account.DoesNotExist:
                pass
            try:
                acct = Account.objects.get(django_user__username__iexact=value)
                GameInvitation.objects.get_or_create(game=game, account=acct)
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

    messages_qs = player.messages.order_by('-year', '-id')

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

    data = build_research_screen_data(player, selected_category)
    return render(request, 'dj4xol/research.html', {
        'game': game,
        'player': player,
        'is_owner': account == game.owner,
        'budget': data['budget'],
        'research_rows': data['rows'],
        'selected_category': data['selected_category'],
        'selected_research': data['selected_research'],
        'next_level_number': data['next_level_number'],
        'next_level_cost': data['next_level_cost'],
        'next_level_rp_current': data['next_level_rp_current'],
        'next_level_progress_percent': data['next_level_progress_percent'],
        'next_level_rp_per_year': data['next_level_rp_per_year'],
        'next_level_eta_years': data['next_level_eta_years'],
        'next_level_requirements': data['next_level_requirements'],
        'next_level_resource_rows': data['next_level_resource_rows'],
        'next_level_items': data['next_level_items'],
        'singular_research': player.singular_research,
        'user_theme': account.theme if account else 'classic',
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
        return redirect('dj4xol:onboarding_theme')
    if request.method == 'POST':
        form = RegistrationForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            if not request.user.is_authenticated and form.user:
                login(request, form.user)
            return redirect('dj4xol:onboarding_theme')
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
    if request.method == 'POST':
        theme = request.POST.get('theme', 'classic')
        valid_themes = [t[0] for t in Account.THEME_CHOICES]
        if theme in valid_themes:
            account.theme = theme
            account.save(update_fields=['theme'])
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
    if ServerRace.objects.filter(owner=account).exists():
        return redirect('dj4xol:index')
    if request.method == 'POST':
        form = ServerRaceForm(request.POST)
        if form.is_valid():
            race = form.save(commit=False)
            race.owner = account
            race.save()
            return redirect('dj4xol:index')
    else:
        form = ServerRaceForm()
    max_level = get_global_research_max_level()
    return render(request, 'dj4xol/onboarding_race.html', {
        'form': form,
        'selected_theme': account.theme,
        'starting_tech_costs_json': json.dumps(
            get_starting_tech_balance_costs(max_level=max_level)
        ),
    })


@registration_required()
def profile(request):
    """View user's account profile."""
    account = request.user.dj4xol_account

    # Get games the user is playing in
    playing = Player.objects.filter(account=account, game__ended=False)
    games_playing = [p.game for p in playing.select_related('game')]

    # Get races owned by the user
    races = ServerRace.objects.filter(owner=account)

    # Get games owned by the user
    games_owned = Game.objects.filter(owner=account, ended=False)

    return render(request, 'dj4xol/profile.html', {
        'account': account,
        'games_playing': games_playing,
        'games_owned': games_owned,
        'races': races,
        'theme_choices': Account.THEME_CHOICES,
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
def rename_object(request, game_short_id, object_short_id):
    """Rename a star or fleet owned by the player."""
    from django.http import JsonResponse
    from .models import Star, Fleet

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    game = Game.objects.get(short_id=game_short_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    if player.turned_in:
        return JsonResponse({'error': 'Turn already submitted'}, status=403)

    new_name = request.POST.get('name', '').strip()
    if not new_name:
        return JsonResponse({'error': 'Name is required'}, status=400)
    if len(new_name) > 30:
        return JsonResponse({'error': 'Name must be 30 characters or less'}, status=400)

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
