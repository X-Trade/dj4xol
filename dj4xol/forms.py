from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import ServerRace, ServerRaceType, Game, Account


class ServerRaceForm(forms.ModelForm):
    """Form for creating a custom race template."""
    class Meta:
        model = ServerRace
        fields = [
            'name', 'plural_name', 'formal_name', 'homeworld_name', 'race_type', 'description',
            'gravity_center', 'gravity_width',
            'temperature_center', 'temperature_width',
            'radiation_center', 'radiation_width',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'gravity_center': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'max': '2'}),
            'gravity_width': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'max': '2'}),
            'temperature_center': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'max': '2'}),
            'temperature_width': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'max': '2'}),
            'radiation_center': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'max': '2'}),
            'radiation_width': forms.NumberInput(attrs={'step': '0.1', 'min': '0', 'max': '2'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['race_type'].queryset = ServerRaceType.objects.filter(enabled=True)
        self.fields['description'].required = False

    def clean(self):
        cleaned_data = super().clean()
        # Build a temporary instance to use validation methods
        instance = ServerRace(**{k: v for k, v in cleaned_data.items() if k in [
            'gravity_center', 'gravity_width',
            'temperature_center', 'temperature_width',
            'radiation_center', 'radiation_width',
        ]})
        errors = instance.validate_habitability()
        if errors:
            raise forms.ValidationError(errors)
        return cleaned_data


class NewGameForm(forms.Form):
    """Form for creating a new game."""
    name = forms.CharField(label="Game Name", max_length=30)
    description = forms.CharField(
        label="Description",
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False
    )
    starting_year = forms.IntegerField(
        label="Starting Year",
        min_value=1,
        initial=2400
    )
    map_size_x = forms.IntegerField(
        label="Map Width",
        min_value=128,
        max_value=500,
        initial=128
    )
    map_size_y = forms.IntegerField(
        label="Map Height",
        min_value=128,
        max_value=500,
        initial=128
    )
    num_stars = forms.IntegerField(
        label="Number of Stars",
        min_value=10,
        max_value=200,
        initial=50
    )
    clusters = forms.BooleanField(
        label="Clusters",
        required=False,
        help_text="Group stars into clusters"
    )
    systems = forms.BooleanField(
        label="Systems",
        required=False,
        help_text="Add companion stars to 25% of stars"
    )
    public = forms.BooleanField(
        label="Public",
        required=False,
        help_text="Anyone can view this game"
    )
    joinable = forms.BooleanField(
        label="Open for Joining",
        required=False,
        help_text="Allow other players to join"
    )
    join_open_years = forms.IntegerField(
        label="Years Open for Joining",
        min_value=0,
        required=False,
        help_text="Auto-close joining after this many years (0 or blank = never)"
    )
    max_players = forms.IntegerField(
        label="Max Players",
        min_value=1,
        required=False,
        help_text="Maximum number of players (blank = unlimited)"
    )
    turn_scheme = forms.ChoiceField(
        label="Turn Generation",
        choices=Game.TURN_SCHEME_CHOICES,
        initial='QUORUM'
    )
    years_per_turn = forms.IntegerField(
        label="Years per Turn",
        min_value=1,
        max_value=100,
        initial=1
    )
    race = forms.ModelChoiceField(
        label="Play as Race",
        queryset=ServerRace.objects.none()
    )
    invitations = forms.CharField(
        label="Invite Players",
        max_length=500,
        required=False,
        help_text="Usernames or emails, comma-separated"
    )

    def __init__(self, account, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['race'].queryset = ServerRace.objects.filter(
            models.Q(public=True) | models.Q(owner=account)
        )

    def parse_invitations(self):
        """Parse invitations field into list of (type, value) tuples."""
        text = self.cleaned_data.get('invitations', '')
        result = []
        for item in text.split(','):
            item = item.strip()
            if not item:
                continue
            result.append(('email' if '@' in item else 'username', item))
        return result


# Import models.Q for the query
from django.db import models


class SignupForm(UserCreationForm):
    """Combined form for creating Django user and dj4xol Account."""
    alias = forms.CharField(
        label="Player Alias",
        max_length=30,
        help_text="Your display name in games"
    )
    email = forms.EmailField(
        label="Email",
        required=True
    )
    full_name = forms.CharField(
        label="Full Name",
        max_length=60,
        required=False
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            Account.objects.create(
                django_user=user,
                alias=self.cleaned_data['alias'],
                email=self.cleaned_data['email'],
                full_name=self.cleaned_data.get('full_name', '')
            )
        return user


class RegistrationForm(forms.ModelForm):
    """Form for completing dj4xol registration with existing Django user."""
    class Meta:
        model = Account
        fields = ['alias', 'email', 'full_name']

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Pre-fill email from Django user
        if user.email:
            self.fields['email'].initial = user.email
        # Pre-fill alias from username
        self.fields['alias'].initial = user.username

    def save(self, commit=True):
        account = super().save(commit=False)
        account.django_user = self.user
        if commit:
            account.save()
        return account


class JoinGameForm(forms.Form):
    """Form for joining a game with a selected race."""
    race = forms.ModelChoiceField(
        label="Play as Race",
        queryset=ServerRace.objects.none()
    )

    def __init__(self, account, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show public races and races owned by this account
        self.fields['race'].queryset = ServerRace.objects.filter(
            models.Q(public=True) | models.Q(owner=account)
        )