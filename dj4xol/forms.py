from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import password_validators_help_text_html
from django.db import models
from urllib.parse import urlparse, urlunparse
from .models import (
    ServerRace,
    ServerRaceType,
    Game,
    Account,
    ServerSettings,
    profanity_filter_settings,
)
from .name_rules import validate_non_reserved_identity_name, validate_safe_public_text
from .research import get_global_research_max_level, get_starting_tech_balance_cost


def _race_queryset_for_account(account):
    """Return race choices ordered as own, server, then other public races."""
    return (
        ServerRace.objects
        .filter(models.Q(public=True) | models.Q(owner=account))
        .annotate(
            _own_rank=models.Case(
                models.When(owner=account, then=models.Value(0)),
                default=models.Value(1),
                output_field=models.IntegerField(),
            ),
            _server_rank=models.Case(
                models.When(owner__isnull=True, then=models.Value(0)),
                default=models.Value(1),
                output_field=models.IntegerField(),
            ),
        )
        .order_by('_own_rank', '_server_rank', 'name', 'id')
    )


class RaceChoiceField(forms.ModelChoiceField):
    """Race field that annotates labels by ownership."""

    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop('account', None)
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        label = obj.name
        account_pk = getattr(self.account, 'pk', None)
        if account_pk is not None and obj.owner_id == account_pk:
            return '%s (yours)' % label
        if obj.owner_id is None:
            return '%s (server)' % label
        return label


