from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import resolve
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required

from dj4xol.objectdetails import DetailBuilder

from .models import Game, Player, ServerSettings, ServerRace
from .decorators import registration_required, player_only_view
from .turn import GameTurn
from .starmap import StarMap
from .factory import GameFactory
from .forms import ServerRaceForm, NewGameForm, SignupForm, RegistrationForm, JoinGameForm


@registration_required()
def gamelist(request):
    """
    index of all games the user can see
    """
    account = request.user.dj4xol_account
    # Get games where this account has a Player instance
    my_games = Game.objects.filter(
        pk__in=Player.objects.filter(account=account).values('game'),
        ended=False
    )
    hosted_games = Game.objects.filter(owner=account)
    open_games = Game.objects.filter(public=True, ended=False)
    return render(request, 'dj4xol/games.html',
                  {'account': account,
                   'my_games': my_games,
                   'open_games': open_games,
                   'server_settings': ServerSettings.all_to_dict()})

@registration_required()
def join_game(request, game_id):
    """Join a game with race selection."""
    game = Game.objects.get(pk=game_id)
    account = request.user.dj4xol_account

    # Check if already in this game
    if game.players.filter(account=account).exists():
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'You are already playing in this game.'
        })

    # Check if game is joinable
    if not game.joinable:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game is not open for joining.'
        })

    # Check max players
    if game.max_players and game.players.count() >= game.max_players:
        return render(request, 'dj4xol/forbidden.html', {
            'message': 'This game is full.'
        })

    if request.method == 'POST':
        form = JoinGameForm(account, request.POST)
        if form.is_valid():
            player = GameFactory(game).join_player(account, form.cleaned_data['race'])
            if player:
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
    detail = DetailBuilder(game, x, y, selected).build_detail()

    return render(request, 'dj4xol/main.html',
                  {'game': game,
                   'player': player,
                   'starmap': starmap,
                   'detail': detail})


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
            if d.get('join_open_years'):
                factory.game.join_until_year = d['starting_year'] + d['join_open_years']
            factory.set_map_size(d['map_size_x'], d['map_size_y'])
            factory.set_owner(account)
            factory.create_stars(d['num_stars'])
            game = factory.save()
            factory.join_player(account, d['race'])
            return redirect('dj4xol:game', game_id=game.pk)
    else:
        form = NewGameForm(account)
    return render(request, 'dj4xol/create_game.html', {'form': form})


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

