import json
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import (
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.password_validation import password_validators_help_text_html
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.utils.html import format_html
from urllib.parse import urlparse, urlunparse
from .models import (
    ServerRace,
    ServerRaceType,
    Game,
    Account,
    Player,
    Star,
    CustomHelpPage,
    CustomHelpPageBlock,
    ServerSettings,
    profanity_filter_settings,
)
from .name_rules import validate_non_reserved_identity_name, validate_safe_public_text
from .research import get_global_research_max_level, get_starting_tech_balance_cost
from .ai_players import (
    AI_SLOT_RANDOM_RACE,
    AI_SLOT_RANDOM_STANCE,
    ai_module_counts_towards_server_cap,
    get_create_game_ai_capacity,
    get_enabled_ai_modules,
    get_ai_max_per_game,
    get_remaining_server_ai_capacity,
    normalize_ai_module_code,
)


AI_MODULE_CONFIG_EXAMPLES = {
    'micromanager': {
        'version': 1,
        'settings': {},
    },
    'expansionist': {
        'version': 1,
        'settings': {},
    },
    'idle': {
        'version': 1,
        'settings': {},
    },
    'openai': {
        'api_base_url': 'https://api.openai.com/v1',
        'chat_completions_url': 'https://api.openai.com/v1/chat/completions',
        'api_key': 'replace-with-api-key',
        'model': 'gpt-5-mini',
        'max_iterations': 6,
        'history_chars': 18000,
        'step_output_chars': 2600,
        'snapshot_commands': [
            '/status',
            '/colonies',
            '/fleets own',
            '/research',
            '/messages priority=1 limit=20',
        ],
        'snapshot_chars': 12000,
        'snapshot_command_chars': 3000,
        'max_output_tokens': 250,
        'temperature': 0.2,
        'timeout_seconds': 25.0,
        'system_prompt': '',
    },
}


def _pretty_json_example(example):
    return json.dumps(example, indent=2)


def _module_settings_help_text(summary, example):
    return format_html(
        '{}<div class="help-text-json-example"><div>Default JSON example:</div><pre>{}</pre></div>',
        summary,
        _pretty_json_example(example),
    )


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


class UnownedStarChoiceField(forms.ModelChoiceField):
    """Star field that shows an admin-friendly location label."""

    def label_from_instance(self, obj):
        return '%s [%s] (%s, %s)' % (
            obj.name,
            obj.short_id,
            int(getattr(obj, 'x', 0) or 0),
            int(getattr(obj, 'y', 0) or 0),
        )


class AdminAddAiPlayerForm(forms.Form):
    """Admin form for adding a single AI player to an existing game."""

    ai_module = forms.ChoiceField(label='AI Player Type', choices=())
    default_diplomatic_stance = forms.ChoiceField(
        label='Default Stance',
        choices=(),
        initial=AI_SLOT_RANDOM_STANCE,
    )
    starting_tech_level = forms.IntegerField(
        label='Starting Tech Level',
        min_value=0,
        required=False,
        help_text=(
            'Leave blank to use the selected race default. Random races keep '
            'their generated starting-tech profile.'
        ),
    )
    race = forms.ChoiceField(
        label='Race',
        choices=(),
        required=False,
        initial=AI_SLOT_RANDOM_RACE,
    )
    homeworld_star = UnownedStarChoiceField(
        label='Homeworld Star',
        queryset=Star.objects.none(),
        required=False,
        help_text='Leave blank to let the game choose a random valid homeworld star.',
    )

    def __init__(self, game, *args, **kwargs):
        self.game = game
        self._enabled_modules = list(get_enabled_ai_modules())
        self._module_codes = {
            normalize_ai_module_code(module.get('code'))
            for module in self._enabled_modules
            if normalize_ai_module_code(module.get('code'))
        }
        self._race_queryset = list(
            ServerRace.objects
            .select_related('owner', 'owner__django_user')
            .order_by('name', 'id')
        )
        super().__init__(*args, **kwargs)

        max_level = max(0, int(get_global_research_max_level() or 0))
        self.fields['starting_tech_level'].max_value = max_level
        self.fields['starting_tech_level'].widget.attrs['max'] = str(max_level)

        self.fields['ai_module'].choices = [
            (
                normalize_ai_module_code(module.get('code')),
                str(module.get('label') or module.get('code') or '').strip(),
            )
            for module in self._enabled_modules
            if normalize_ai_module_code(module.get('code'))
        ]
        if self.fields['ai_module'].choices:
            self.fields['ai_module'].initial = self.fields['ai_module'].choices[0][0]

        self.fields['default_diplomatic_stance'].choices = list(Player.STANCE_CHOICES) + [
            (AI_SLOT_RANDOM_STANCE, 'Random (Hostile to Warm)'),
        ]

        race_choices = [
            (AI_SLOT_RANDOM_RACE, 'Random (generated fair race)'),
        ]
        for race in self._race_queryset:
            owner = getattr(race, 'owner', None)
            if owner is None:
                owner_label = 'server'
            else:
                owner_label = owner.alias or getattr(owner.django_user, 'username', 'player')
                if bool(getattr(race, 'public', False)):
                    owner_label = '%s public' % owner_label
                else:
                    owner_label = '%s private' % owner_label
            race_choices.append((str(race.pk), '%s (%s)' % (race.name, owner_label)))
        self.fields['race'].choices = race_choices

        self.fields['homeworld_star'].queryset = (
            self.game.stars
            .filter(player=None)
            .order_by('name', 'id')
        )

        current_ai = int(self.game.players.filter(is_ai=True).count())
        max_per_game = int(get_ai_max_per_game() or 0)
        remaining_per_game = max(0, max_per_game - current_ai)
        remaining_server = int(get_remaining_server_ai_capacity() or 0)
        self.fields['ai_module'].help_text = (
            'Game AI slots remaining: %s of %s. '
            'Server-capped AI slots remaining: %s '
            '(micromanager/expansionist/idle do not consume server cap).'
        ) % (
            remaining_per_game,
            max_per_game,
            remaining_server,
        )
        self.fields['race'].help_text = (
            'Choose a saved race template or leave the default random option '
            'for a generated fair AI race.'
        )

    def clean(self):
        cleaned = super().clean()

        available_star_count = int(self.fields['homeworld_star'].queryset.count())
        if available_star_count <= 0:
            raise forms.ValidationError(
                'This game has no unowned stars available for a new AI player.'
            )

        if not self._module_codes:
            raise forms.ValidationError(
                'No AI modules are enabled by server settings.'
            )

        module_code = normalize_ai_module_code(cleaned.get('ai_module'))
        if module_code not in self._module_codes:
            self.add_error('ai_module', 'Select a valid AI player type.')
        max_per_game = int(get_ai_max_per_game() or 0)
        current_ai = int(self.game.players.filter(is_ai=True).count())
        if current_ai >= max_per_game:
            raise forms.ValidationError(
                'This game already has the maximum %s AI player%s.'
                % (max_per_game, '' if max_per_game == 1 else 's')
            )

        if (
            module_code in self._module_codes and
            ai_module_counts_towards_server_cap(module_code) and
            int(get_remaining_server_ai_capacity() or 0) <= 0
        ):
            self.add_error(
                'ai_module',
                'No server-capped AI slots are currently available for that AI type.',
            )

        race_lookup = {str(race.pk): race for race in self._race_queryset}
        race_ref = str(cleaned.get('race') or '').strip()
        race_random = race_ref.upper() == AI_SLOT_RANDOM_RACE or not race_ref
        race_obj = None if race_random else race_lookup.get(race_ref)
        if not race_random and race_obj is None:
            self.add_error('race', 'Select a valid race or use the random option.')

        max_tech_level = max(0, int(get_global_research_max_level() or 0))
        starting_tech_level = cleaned.get('starting_tech_level')
        if starting_tech_level in (None, ''):
            if race_random:
                starting_tech_level = None
            else:
                starting_tech_level = int(getattr(race_obj, 'starting_tech_level', 0) or 0)
        else:
            starting_tech_level = int(starting_tech_level)
        if starting_tech_level is not None and starting_tech_level > max_tech_level:
            self.add_error(
                'starting_tech_level',
                'Starting tech level cannot exceed %s.' % max_tech_level,
            )

        cleaned['module_code'] = module_code
        cleaned['race_random'] = bool(race_random)
        cleaned['race'] = race_obj
        cleaned['starting_tech_level_override'] = starting_tech_level
        return cleaned


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
    improved_star_names = forms.BooleanField(
        label="Improved Star Names",
        required=False,
        help_text="Use related names for systems and nearby clusters (requires Systems)"
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
        help_text="Maximum number of human players (AI players do not count; blank = unlimited)"
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
        self._ai_modules = list(get_enabled_ai_modules())
        self._ai_capacity = int(get_create_game_ai_capacity() or 0)
        self._ai_module_field_names = [
            self._ai_module_field_name(str(module.get('code') or '').strip().lower())
            for module in self._ai_modules
            if str(module.get('code') or '').strip().lower()
        ]

        ordered = [
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
            'improved_star_names',
            'public',
            'joinable',
            'join_open_years',
            'max_players',
        ]
        if self._ai_capacity > 0 and self._ai_modules:
            self.fields['ai_player_count'] = forms.IntegerField(
                label='AI Players',
                min_value=0,
                max_value=self._ai_capacity,
                required=False,
                initial=0,
                help_text=(
                    'Total AI players for this game. Per-game cap: %s. '
                    'Remaining server-capped slots: %s '
                    '(micromanager/expansionist/idle do not consume server cap).'
                ) % (
                    int(get_ai_max_per_game() or 0),
                    int(get_remaining_server_ai_capacity() or 0),
                ),
            )
            self.fields['ai_player_config_json'] = forms.CharField(
                label='AI Slot Configuration (JSON)',
                required=False,
                widget=forms.Textarea(attrs={'rows': 6}),
                help_text=(
                    'JSON list of AI slot entries. In JavaScript-enabled browsers this '
                    'is replaced with a slot editor table. Use '
                    '"race_id": "__RANDOM__" for a generated fair random race and '
                    '"default_diplomatic_stance": "RANDOM" to randomize stance '
                    '(Hostile to Warm).'
                ),
            )
            ordered.extend(['ai_player_count', 'ai_player_config_json'])
        ordered.extend([
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
        self.order_fields(ordered)
        self.fields['max_starting_tech_level'].widget.attrs['max'] = str(
            get_global_research_max_level()
        )
        self.fields['race'].queryset = _race_queryset_for_account(account)
        self.fields['race'].account = account
        if 'ai_player_config_json' in self.fields and not self.is_bound:
            sample_module = ''
            for module in list(self._ai_modules or []):
                code = str(module.get('code') or '').strip().lower()
                if code:
                    sample_module = code
                    break
            sample_race = self.fields['race'].queryset.first()
            sample_entry = {
                'module': sample_module,
                'race_id': AI_SLOT_RANDOM_RACE,
                'starting_tech_level': int(
                    getattr(sample_race, 'starting_tech_level', 0) or 0
                ) if sample_race is not None else 0,
                'default_diplomatic_stance': AI_SLOT_RANDOM_STANCE,
            }
            self.fields['ai_player_config_json'].initial = json.dumps(
                [sample_entry],
                indent=2,
            )

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
        max_per_game = int(get_ai_max_per_game() or 0)
        remaining_server = int(get_remaining_server_ai_capacity() or 0)
        ai_cap = max(0, max_per_game)
        self._clean_ai_slot_config(cleaned, ai_cap, max_per_game, remaining_server)
        if cleaned.get('clusters') and cleaned.get('spiral_arms'):
            self.add_error('clusters', 'Clusters cannot be combined with spiral arm galaxy generation.')
            self.add_error('spiral_arms', 'Spiral arm galaxy generation cannot be combined with clusters.')
        if cleaned.get('improved_star_names') and not cleaned.get('systems'):
            self.add_error('improved_star_names', 'Improved star names require Systems to be enabled.')
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

    @staticmethod
    def _ai_module_field_name(code):
        return 'ai_module_count_%s' % str(code or '').strip().lower()

    def _legacy_ai_module_allocations_from_data(self):
        """Return legacy module allocations posted by old clients."""
        allocations = []
        for module in list(self._ai_modules or []):
            code = str(module.get('code') or '').strip().lower()
            if not code:
                continue
            field_name = self._ai_module_field_name(code)
            raw = self.data.get(field_name)
            try:
                count = int(raw or 0)
            except (TypeError, ValueError):
                count = 0
            if count <= 0:
                continue
            allocations.extend([code] * count)
        return allocations

    def _clean_ai_slot_config(self, cleaned, ai_cap, max_per_game, remaining_server):
        if 'ai_player_count' not in self.fields:
            cleaned['ai_player_slots'] = []
            return 0

        try:
            ai_count = int(cleaned.get('ai_player_count') or 0)
        except (TypeError, ValueError):
            ai_count = 0
        ai_count = max(0, ai_count)
        legacy_allocations = self._legacy_ai_module_allocations_from_data()
        if ai_count <= 0 and legacy_allocations:
            ai_count = len(legacy_allocations)
        cleaned['ai_player_count'] = ai_count

        if ai_count > ai_cap:
            self.add_error(
                'ai_player_count',
                (
                    'Requested %s AI player%s but only %s slot%s are available '
                    '(max per game %s).'
                ) % (
                    ai_count,
                    '' if ai_count == 1 else 's',
                    ai_cap,
                    '' if ai_cap == 1 else 's',
                    max_per_game,
                ),
            )

        if ai_count <= 0:
            cleaned['ai_player_slots'] = []
            return 0

        module_codes = [
            str(module.get('code') or '').strip().lower()
            for module in list(self._ai_modules or [])
            if str(module.get('code') or '').strip().lower()
        ]
        if ai_count > 0 and not module_codes:
            self.add_error(
                'ai_player_count',
                'No AI modules are enabled by server settings.',
            )
            cleaned['ai_player_slots'] = []
            return ai_count

        race_queryset = list(self.fields['race'].queryset)
        race_by_id = {str(race.id): race for race in race_queryset}
        race_by_short_id = {str(race.short_id): race for race in race_queryset}
        selected_race = cleaned.get('race')
        if selected_race is None and race_queryset:
            selected_race = race_queryset[0]
        default_module = module_codes[0] if module_codes else ''
        valid_stances = {str(code) for code, _label in Player.STANCE_CHOICES}

        try:
            max_tech_level = int(get_global_research_max_level() or 0)
        except (TypeError, ValueError):
            max_tech_level = 0
        max_tech_level = max(0, max_tech_level)

        raw_config = str(cleaned.get('ai_player_config_json') or '').strip()
        parsed_config = []
        if raw_config:
            try:
                parsed = json.loads(raw_config)
            except Exception:
                parsed = None
            if not isinstance(parsed, list):
                self.add_error(
                    'ai_player_config_json',
                    'AI slot configuration must be a JSON list.',
                )
            else:
                parsed_config = list(parsed)
                if ai_count > 0 and len(parsed_config) != ai_count:
                    self.add_error(
                        'ai_player_config_json',
                        'AI slot configuration must contain exactly %s entr%s.'
                        % (ai_count, 'y' if ai_count == 1 else 'ies'),
                    )
        elif legacy_allocations:
            parsed_config = [{'module': code} for code in legacy_allocations]

        slots = []
        for idx in range(ai_count):
            slot_data = parsed_config[idx] if idx < len(parsed_config) and isinstance(parsed_config[idx], dict) else {}
            module_code = str(
                slot_data.get('module')
                or slot_data.get('ai_module')
                or slot_data.get('module_code')
                or ''
            ).strip().lower()
            if not module_code:
                module_code = (
                    legacy_allocations[idx]
                    if idx < len(legacy_allocations) else default_module
                )
            if module_code not in module_codes:
                self.add_error(
                    'ai_player_config_json',
                    'AI slot %s has an invalid module.' % (idx + 1),
                )
                module_code = default_module

            race_ref = slot_data.get('race_id', slot_data.get('race', slot_data.get('race_short_id')))
            race_random = False
            if str(race_ref or '').strip().upper() in {
                AI_SLOT_RANDOM_RACE,
                'RANDOM',
            }:
                race_random = True
                race_ref = AI_SLOT_RANDOM_RACE
            race_obj = None
            if race_ref is not None and not race_random:
                key = str(race_ref).strip()
                race_obj = race_by_id.get(key) or race_by_short_id.get(key)
            if race_obj is None and not race_random:
                race_obj = selected_race
            if race_obj is None and not race_random:
                self.add_error(
                    'ai_player_config_json',
                    'AI slot %s must select a valid race.' % (idx + 1),
                )
                continue

            raw_tech = slot_data.get(
                'starting_tech_level',
                getattr(race_obj, 'starting_tech_level', 3) if race_obj is not None else 3,
            )
            try:
                starting_tech_level = int(raw_tech)
            except (TypeError, ValueError):
                self.add_error(
                    'ai_player_config_json',
                    'AI slot %s has an invalid starting tech level.' % (idx + 1),
                )
                starting_tech_level = int(getattr(race_obj, 'starting_tech_level', 0) or 0)
            if starting_tech_level < 0 or starting_tech_level > max_tech_level:
                self.add_error(
                    'ai_player_config_json',
                    'AI slot %s starting tech level must be between 0 and %s.'
                    % (idx + 1, max_tech_level),
                )
                starting_tech_level = max(0, min(max_tech_level, starting_tech_level))

            stance = str(
                slot_data.get(
                    'default_diplomatic_stance',
                    slot_data.get('default_stance', 'NEUTRAL'),
                ) or 'NEUTRAL'
            ).strip().upper()
            if stance == AI_SLOT_RANDOM_STANCE:
                pass
            elif stance not in valid_stances:
                self.add_error(
                    'ai_player_config_json',
                    'AI slot %s has an invalid default stance.' % (idx + 1),
                )
                stance = 'NEUTRAL'

            slots.append({
                'module_code': module_code,
                'race': race_obj,
                'race_random': bool(race_random),
                'starting_tech_level': int(starting_tech_level),
                'default_diplomatic_stance': stance,
            })

        server_capped_slots = sum(
            1 for slot in slots
            if ai_module_counts_towards_server_cap(slot.get('module_code'))
        )
        if server_capped_slots > remaining_server:
            self.add_error(
                'ai_player_config_json',
                (
                    'Requested %s server-capped AI slot%s but only %s server slot%s '
                    'are currently available.'
                ) % (
                    server_capped_slots,
                    '' if server_capped_slots == 1 else 's',
                    remaining_server,
                    '' if remaining_server == 1 else 's',
                ),
            )

        cleaned['ai_player_slots'] = slots
        return ai_count

    def parse_ai_player_slots(self):
        """Return validated AI slot configuration entries."""
        return list(self.cleaned_data.get('ai_player_slots') or [])

    def ai_slot_editor_payload(self):
        """Return JSON-safe payload for browser AI slot editor enhancement."""
        if 'ai_player_count' not in self.fields:
            return {}

        race_field = self.fields['race']
        races = []
        for race in list(race_field.queryset):
            races.append({
                'id': str(race.id),
                'short_id': str(race.short_id),
                'label': race_field.label_from_instance(race),
                'starting_tech_level': int(getattr(race, 'starting_tech_level', 0) or 0),
            })
        races.insert(0, {
            'id': AI_SLOT_RANDOM_RACE,
            'short_id': AI_SLOT_RANDOM_RACE,
            'label': 'Random (generated fair race)',
            'starting_tech_level': 3,
        })

        modules = []
        for module in list(self._ai_modules or []):
            code = str(module.get('code') or '').strip().lower()
            if not code:
                continue
            modules.append({
                'code': code,
                'label': str(module.get('label') or code.title()),
            })

        default_race_id = AI_SLOT_RANDOM_RACE
        if self.is_bound:
            raw_selected_race = self.data.get('race')
            if raw_selected_race is not None:
                selected_race_id = str(raw_selected_race).strip()
                if selected_race_id:
                    default_race_id = selected_race_id

        return {
            'capacity': int(self._ai_capacity),
            'max_starting_tech_level': int(get_global_research_max_level() or 0),
            'modules': modules,
            'races': races,
            'stances': [
                {'code': str(code), 'label': str(label)}
                for code, label in Player.STANCE_CHOICES
            ] + [{
                'code': AI_SLOT_RANDOM_STANCE,
                'label': 'Random (Hostile to Warm)',
            }],
            'default_race_id': default_race_id,
            'default_stance': AI_SLOT_RANDOM_STANCE,
        }


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
            'ai_max_per_game',
            'ai_max_per_server',
            'ai_check_in_turns',
            'ai_module_micromanager_enabled',
            'ai_module_expansionist_enabled',
            'ai_module_idle_enabled',
            'ai_module_openai_enabled',
            'ai_module_micromanager_config',
            'ai_module_expansionist_config',
            'ai_module_idle_config',
            'ai_module_openai_config',
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
        help_text=(
            'Supports paragraphs, bullet lines beginning with "- ", '
            '[links](https://example.com), and '
            '![images](https://example.com/image.png).'
        ),
        widget=forms.Textarea(attrs={
            'rows': 8,
            'class': 'rich-text-source',
            'data-rich-text-role': 'source',
        }),
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
    ai_max_per_game = forms.IntegerField(
        label='Max AIs per Game',
        required=False,
        min_value=0,
        initial=0,
        help_text='Maximum AI players that can be configured in a single game.',
    )
    ai_max_per_server = forms.IntegerField(
        label='Max AIs per Server',
        required=False,
        min_value=0,
        initial=0,
        help_text=(
            'Maximum active server-capped AI players allowed across all non-ended '
            'games (micromanager/expansionist/idle are excluded).'
        ),
    )
    ai_check_in_turns = forms.IntegerField(
        label='AIs Check In Every X Turns',
        required=False,
        min_value=1,
        initial=1,
        help_text='AI players auto-ready each turn; this value controls decision refresh cadence tracking.',
    )
    ai_module_micromanager_enabled = forms.BooleanField(
        label='Enable AI Module: Micromanager',
        required=False,
        initial=True,
        help_text='Max-tier Administration automation on all AI colonies.',
    )
    ai_module_expansionist_enabled = forms.BooleanField(
        label='Enable AI Module: Expansionist',
        required=False,
        initial=True,
        help_text='Micromanager-derived AI with stronger expansion, extraction, and growth priorities.',
    )
    ai_module_idle_enabled = forms.BooleanField(
        label='Enable AI Module: Idle',
        required=False,
        initial=True,
        help_text='Tier-3 Administration automation on all AI colonies.',
    )
    ai_module_openai_enabled = forms.BooleanField(
        label='Enable AI Module: OpenAI-Compatible',
        required=False,
        initial=False,
        help_text='Uses an OpenAI API-compatible model to drive Play CLI commands for AI turns.',
    )
    ai_module_micromanager_config = forms.CharField(
        label='Micromanager Module Settings',
        required=False,
        initial=_pretty_json_example(AI_MODULE_CONFIG_EXAMPLES['micromanager']),
        widget=forms.Textarea(attrs={
            'rows': 6,
            'spellcheck': 'false',
            'placeholder': _pretty_json_example(AI_MODULE_CONFIG_EXAMPLES['micromanager']),
        }),
        help_text=_module_settings_help_text(
            'JSON object for micromanager module settings. '
            'Current gameplay behavior does not consume module-specific keys yet.',
            AI_MODULE_CONFIG_EXAMPLES['micromanager'],
        ),
    )
    ai_module_expansionist_config = forms.CharField(
        label='Expansionist Module Settings',
        required=False,
        initial=_pretty_json_example(AI_MODULE_CONFIG_EXAMPLES['expansionist']),
        widget=forms.Textarea(attrs={
            'rows': 6,
            'spellcheck': 'false',
            'placeholder': _pretty_json_example(AI_MODULE_CONFIG_EXAMPLES['expansionist']),
        }),
        help_text=_module_settings_help_text(
            'JSON object for expansionist module settings. '
            'Current gameplay behavior does not consume module-specific keys yet.',
            AI_MODULE_CONFIG_EXAMPLES['expansionist'],
        ),
    )
    ai_module_idle_config = forms.CharField(
        label='Idle Module Settings',
        required=False,
        initial=_pretty_json_example(AI_MODULE_CONFIG_EXAMPLES['idle']),
        widget=forms.Textarea(attrs={
            'rows': 6,
            'spellcheck': 'false',
            'placeholder': _pretty_json_example(AI_MODULE_CONFIG_EXAMPLES['idle']),
        }),
        help_text=_module_settings_help_text(
            'JSON object for idle module settings. '
            'Current gameplay behavior does not consume module-specific keys yet.',
            AI_MODULE_CONFIG_EXAMPLES['idle'],
        ),
    )
    ai_module_openai_config = forms.CharField(
        label='OpenAI-Compatible Module Settings',
        required=False,
        initial=_pretty_json_example(AI_MODULE_CONFIG_EXAMPLES['openai']),
        widget=forms.Textarea(attrs={
            'rows': 16,
            'spellcheck': 'false',
            'placeholder': _pretty_json_example(AI_MODULE_CONFIG_EXAMPLES['openai']),
        }),
        help_text=_module_settings_help_text(
            'JSON settings for API-compatible chat completion and Play CLI loop behavior.',
            AI_MODULE_CONFIG_EXAMPLES['openai'],
        ),
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
        'ai_max_per_game': {
            'description': 'Maximum AI players per game',
            'default': 0,
        },
        'ai_max_per_server': {
            'description': 'Maximum active server-capped AI players per server',
            'default': 0,
        },
        'ai_check_in_turns': {
            'description': 'AI check-in cadence in turns',
            'default': 1,
        },
        'ai_module_micromanager_enabled': {
            'description': 'Enable AI module: micromanager',
            'boolean': True,
            'default': True,
        },
        'ai_module_expansionist_enabled': {
            'description': 'Enable AI module: expansionist',
            'boolean': True,
            'default': True,
        },
        'ai_module_idle_enabled': {
            'description': 'Enable AI module: idle',
            'boolean': True,
            'default': True,
        },
        'ai_module_openai_enabled': {
            'description': 'Enable AI module: openai',
            'boolean': True,
            'default': False,
        },
        'ai_module_micromanager_config': {
            'description': 'AI module config: micromanager',
            'use_long_value': True,
            'default': '',
        },
        'ai_module_expansionist_config': {
            'description': 'AI module config: expansionist',
            'use_long_value': True,
            'default': '',
        },
        'ai_module_idle_config': {
            'description': 'AI module config: idle',
            'use_long_value': True,
            'default': '',
        },
        'ai_module_openai_config': {
            'description': 'AI module config: openai',
            'use_long_value': True,
            'default': '',
        },
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
            if setting is None:
                if key in (
                    'ai_module_micromanager_config',
                    'ai_module_expansionist_config',
                    'ai_module_idle_config',
                    'ai_module_openai_config',
                ):
                    field = cls.base_fields.get(key)
                    initial[key] = str(getattr(field, 'initial', '') or '')
                    continue
                if meta.get('boolean'):
                    initial[key] = bool(meta.get('default', False))
                    continue
                if 'default' in meta:
                    initial[key] = meta.get('default')
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
            if (
                raw_value in (None, '') and
                not meta.get('boolean') and
                'default' in meta
            ):
                raw_value = meta.get('default')
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


class PasswordResetRequestForm(PasswordResetForm):
    """Styled password reset request form."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({
            'autocomplete': 'email',
            'autocorrect': 'off',
            'autocapitalize': 'none',
            'spellcheck': 'false',
        })


class PasswordResetSetForm(SetPasswordForm):
    """Styled password reset confirmation form."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        for field_name in ['new_password1', 'new_password2']:
            self.fields[field_name].widget.attrs.update({
                'autocomplete': 'new-password',
                'autocorrect': 'off',
                'autocapitalize': 'none',
                'spellcheck': 'false',
            })


class AccountPasswordChangeForm(PasswordChangeForm):
    """Profile password change form with project-consistent widgets."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields['old_password'].widget.attrs.update({
            'autocomplete': 'current-password',
            'autocorrect': 'off',
            'autocapitalize': 'none',
            'spellcheck': 'false',
        })
        for field_name in ['new_password1', 'new_password2']:
            self.fields[field_name].widget.attrs.update({
                'autocomplete': 'new-password',
                'autocorrect': 'off',
                'autocapitalize': 'none',
                'spellcheck': 'false',
            })


class CustomHelpPageForm(forms.ModelForm):
    class Meta:
        model = CustomHelpPage
        fields = [
            'title',
            'slug',
            'tagline',
            'summary',
            'nav_order',
            'published',
        ]
        widgets = {
            'summary': forms.Textarea(attrs={'rows': 2}),
            'nav_order': forms.NumberInput(attrs={'step': '1'}),
        }
        help_texts = {
            'slug': 'Used in the page URL, for example /4x/help/pages/your-slug/.',
            'summary': 'Shown on the Help index page.',
            'nav_order': 'Lower numbers appear earlier on the Help index.',
        }


class CustomHelpPageBlockForm(forms.ModelForm):
    class Meta:
        model = CustomHelpPageBlock
        fields = [
            'display_order',
            'heading',
            'body',
        ]
        widgets = {
            'display_order': forms.NumberInput(attrs={'step': '1'}),
            'body': forms.Textarea(attrs={
                'rows': 10,
                'class': 'rich-text-source',
                'data-rich-text-role': 'source',
            }),
        }
        help_texts = {
            'display_order': 'Lower numbers appear earlier on the page.',
            'body': (
                'Supports paragraphs, bullet lines beginning with "- ", '
                '[links](https://example.com), and '
                '![images](https://example.com/image.png).'
            ),
        }


CustomHelpPageBlockFormSet = forms.inlineformset_factory(
    CustomHelpPage,
    CustomHelpPageBlock,
    form=CustomHelpPageBlockForm,
    extra=1,
    can_delete=True,
)


def _normalise_optional_website_url(value):
    text = str(value or '').strip()
    if not text or text == 'https://':
        return ''
    while (
        text.startswith('https://https://') or
        text.startswith('https://http://')
    ):
        text = text[len('https://'):]
    if '://' not in text:
        text = 'https://' + text
    return text


def _capitalise_name_words(value):
    text = str(value or '')
    result = []
    should_upper = True
    for ch in text:
        if should_upper and ch.isalpha():
            result.append(ch.upper())
            should_upper = False
            continue
        result.append(ch)
        should_upper = ch.isspace()
    return ''.join(result)


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
    website_url = forms.CharField(
        required=False,
        label='Website URL',
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
        self.fields['website_url'].widget.attrs.update({
            'placeholder': 'optional',
            'data-url-prefix': 'https://',
            'autocomplete': 'url',
            'spellcheck': 'false',
            'autocorrect': 'off',
            'autocapitalize': 'none',
        })
        self.fields['full_name'].widget.attrs.update({
            'autocapitalize': 'words',
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
            _capitalise_name_words(self.cleaned_data.get('full_name')),
            'Full name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )

    def clean_website_url(self):
        website_url = _normalise_optional_website_url(
            self.cleaned_data.get('website_url')
        )
        if not website_url:
            return ''
        validator = URLValidator()
        try:
            validator(website_url)
        except ValidationError:
            raise forms.ValidationError('Enter a valid URL.')
        return website_url

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
        account.onboarding_step = Account.ONBOARDING_STEP_THEME
        if commit:
            account.save()
        self.user = user
        return account


class ChangeEmailForm(forms.Form):
    """Profile form for changing an account email address."""
    email = forms.EmailField(label='New Email')

    def __init__(self, account, *args, **kwargs):
        self.account = account
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        current_email = str(getattr(self.account, 'email', '') or '').strip()
        if email.lower() == current_email.lower():
            raise forms.ValidationError('Enter a different email address.')
        return email


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