class ServerRaceForm(forms.ModelForm):
    """Form for creating a custom race template."""
    spend_leftover_on_minerals = forms.BooleanField(
        required=False,
        label="Spend leftover points on surface minerals"
    )
    spend_leftover_on_research = forms.BooleanField(
        required=False,
        label="Spend leftover points on research"
    )
    class Meta:
        model = ServerRace
        fields = [
            'name', 'plural_name', 'homeworld_name', 'race_type', 'public', 'description',
            'starting_colonists',
            'starting_mines', 'starting_factories', 'starting_labs',
            'starting_shipyards', 'starting_fleets', 'starting_tech_level',
            'convert_unused_buildpoints_to_research', 'singular_research',
            'fixed_homeworld',
            'gravity_center', 'gravity_width',
            'temperature_center', 'temperature_width',
            'radiation_center', 'radiation_width',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'starting_colonists': forms.NumberInput(attrs={'step': '1', 'min': '1'}),
            'starting_mines': forms.NumberInput(attrs={'step': '1', 'min': '0'}),
            'starting_factories': forms.NumberInput(attrs={'step': '1', 'min': '0'}),
            'starting_labs': forms.NumberInput(attrs={'step': '1', 'min': '0'}),
            'starting_shipyards': forms.NumberInput(attrs={'step': '1', 'min': '0'}),
            'starting_fleets': forms.NumberInput(attrs={'step': '1', 'min': '0'}),
            'starting_tech_level': forms.NumberInput(attrs={'step': '1', 'min': '0'}),
            'gravity_center': forms.NumberInput(attrs={'step': '0.05', 'min': '0', 'max': '2'}),
            'gravity_width': forms.NumberInput(attrs={'step': '0.1', 'min': '0.1', 'max': '2'}),
            'temperature_center': forms.NumberInput(attrs={'step': '0.05', 'min': '0', 'max': '2'}),
            'temperature_width': forms.NumberInput(attrs={'step': '0.1', 'min': '0.1', 'max': '2'}),
            'radiation_center': forms.NumberInput(attrs={'step': '0.05', 'min': '0', 'max': '2'}),
            'radiation_width': forms.NumberInput(attrs={'step': '0.1', 'min': '0.1', 'max': '2'}),
        }

    def __init__(self, *args, **kwargs):
        show_public = bool(kwargs.pop('show_public', False))
        selected_race_type = kwargs.pop('selected_race_type', None)
        super().__init__(*args, **kwargs)
        max_level = get_global_research_max_level()
        self.fields['race_type'].queryset = (
            ServerRaceType.objects.filter(enabled=True).order_by('display_order', 'name', 'code')
        )
        self.fields['race_type'].empty_label = None
        if selected_race_type and not self.is_bound:
            self.fields['race_type'].initial = selected_race_type
        self.fields['description'].required = False
        if not show_public and 'public' in self.fields:
            self.fields.pop('public')
        self.fields['starting_tech_level'].widget.attrs['max'] = str(max_level)
        if self.instance and self.instance.pk:
            self.fields['spend_leftover_on_research'].initial = bool(
                self.instance.spend_leftover_points_on_research
            )
            self.fields['spend_leftover_on_minerals'].initial = bool(
                self.instance.leftover_points and not self.instance.spend_leftover_points_on_research
            )
        for field in [
            'gravity_center', 'gravity_width',
            'temperature_center', 'temperature_width',
            'radiation_center', 'radiation_width',
        ]:
            css_class = self.fields[field].widget.attrs.get('class', '')
            self.fields[field].widget.attrs['class'] = (css_class + ' habitability-field').strip()

    def clean(self):
        cleaned_data = super().clean()
        from .habitability_rules import RaceCreationRules
        profanity_filter = profanity_filter_settings()

        for field_name, label in [
            ('name', 'Race name'),
            ('plural_name', 'Race plural name'),
            ('homeworld_name', 'Homeworld name'),
        ]:
            value = cleaned_data.get(field_name)
            if value:
                try:
                    cleaned_data[field_name] = validate_non_reserved_identity_name(
                        value,
                        label,
                        block_profanity=profanity_filter['enabled'],
                        profanity_whitelist=profanity_filter['whitelist'],
                        profanity_blacklist=profanity_filter['blacklist'],
                    )
                except forms.ValidationError as exc:
                    self.add_error(field_name, exc)
        description = cleaned_data.get('description')
        if description:
            try:
                cleaned_data['description'] = validate_safe_public_text(
                    description,
                    label='Race description',
                    allow_newlines=True,
                    block_profanity=profanity_filter['enabled'],
                    profanity_whitelist=profanity_filter['whitelist'],
                    profanity_blacklist=profanity_filter['blacklist'],
                )
            except forms.ValidationError as exc:
                self.add_error('description', exc)

        spend_leftover_on_minerals = cleaned_data.get('spend_leftover_on_minerals', False)
        spend_leftover_on_research = cleaned_data.get('spend_leftover_on_research', False)
        if spend_leftover_on_minerals and spend_leftover_on_research:
            raise forms.ValidationError(
                'Choose only one leftover points option: minerals or research.'
            )

        race_type = cleaned_data.get('race_type')
        if race_type is not None:
            for env, field_name in [
                ('gravity', 'ignores_gravity'),
                ('temperature', 'ignores_temperature'),
                ('radiation', 'ignores_radiation'),
            ]:
                if bool(getattr(race_type, field_name, False)):
                    cleaned_data['%s_center' % env] = 1.0
                    cleaned_data['%s_width' % env] = 1.0

        rules = RaceCreationRules(
            centers={
                'gravity': cleaned_data.get('gravity_center', 1.0),
                'temperature': cleaned_data.get('temperature_center', 1.0),
                'radiation': cleaned_data.get('radiation_center', 1.0),
            },
            widths={
                'gravity': cleaned_data.get('gravity_width', 1.0),
                'temperature': cleaned_data.get('temperature_width', 1.0),
                'radiation': cleaned_data.get('radiation_width', 1.0),
            },
            starting_colonists=cleaned_data.get('starting_colonists', 20),
            starting_mines=cleaned_data.get('starting_mines', 4),
            starting_factories=cleaned_data.get('starting_factories', 2),
            starting_labs=cleaned_data.get('starting_labs', 1),
            starting_shipyards=cleaned_data.get('starting_shipyards', 1),
            starting_fleets=cleaned_data.get('starting_fleets', 2),
            starting_tech_level=cleaned_data.get('starting_tech_level', 3),
            starting_tech_level_cost=get_starting_tech_balance_cost(
                cleaned_data.get('starting_tech_level', 3)
            ),
            race_type_points_balance=(
                float(getattr(race_type, 'race_creation_points_balance', 0.0) or 0.0)
                if race_type is not None else 0.0
            ),
            convert_unused_buildpoints_to_research=cleaned_data.get(
                'convert_unused_buildpoints_to_research', False
            ),
            singular_research=cleaned_data.get('singular_research', False),
            fixed_homeworld=cleaned_data.get('fixed_homeworld', False),
        )
        max_level = get_global_research_max_level()
        chosen_level = int(cleaned_data.get('starting_tech_level', 0) or 0)
        if chosen_level > max_level:
            self.add_error(
                'starting_tech_level',
                'Starting tech level cannot exceed %s.' % max_level
            )
        errors = rules.validate()
        if errors:
            raise forms.ValidationError(errors)
        cleaned_data['__rules__'] = rules
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        rules = self.cleaned_data.get('__rules__')
        spend_leftover_on_minerals = self.cleaned_data.get('spend_leftover_on_minerals')
        spend_leftover_on_research = self.cleaned_data.get('spend_leftover_on_research')
        if rules and (spend_leftover_on_minerals or spend_leftover_on_research):
            instance.leftover_points = max(0.0, rules.budget - rules.total_cost())
        else:
            instance.leftover_points = 0.0
        instance.spend_leftover_points_on_research = bool(spend_leftover_on_research)
        if commit:
            instance.save()
        return instance


