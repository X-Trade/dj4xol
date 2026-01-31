from django.db import models
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import resolve
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required

from dj4xol.objectdetails import DetailBuilder

from .models import Game, Player, ServerSettings, ServerRace, Account, GameInvitation
from .decorators import registration_required, player_only_view
from .turn import GameTurn
from .starmap import StarMap
from .factory import GameFactory
from .forms import ServerRaceForm, NewGameForm, SignupForm, RegistrationForm, JoinGameForm


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
    })

@registration_required()
def join_game(request, game_id):
    """Join a game with race selection."""
    game = Game.objects.get(pk=game_id)
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
                return redirect('dj4xol:game', game_id=game.pk)
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
def starmap(request, game_id):
    """
    A rudimentary map viewer.
    """
    game = Game.objects.get(pk=game_id)
    account = request.user.dj4xol_account
    # Get the Player instance for this account in this game
    player = Player.objects.filter(game=game, account=account).first()
    starmap = StarMap(game, player).render_map()

    url = request.path
    x = request.GET.get('x', None)
    y = request.GET.get('y', None)

    selected = request.GET.get('sel', None)
    detail = DetailBuilder(game, x, y, selected, player=player).build_detail()

    # Get messages for this player, most recent first
    messages = player.messages.order_by('-year', '-id') if player else []

    # Get player's homeworld for home button
    homeworld = player.homeworld if player else None

    return render(request, 'dj4xol/main.html', {
        'game': game,
        'player': player,
        'starmap': starmap,
        'detail': detail,
        'messages': messages,
        'is_owner': account == game.owner,
        'selection': {'x': x, 'y': y, 'sel': selected},
        'homeworld': homeworld,
    })


@player_only_view()
def turn_in(request, game_id):
    """Mark player as turned in for quorum-based games."""
    game = Game.objects.get(pk=game_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()

    if game.turn_scheme != 'QUORUM':
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game does not use quorum-based turns.'
        })

    player.turned_in = True
    player.save()

    # Check if quorum is met and generate turn
    turn = GameTurn(game)
    if turn.check_quorum():
        turn.generate_turn()

    return _redirect_preserving_selection(request, game_id)


@player_only_view()
def generate_turn(request, game_id):
    """Generate turn for owner-controlled games."""
    game = Game.objects.get(pk=game_id)
    account = request.user.dj4xol_account

    if game.turn_scheme != 'OWNER':
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game does not use owner-triggered turns.'
        })

    if account != game.owner:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'Only the game owner can generate turns.'
        })

    GameTurn(game).generate_turn()
    return _redirect_preserving_selection(request, game_id)


@player_only_view()
def debug_colonize(request, game_id, star_id):
    """Debug: instantly colonize a star with 1000 colonists."""
    from .models import Star
    game = Game.objects.get(pk=game_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()
    star = Star.objects.get(pk=star_id, game=game)

    star.player = player
    star.colonists = 1000
    star.save()

    return _redirect_preserving_selection(request, game_id)


@player_only_view()
def debug_create_fleet(request, game_id):
    """Debug: create a fleet at the current x/y location."""
    from .models import Fleet
    game = Game.objects.get(pk=game_id)
    account = request.user.dj4xol_account
    player = Player.objects.filter(game=game, account=account).first()

    x = int(request.POST.get('x') or request.GET.get('x') or 0)
    y = int(request.POST.get('y') or request.GET.get('y') or 0)

    fleet = Fleet.objects.create(
        game=game,
        player=player,
        name=f"Fleet {game.fleets.count() + 1}",
        x=x,
        y=y,
    )

    return _redirect_preserving_selection(request, game_id)


def _redirect_preserving_selection(request, game_id):
    """Redirect to game view, preserving x, y, sel query params."""
    from django.urls import reverse
    from urllib.parse import urlencode
    url = reverse('dj4xol:game', kwargs={'game_id': game_id})
    params = {k: request.POST.get(k) or request.GET.get(k)
              for k in ['x', 'y', 'sel'] if request.POST.get(k) or request.GET.get(k)}
    if params:
        url = f"{url}?{urlencode(params)}"
    return redirect(url)


@registration_required()
def create_race(request):
    """Create a new custom race template."""
    account = request.user.dj4xol_account
    if request.method == 'POST':
        form = ServerRaceForm(request.POST)
        if form.is_valid():
            race = form.save(commit=False)
            race.owner = account
            race.save()
            return redirect('dj4xol:index')
    else:
        form = ServerRaceForm()
    return render(request, 'dj4xol/create_race.html', {'form': form})


@registration_required()
def create_game(request):
    """Create a new game."""
    account = request.user.dj4xol_account
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
            if d.get('join_open_years'):
                factory.game.join_until_year = d['starting_year'] + d['join_open_years']
            factory.set_map_size(d['map_size_x'], d['map_size_y'])
            factory.set_owner(account)
            factory.create_stars(d['num_stars'], clusters=d.get('clusters', False), systems=d.get('systems', False))
            game = factory.save()
            factory.join_player(account, d['race'])
            _create_invitations(game, form.parse_invitations())
            return redirect('dj4xol:game', game_id=game.pk)
    else:
        form = NewGameForm(account)
    return render(request, 'dj4xol/create_game.html', {'form': form})


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
            # Username lookup
            try:
                acct = Account.objects.get(django_user__username=value)
                GameInvitation.objects.get_or_create(game=game, account=acct)
            except Account.DoesNotExist:
                pass  # Silently ignore invalid usernames


def signup(request):
    """Create a new Django user and dj4xol Account together."""
    if request.user.is_authenticated:
        return redirect('dj4xol:index')
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dj4xol:index')
    else:
        form = SignupForm()
    return render(request, 'dj4xol/signup.html', {'form': form})


@login_required
def register(request):
    """Complete dj4xol registration for existing Django user."""
    # Check if already registered
    if hasattr(request.user, 'dj4xol_account'):
        return redirect('dj4xol:index')
    if request.method == 'POST':
        form = RegistrationForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            return redirect('dj4xol:index')
    else:
        form = RegistrationForm(request.user)
    return render(request, 'dj4xol/register.html', {'form': form})