class NewGameForm(forms.Form):
    """Form for creating a new game."""
    RESEARCH_COST_CHOICES = [
        (0.1, '0.1x (/10)'),
        (0.25, '0.25x (/4)'),
        (0.5, '0.5x (/2)'),
        (1.0, '1x (Normal)'),
        (2.0, '2x'),
        (3.0, '3x'),
        (5.0, '5x'),
        (10.0, '10x'),
    ]
    WARP_SPEED_CHOICES = [
        (0.5, '0.5x (/2)'),
        (1.0, '1x (Normal)'),
        (2.0, '2x'),
        (3.0, '3x'),
        (4.0, '4x'),
    ]
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
        max_value=300,
        initial=50
    )
    clusters = forms.BooleanField(
        label="Clusters",
        required=False,
        help_text="Group stars into clusters"
    )
    spiral_arms = forms.BooleanField(
        label="Spiral Arm Galaxy",
        required=False,
        help_text="Generate a spiral arm galaxy (exclusive with clusters)"
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
    research_cost_multiplier = forms.TypedChoiceField(
        label="Research Cost",
        choices=RESEARCH_COST_CHOICES,
        coerce=float,
        initial=1.0,
        help_text="Scales RP and mineral requirements for all technologies."
    )
    warp_speed_multiplier = forms.TypedChoiceField(
        label="Warp Speed Multiplier",
        choices=WARP_SPEED_CHOICES,
        coerce=float,
        initial=1.0,
        help_text="Scales distance traveled per year without changing fuel use."
    )
    random_events = forms.BooleanField(
        label="Random Events",
        required=False,
        initial=True,
        help_text="Enable random events affecting colonies"
    )
    anomalies_enabled = forms.BooleanField(
        label="Anomalies",
        required=False,
        initial=True,
        help_text="Enable anomalies and anomaly interactions for fleets"
    )
    anomaly_spawn_rate = forms.ChoiceField(
        label="Anomaly Spawn Rate",
        choices=[
            ('HIGH', 'High (x2)'),
            ('NORMAL', 'Normal'),
            ('LOW', 'Low (/2)'),
        ],
        initial='NORMAL',
    )
    no_scanners = forms.BooleanField(
        label="No Scanners",
        required=False,
        help_text="Disable scanner range visibility rules (classic map visibility). Scanner tech still affects visit report quality."
    )
    max_starting_tech_level = forms.IntegerField(
        label="Max Starting Tech Level",
        min_value=0,
        required=False,
        initial=5,
        help_text="Highest starting tech level a race can keep in this game. Races above this are clamped and the difference is refunded into leftover points."
    )
    race = RaceChoiceField(
        label="Play as Race",
        queryset=ServerRace.objects.none()
    )
    invitations = forms.CharField(
        label="Invite Players",
        max_length=500,
        required=False,
        help_text="Usernames or emails, comma-separated"
    )

    def clean_name(self):
        profanity_filter = profanity_filter_settings()
        return validate_safe_public_text(
            self.cleaned_data.get('name'),
            'Game name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )

    def clean_description(self):
        profanity_filter = profanity_filter_settings()
        return validate_safe_public_text(
            self.cleaned_data.get('description'),
            'Game description',
            allow_newlines=True,
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )

    def __init__(self, account, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields([
            'name',
            'description',
            'race',
            'starting_year',
            'map_size_x',
            'map_size_y',
            'num_stars',
            'clusters',
            'spiral_arms',
            'systems',
            'public',
            'joinable',
            'join_open_years',
            'max_players',
            'turn_scheme',
            'years_per_turn',
            'research_cost_multiplier',
            'warp_speed_multiplier',
            'random_events',
            'anomalies_enabled',
            'anomaly_spawn_rate',
            'no_scanners',
            'max_starting_tech_level',
            'invitations',
        ])
        self.fields['max_starting_tech_level'].widget.attrs['max'] = str(
            get_global_research_max_level()
        )
        self.fields['race'].queryset = _race_queryset_for_account(account)
        self.fields['race'].account = account

    def clean_max_starting_tech_level(self):
        max_level = get_global_research_max_level()
        value = self.cleaned_data.get('max_starting_tech_level')
        if value is None:
            return 5
        value = int(value)
        if value > max_level:
            raise forms.ValidationError(
                'Max starting tech level cannot exceed %s.' % max_level
            )
        return value

    def clean_research_cost_multiplier(self):
        value = self.cleaned_data.get('research_cost_multiplier')
        if value is None:
            return 1.0
        value = float(value)
        return max(0.1, min(10.0, value))

    def clean_warp_speed_multiplier(self):
        value = self.cleaned_data.get('warp_speed_multiplier')
        if value is None:
            return 1.0
        value = float(value)
        return max(0.5, min(4.0, value))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('clusters') and cleaned.get('spiral_arms'):
            self.add_error('clusters', 'Clusters cannot be combined with spiral arm galaxy generation.')
            self.add_error('spiral_arms', 'Spiral arm galaxy generation cannot be combined with clusters.')
        return cleaned

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


class ServerSettingsForm(forms.Form):
    SECTION_ORDER = [
        ('General (web)', [
            'server_name',
            'server_tagline',
            'server_admin',
            'server_url',
            'server_welcome',
            'allow_self_signup',
            'allow_player_public_races',
            'enable_spectator_mode',
            'max_diplomatic_requests_per_race_per_turn',
            'enable_debug_actions',
            'enable_play_api',
        ]),
        ('Email', [
            'server_contact',
            'enable_email',
        ]),
        ('AI Integration', [
            'enable_gpt',
        ]),
        ('Profanity Filter', [
            'enable_profanity_filter',
            'profanity_filter_whitelist',
            'profanity_filter_blacklist',
        ]),
    ]

    server_name = forms.CharField(label="Server Name", max_length=120)
    server_tagline = forms.CharField(label="Server Tagline", max_length=255, required=False)
    server_admin = forms.CharField(label="Server Admin", max_length=120, required=False)
    server_contact = forms.EmailField(
        label="Server Contact Email",
        required=False,
        help_text="Public contact address shown in server-facing email and profile/help contexts.",
    )
    server_url = forms.URLField(
        label="Public Server URL",
        required=False,
        help_text="Used for links in emails. Use the public site root only; /4x and trailing slashes are removed automatically.",
    )
    server_welcome = forms.CharField(
        label="Homepage Welcome",
        required=False,
        widget=forms.Textarea(attrs={'rows': 8}),
    )
    allow_self_signup = forms.BooleanField(
        label="Allow Self Sign-up",
        required=False,
        help_text="Allows visitors without an account to register themselves through the onboarding flow.",
    )
    enable_email = forms.BooleanField(
        label="Enable Email",
        required=False,
        help_text="Enables outgoing server email, including rollups, invitations, and test emails.",
    )
    allow_player_public_races = forms.BooleanField(
        label="Allow Player Public Races",
        required=False,
        help_text="Allows non-staff players to publish race templates for others to use.",
    )
    enable_spectator_mode = forms.BooleanField(
        label="Enable Spectator Mode",
        required=False,
        help_text="Shows View actions for public games and allows spectator access.",
    )
    max_diplomatic_requests_per_race_per_turn = forms.IntegerField(
        label="Diplomatic Requests Per Race Per Turn",
        required=True,
        min_value=1,
        help_text="Maximum diplomatic requests a player can send to the same race in one turn.",
        initial=2,
    )
    enable_gpt = forms.BooleanField(
        label="Enable GPT",
        required=False,
    )
    enable_debug_actions = forms.BooleanField(
        label="Enable Debug Actions",
        required=False,
        help_text="Shows staff-only debug actions in game panels and related admin UI.",
    )
    enable_play_api = forms.BooleanField(
        label="Enable Web Play CLI",
        required=False,
        help_text="Enables the authenticated in-browser Play CLI overlay and its web API.",
    )
    enable_profanity_filter = forms.BooleanField(
        label="Enable Profanity Filter",
        required=False,
        help_text="Blocks profane names and public text according to this server's social policy.",
    )
    profanity_filter_whitelist = forms.CharField(
        label="Profanity Whitelist",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text="Optional allowed terms to ignore during profanity checks, for false positives. Terms are matched after removing spaces and punctuation.",
    )
    profanity_filter_blacklist = forms.CharField(
        label="Profanity Blacklist",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text="Optional extra blocked terms for this server. Separate terms with commas or spaces. Terms are matched after removing spaces and punctuation.",
    )

    SETTINGS_META = {
        'server_name': {'description': 'Server name'},
        'server_tagline': {'description': 'Server tagline'},
        'server_admin': {'description': "Server admin's name"},
        'server_contact': {'description': "Server admin's email"},
        'server_url': {'description': 'Server URL', 'use_long_value': True},
        'server_welcome': {'description': 'Welcome message on homepage', 'use_long_value': True},
        'allow_self_signup': {'description': 'Allow self-sign-up', 'boolean': True},
        'enable_email': {'description': 'Enable email', 'boolean': True},
        'allow_player_public_races': {
            'description': 'Allow players to publish public races',
            'boolean': True,
            'default': False,
        },
        'enable_spectator_mode': {
            'description': 'Enable spectator mode',
            'boolean': True,
            'default': True,
        },
        'max_diplomatic_requests_per_race_per_turn': {
            'description': 'Maximum diplomatic requests per race per turn',
            'default': 2,
        },
        'enable_gpt': {'description': 'Enable GPT API usage', 'boolean': True},
        'enable_debug_actions': {'description': 'Enable debug actions in game panels', 'boolean': True},
        'enable_play_api': {'description': 'Enable web Play CLI API', 'boolean': True},
        'enable_profanity_filter': {'description': 'Enable profanity filter', 'boolean': True, 'default': True},
        'profanity_filter_whitelist': {'description': 'Profanity filter whitelist', 'use_long_value': True},
        'profanity_filter_blacklist': {'description': 'Profanity filter blacklist', 'use_long_value': True},
    }

    @classmethod
    def initial_from_settings(cls):
        initial = {}
        for key, meta in cls.SETTINGS_META.items():
            setting = ServerSettings.objects.filter(key=key).first()
            if setting is None and meta.get('boolean'):
                initial[key] = bool(meta.get('default', False))
                continue
            value = setting.long_value or setting.value if setting else ''
            if meta.get('boolean'):
                initial[key] = str(value).strip().lower() in ('1', 'true', 'yes', 'on')
            else:
                initial[key] = value
        return initial

    def clean_server_url(self):
        raw_value = (self.cleaned_data.get('server_url') or '').strip()
        if not raw_value:
            return ''
        parsed = urlparse(raw_value)
        path = (parsed.path or '').rstrip('/')
        if path == '/4x':
            path = ''
        normalized = parsed._replace(path=path, params='', query='', fragment='')
        return urlunparse(normalized).rstrip('/')

    def save(self, user=None):
        for key, meta in self.SETTINGS_META.items():
            raw_value = self.cleaned_data.get(key)
            if meta.get('boolean'):
                stored = 'True' if raw_value else 'False'
            else:
                stored = str(raw_value or '')
            use_long_value = bool(meta.get('use_long_value'))
            value = ''
            long_value = ''
            if use_long_value:
                long_value = stored
                value = stored if len(stored) <= 30 else ''
            else:
                if len(stored) <= 30:
                    value = stored
                else:
                    long_value = stored
            defaults = {
                'value': value,
                'long_value': long_value,
                'description': meta.get('description', key.replace('_', ' ').title()),
                'modified_by': user,
            }
            ServerSettings.objects.update_or_create(key=key, defaults=defaults)

    def iter_sections(self):
        for title, field_names in self.SECTION_ORDER:
            yield title, [self[name] for name in field_names if name in self.fields]

class SignupForm(UserCreationForm):
    """Combined form for creating Django user and dj4xol Account."""
    email = forms.EmailField(
        label="Email",
        required=True
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'spellcheck': 'false',
            'autocorrect': 'off',
            'autocapitalize': 'none',
        })

    def clean_username(self):
        username = super(SignupForm, self).clean_username()
        profanity_filter = profanity_filter_settings()
        validate_non_reserved_identity_name(
            username,
            'Username',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class RegistrationForm(forms.ModelForm):
    """Registration form for account profile, with optional Django user creation."""
    email_game_rollups_per_day = forms.TypedChoiceField(
        choices=[(0, '0'), (1, '1'), (2, '2'), (3, '3'), (4, '4')],
        coerce=int,
        required=False,
        label='Send me up to x message-rollups per day',
    )
    username = forms.CharField(
        required=False,
        max_length=150,
        help_text='Required when creating a new login.',
    )
    password1 = forms.CharField(
        required=False,
        label='Password',
        widget=forms.PasswordInput(),
        help_text=password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        required=False,
        label='Confirm Password',
        widget=forms.PasswordInput(),
    )

    class Meta:
        model = Account
        fields = [
            'alias',
            'email',
            'full_name',
            'website_url',
            'email_game_updates',
            'email_game_rollups_per_day',
            'email_newsletter',
        ]
        labels = {
            'email_game_updates': 'Send me updates about my game progress',
            'email_newsletter': 'Send me newsletters about DJ4XOL and the server',
        }

    def __init__(self, user, *args, **kwargs):
        self.user = user if user and user.is_authenticated else None
        super().__init__(*args, **kwargs)
        self.fields['alias'].widget.attrs.update({
            'spellcheck': 'false',
            'autocorrect': 'off',
            'autocapitalize': 'none',
        })
        self.fields['username'].widget.attrs.update({
            'spellcheck': 'false',
            'autocorrect': 'off',
            'autocapitalize': 'none',
        })
        self.create_user = self.user is None
        if not self.is_bound and (not self.instance or not self.instance.pk):
            # New sign-ups must opt in explicitly to newsletters.
            self.fields['email_newsletter'].initial = False
        if not self.is_bound and self.instance and self.instance.pk:
            if not self.instance.email_game_updates:
                self.fields['email_game_rollups_per_day'].initial = 0
        if not self.create_user:
            # Hide Django user-creation fields for existing authenticated users.
            self.fields.pop('username')
            self.fields.pop('password1')
            self.fields.pop('password2')
            if self.user.email:
                self.fields['email'].initial = self.user.email
            self.fields['alias'].initial = self.user.username

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not self.create_user:
            return username
        if not username:
            raise forms.ValidationError('This field is required.')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('A user with that username already exists.')
        profanity_filter = profanity_filter_settings()
        validate_non_reserved_identity_name(
            username,
            'Username',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        return username

    def clean_alias(self):
        alias = (self.cleaned_data.get('alias') or '').strip()
        profanity_filter = profanity_filter_settings()
        validate_non_reserved_identity_name(
            alias,
            'Account name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        return alias

    def clean_full_name(self):
        profanity_filter = profanity_filter_settings()
        return validate_safe_public_text(
            self.cleaned_data.get('full_name'),
            'Full name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )

    def clean(self):
        cleaned = super().clean()
        if not self.create_user:
            email_updates = bool(cleaned.get('email_game_updates'))
            rollups = cleaned.get('email_game_rollups_per_day')
            if not email_updates:
                cleaned['email_game_rollups_per_day'] = 0
            else:
                try:
                    rollups = int(rollups)
                except (TypeError, ValueError):
                    rollups = 1
                rollups = max(1, min(4, rollups))
                cleaned['email_game_rollups_per_day'] = rollups
            return cleaned
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if not password1:
            self.add_error('password1', 'This field is required.')
        if not password2:
            self.add_error('password2', 'This field is required.')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The two password fields did not match.')
        email_updates = bool(cleaned.get('email_game_updates'))
        rollups = cleaned.get('email_game_rollups_per_day')
        if not email_updates:
            cleaned['email_game_rollups_per_day'] = 0
        else:
            try:
                rollups = int(rollups)
            except (TypeError, ValueError):
                rollups = 1
            rollups = max(1, min(4, rollups))
            cleaned['email_game_rollups_per_day'] = rollups
        return cleaned

    def save(self, commit=True):
        user = self.user
        if self.create_user:
            user = User.objects.create_user(
                username=self.cleaned_data['username'],
                email=self.cleaned_data.get('email', ''),
                password=self.cleaned_data['password1'],
            )
        account = super().save(commit=False)
        account.django_user = user
        if commit:
            account.save()
        self.user = user
        return account


class JoinGameForm(forms.Form):
    """Form for joining a game with a selected race."""
    race = RaceChoiceField(
        label="Play as Race",
        queryset=ServerRace.objects.none()
    )

    def __init__(self, account, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['race'].queryset = _race_queryset_for_account(account)
        self.fields['race'].account = account
