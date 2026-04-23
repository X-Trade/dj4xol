from .models import Game, Player, GameMessage
from .secret_resources import SECRET_RESOURCE_KEYS, get_secret_resource_name
from .map_object_rules import (
    format_space_label,
    format_salvage_label,
    format_map_link,
)
import random
from itertools import chain
from django.utils.html import escape


def map_object_link(obj):
    """Format a map object (Star/Fleet) as a clickable link."""
    from django.urls import reverse
    base_url = reverse('dj4xol:game', args=[obj.game.short_id])
    return format_map_link(base_url, obj.x, obj.y, obj.name, short_id=obj.short_id)


def map_coordinate_link(game, x, y, label=None):
    """Format map coordinates as a clickable link."""
    from django.urls import reverse
    if label is None:
        label = format_space(x, y)
    base_url = reverse('dj4xol:game', args=[game.short_id])
    return format_map_link(base_url, x, y, label)


def diplomacy_player_link(game, player, label=None):
    """Format a player/race as a clickable link to diplomacy detail."""
    from django.urls import reverse
    if player is None:
        return escape(label or 'Unknown race')
    base_url = reverse('dj4xol:diplomacy', args=[game.short_id])
    target = escape(getattr(player, 'short_id', ''))
    text = escape(label or getattr(player, 'name', 'Unknown race'))
    return '<a href="%s?target=%s">%s</a>' % (base_url, target, text)


def format_space(x, y):
    return format_space_label(x, y)


def format_space_link(game, x, y):
    return map_coordinate_link(game, x, y, label=format_space_label(x, y))


def format_salvage(x, y):
    return format_salvage_label(x, y)


def format_map_object(obj, link=True):
    """Format a map object name, optionally with a hyperlink."""
    if obj is None:
        return ""
    from .models import Star, Fleet, Salvage
    if isinstance(obj, Salvage):
        name = obj.name
    elif isinstance(obj, (Star, Fleet)):
        name = obj.name
    else:
        name = getattr(obj, 'name', str(obj))
    if link and hasattr(obj, 'game'):
        return map_object_link(obj)
    return name


def format_map_object_reference(obj=None, name=None, link=True):
    """Format a map object when an object may not always be available."""
    if obj is not None:
        return format_map_object(obj, link=link)
    if name is None:
        return ""
    return escape(str(name))


RESOURCE_DISPLAY_NAMES = {
    'ironium': 'Ironium',
    'boranium': 'Boranium',
    'germanium': 'Germanium',
}


def format_resource_name(resource_key):
    if resource_key in SECRET_RESOURCE_KEYS:
        return get_secret_resource_name(resource_key)
    return RESOURCE_DISPLAY_NAMES.get(resource_key, str(resource_key).title())


def format_location(obj=None, x=None, y=None, link=True, game=None):
    """Format a location as a map object or empty space."""
    if obj is not None:
        return format_map_object(obj, link=link)
    if x is not None and y is not None:
        if game is not None:
            from .models import Anomaly, Star
            anomaly = Anomaly.objects.filter(game=game, x=x, y=y).first()
            if anomaly is not None:
                return format_map_object(anomaly, link=link)
            star = Star.objects.filter(game=game, x=x, y=y).first()
            if star is not None:
                return format_map_object(star, link=link)
        if link and game is not None:
            return format_space_link(game, x, y)
        return format_space(x, y)
    return ""


def weighted_random_choice(choices, offset, window_size=1):
        """Select a random choice from a list of choices, with a moving window based on intensity."""
        position = offset * (len(choices)-1) + random.randint(0-window_size, window_size)
        position = min(max(position, 0), len(choices)-1)
        return choices[int(position)]

class GameEvent():
    game = None
    player = None
    encounter_player = None

class EventFactory():
    def __init__(self, game, player, event = None):
        if not event:
            event = GameEvent()
        self.event = event


class MessageFactory():
    POSITIVE_ADVERBS = ['respectfully', 'humbly', 'sincerely', 'cordially', 'thoroughly', 'warmly', 'cheerfully', 'gratefully', 'faithfully', 'earnestly', 'gladly', 'graciously', 'joyfully', 'kindly', 'lovingly', 'patiently', 'pleasantly', 'proudly', 'thankfully', 'vivaciously', 'zealously', 'zestfully']
    NEGATIVE_ADVERBS = ['dutifully', 'sumarily', 'worriedly', 'anxiously', 'mysteriously', 'wearily', 'tensely', 'coldly', 'defiantly', 'grevously', 'painfully', 'gravely', 'bitterly', 'mockingly', 'wildly', 'wickedly', 'wrathfully', 'hatefully', 'grusomely', 'viciously', 'cruelly', 'zealously']
    DEFAULT_ADVERBS = ['respectfully', 'dutifully', 'sincierly', 'thoroughly', 'mysteriously']
    POSITIVE_VERBS = ['appraised', 'addressed', 'greeted', 'commended', 'praised', 'celebrated', 'congratulated']
    NEGATIVE_VERBS = ['unsucessful', 'disrespected', 'condemned', 'denounced', 'criticized', 'rejected', 'challenged', 'berated', 'deserted', 'injured', 'wounded', 'harmed', 'executed', 'exterminated', 'devoured', 'consumed']
    GIVE_VERBS = ['given', 'sent', 'transferred', 'delivered', 'donated', 'offered', 'lost', 'surrendered', 'forefeitted', 'sacrificed']
    TAKE_VERBS = ['received', 'recovered', 'gained', 'acquired', 'obtained', 'taken', 'claimed', 'captured', 'stolen', 'seized', 'confiscated']
    TEMPLATES=[]

    message = None
    game = None
    player = None
    intensity = 0.0
    category = 'GENERAL'
    priority = False  # Set True for significant events: failed orders, attacks, etc.

    def __init__(self, game, player, message=None, intensity=0.0):
        if not message:
            message = GameMessage()
        self.game = game
        self.player = player
        self.message = message
        self.intensity = intensity

    def get_message(self, intensity=None):
        if intensity is not None:
            self.intensity = intensity
        if self.message.message is None or self.message.message == "":
            self.message.message = self.format_message()
        return self.message

    def new_message(self, intensity=None):
        message = GameMessage()
        message.game = self.game
        message.player = self.player
        message.category = self.category
        message.priority = self.priority
        self.message = message
        return self.get_message(intensity=intensity)

    def _format_adverb(self):
        """select from the adverbs using a moving window based on intensity"""
        if self.intensity > 0.1:
            adverbs = list(chain(self.DEFAULT_ADVERBS, self.POSITIVE_ADVERBS))
        elif self.intensity < 0.1:
            adverbs = list(chain(self.DEFAULT_ADVERBS, self.NEGATIVE_ADVERBS))
        else:
            adverbs = self.DEFAULT_ADVERBS
        
        return weighted_random_choice(adverbs, self._get_abs_intensity(), 2)
    
    def _format_verb(self):
        """select from the verbs using a moving window based on intensity"""
        if self.intensity >= 0.0:
            verbs = list(self.POSITIVE_VERBS)
        elif self.intensity < 0.0:
            verbs = list(self.NEGATIVE_VERBS)
        
        return weighted_random_choice(verbs, self._get_abs_intensity(), 2)
    
    def _get_abs_intensity(self):
        return min(abs(self.intensity), 1.0)
    
    def format_message(self):
        return random.choice(self.templates).format(
            adverb=self._format_adverb(),
            verb=self._format_verb()
        )
    
    def format_outcome(self, item, quantity):
        verbs = self.TAKE_VERBS if quantity > 0 else self.GIVE_VERBS
        verb = weighted_random_choice(verbs, 1 - self.intensity * 0.5, 2)
        quantity = abs(quantity)
        return "We have {verb} {quantity} {item}. ".format(verb=verb, quantity=quantity, item=item)
    
    def append_outcome(self, item, quantity):
        self.message.message = " ".join([self.message.message, self.format_outcome(item, quantity)])


class DiplomaticMessageFactory(MessageFactory):
    category = 'DIPLOMATIC'
    templates = ["A representative of {race_formal} was recieved and {adverb} {verb}.",
                 "A representative was dispatched to {race_formal} and was {adverb} {verb}.",
                 "A delegation was received by {race_formal}. They were {adverb} {verb}.",
                 "A delegation was recieved from {race_formal}. They were {adverb} {verb}.",
                 "A party was sent to {race_formal}. They were {adverb} {verb}.",
                 "An envoy was dispatched to {race_formal}. They were {adverb} {verb}."
                 "An envoy was recieved from {race_formal}. They were {adverb} {verb}."]

    def __init__(self, game, player, encounter_player, message=None, intensity=0.0):
        super(DiplomaticMessageFactory, self).__init__(game, player, message, intensity)
        self.encounter_player = encounter_player

    def format_message(self):
        return random.choice(self.templates).format(race_formal=self.encounter_player.name,
                                                    adverb=self._format_adverb(),
                                                    verb=self._format_verb())


class EnvironmentalDeathMessageFactory(MessageFactory):
    """Messages for colonist deaths due to uninhabitable environmental conditions."""
    category = 'ENVIRONMENTAL'
    templates = [
        "{deaths:,} colonists perished on {star} due to harsh environmental conditions.",
        "{deaths:,} colonists on {star} succumbed to the hostile environment.",
        "Environmental hazards on {star} claimed the lives of {deaths:,} colonists.",
        "The inhospitable conditions on {star} proved fatal for {deaths:,} colonists.",
        "{deaths:,} settlers on {star} were lost to environmental exposure.",
    ]

    def __init__(self, game, player, star, deaths, message=None):
        super().__init__(game, player, message, intensity=-0.5)
        self.star = star
        self.deaths = deaths

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            deaths=self.deaths
        )


class OvercrowdingDeathMessageFactory(MessageFactory):
    """Messages for colonist deaths due to overcrowding/exceeding capacity."""
    category = 'POPULATION'
    templates = [
        "{deaths:,} colonists on {star} perished due to overcrowding.",
        "Overcrowding on {star} led to the deaths of {deaths:,} colonists.",
        "Resource shortages from overpopulation on {star} claimed {deaths:,} lives.",
        "{deaths:,} colonists on {star} died as the population exceeded sustainable limits.",
        "The colony on {star} lost {deaths:,} settlers to overcrowding.",
    ]

    def __init__(self, game, player, star, deaths, message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.star = star
        self.deaths = deaths

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            deaths=self.deaths
        )


class ColonyAbandonedMessageFactory(MessageFactory):
    """Messages for when a colony is completely depopulated."""
    category = 'POPULATION'
    priority = True
    templates = [
        "Your colony on {star} has been abandoned.",
        "The last colonists have departed {star}. The colony is no more.",
        "{star} colony has been lost. No survivors remain.",
        "All colonists on {star} have perished. The colony is abandoned.",
        "The colony on {star} has fallen silent. None remain.",
    ]

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=-0.8)
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(star=format_map_object(self.star))


class PlanetoidEventMessageFactory(MessageFactory):
    """Messages for rogue planetoid environmental effects."""
    category = 'RANDOM'
    templates = [
        "A rogue planetoid passed through the {star} system and {adverb} {verb} environmental conditions.",
        "Gravitational effects from an uncharted body {adverb} {verb} the environment on {star}.",
        "A comet's near-miss {adverb} {verb} atmospheric conditions on {star}.",
    ]
    POSITIVE_ADVERBS = ['slightly', 'mildly', 'noticeably', 'considerably', 'significantly']
    NEGATIVE_ADVERBS = ['slightly', 'mildly', 'severely', 'wildly', 'devastatingly']

    def __init__(self, game, player, star, message=None, intensity=0.0):
        super().__init__(game, player, message, intensity)
        self.star = star

    def _format_adverb(self):
        adverbs = self.POSITIVE_ADVERBS if self.intensity >= 0 else self.NEGATIVE_ADVERBS
        return weighted_random_choice(adverbs, self._get_abs_intensity(), 1)

    def _format_verb(self):
        if self.intensity >= 0:
            return random.choice(['improved', 'enhanced', 'stabilized', 'benefited'])
        else:
            return random.choice(['disrupted', 'destabilized', 'altered', 'degraded'])

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            adverb=self._format_adverb(),
            verb=self._format_verb()
        )


class PopulationBoomMessageFactory(MessageFactory):
    """Messages for population boom events."""
    category = 'RANDOM'
    templates = [
        "Unusual solar conditions on {star} coincided with a population surge of {qty:,} colonists.",
        "An unexplained birth rate spike on {star} produced {qty:,} additional colonists.",
        "Favourable cosmic radiation levels on {star} were linked to {qty:,} unexpected births.",
    ]

    def __init__(self, game, player, star, qty, message=None):
        super().__init__(game, player, message, intensity=0.4)
        self.star = star
        self.qty = qty

    def format_message(self):
        return random.choice(self.templates).format(star=format_map_object(self.star), qty=self.qty)


class MiningDiscoveryMessageFactory(MessageFactory):
    """Messages for surface resource discoveries."""
    category = 'RANDOM'
    templates = [
        "A meteor impact on {star} exposed {qty}kt of {resource}.",
        "Seismic activity on {star} revealed deposits of {qty}kt {resource}.",
        "Volcanic activity on {star} brought {qty}kt of {resource} to the surface.",
    ]

    def __init__(self, game, player, star, qty, resource, message=None):
        super().__init__(game, player, message, intensity=0.3)
        self.star = star
        self.qty = qty
        self.resource = resource

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            qty=self.qty,
            resource=self.resource
        )


class SecretResourceDiscoveryMessageFactory(MessageFactory):
    """Messages for secret resource discoveries."""
    category = 'RANDOM'
    priority = True
    adjectives = [
        'puzzling',
        'perplexing',
        'exciting',
        'unique',
        'disturbing',
    ]
    naming_phrases = [
        'our scientists have dubbed it',
        'called',
        'colonists have voted and named it',
    ]
    impact_phrases = [
        'It is believed this will',
        'This will almost certainly',
    ]

    def __init__(self, game, player, star, resource_name, fleet=None, message=None):
        super().__init__(game, player, message, intensity=0.6)
        self.star = star
        self.resource_name = resource_name
        self.fleet = fleet

    def format_message(self):
        subjects = []
        if self.fleet:
            subjects.append(f"{format_map_object(self.fleet)} has")
        subjects.extend(["We have", "Our scientists have"])
        subject = random.choice(subjects)
        adjective = random.choice(self.adjectives)
        naming = random.choice(self.naming_phrases)
        impact = random.choice(self.impact_phrases)
        return (
            f"{subject} discovered a {adjective} new element on {format_map_object(self.star)}, "
            f"{naming} '{self.resource_name}'. {impact} open up new avenues of research."
        )


class UnexplainedScanContactMessageFactory(MessageFactory):
    """Priority messages for remote scans that detect unknown phenomena."""
    category = 'RANDOM'
    priority = True

    def __init__(self, game, player, target=None, subject='', target_label=None, message=None):
        super().__init__(game, player, message, intensity=0.4)
        self.target = target
        self.subject = subject
        self.target_label = target_label

    def format_message(self):
        target_label = self.target_label or format_map_object_reference(self.target)
        return (
            "Long-range scans of %s have detected %s. "
            "Our scientists cannot explain it from afar; dispatch a fleet for closer study."
        ) % (
            target_label,
            self.subject,
        )


class ColonyVanishedMessageFactory(MessageFactory):
    """Messages for mysterious colony disappearance (extreme negative)."""
    category = 'RANDOM'
    priority = True
    templates = [
        "The colony on {star} went dark without warning and survey ships found all structures intact but empty.",
        "Contact with {star} was lost and rescue teams found the colony abandoned with no survivors or explanation.",
        "The population of {star} vanished after an anomalous energy signature was detected.",
    ]

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=-1.0)
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(star=format_map_object(self.star))


class MiningAccidentDeathsMessageFactory(MessageFactory):
    """Messages for mining accidents with colonist deaths."""
    category = 'RANDOM'
    templates = [
        "An industrial accident on {star} claimed {qty:,} lives.",
        "A seismic event on {star} caused a mine collapse that killed {qty:,} colonists.",
        "An equipment failure on {star} resulted in {qty:,} deaths.",
    ]

    def __init__(self, game, player, star, qty, message=None):
        super().__init__(game, player, message, intensity=-0.4)
        self.star = star
        self.qty = qty

    def format_message(self):
        return random.choice(self.templates).format(star=format_map_object(self.star), qty=self.qty)


class MiningAccidentResourcesMessageFactory(MessageFactory):
    """Messages for mining accidents with surface resource loss."""
    category = 'RANDOM'
    templates = [
        "A storage facility breach on {star} resulted in the loss of {qty}kt of {resource}.",
        "Volcanic activity on {star} destroyed {qty}kt of {resource} in storage.",
        "An equipment malfunction on {star} resulted in the loss of {qty}kt of {resource}.",
    ]

    def __init__(self, game, player, star, qty, resource, message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.star = star
        self.qty = qty
        self.resource = resource

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            qty=self.qty,
            resource=self.resource
        )


class FleetBuiltMessageFactory(MessageFactory):
    """Messages for fleet construction completion."""
    category = 'PRODUCTION'
    templates = [
        "Production of {fleet} completed at {star}.",
        "{fleet} has been commissioned at {star}.",
        "The shipyards at {star} have finished producing {fleet}.",
    ]

    def __init__(self, game, player, star, fleet, message=None):
        super().__init__(game, player, message, intensity=0.3)
        self.star = star
        self.fleet = fleet

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            fleet=format_map_object(self.fleet)
        )


class ProductionSummaryMessageFactory(MessageFactory):
    """Single rollup message for construction completed at one star in a year."""
    category = 'PRODUCTION'
    templates = [
        "Production update from {star}: completed {items}.",
        "Production report for {star}: {items} completed this year.",
        "{star} production report: {items} completed.",
    ]

    LABELS = {
        'mine': ('mine', 'mines'),
        'factory': ('factory', 'factories'),
        'lab': ('lab', 'labs'),
        'defense': ('defense', 'defenses'),
        'shipyard': ('shipyard', 'shipyards'),
        'city': ('city', 'cities'),
        'megacity': ('megacity', 'megacities'),
        'administration': ('Administration', 'Administrations'),
        'dyson_sphere': ('Dyson Sphere', 'Dyson Spheres'),
    }

    def __init__(self, game, player, star, production_counts, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.star = star
        self.production_counts = dict(production_counts or {})

    @staticmethod
    def _join_list(parts):
        if not parts:
            return ''
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return parts[0] + ' and ' + parts[1]
        return ', '.join(parts[:-1]) + ', and ' + parts[-1]

    def format_message(self):
        parts = []
        for key in [
            'mine', 'factory', 'lab', 'defense', 'shipyard',
            'city', 'megacity', 'administration', 'dyson_sphere'
        ]:
            count = int(self.production_counts.get(key) or 0)
            if count <= 0:
                continue
            singular, plural = self.LABELS.get(key, (key, key + 's'))
            label = singular if count == 1 else plural
            parts.append(f"{count} {label}")

        if not parts:
            return ""

        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            items=self._join_list(parts),
        )


class ProductionOrdersCompletedMessageFactory(MessageFactory):
    """Message when a colony has no remaining production orders."""
    category = 'PRODUCTION'
    templates = [
        "Production queue at {star} is now empty.",
        "{star} has completed all queued production orders.",
    ]

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=0.0)
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star)
        )


class ResearchLevelUnlockedMessageFactory(MessageFactory):
    """Message when a research category advances one or more levels."""
    category = 'GENERAL'
    templates = [
        "Research in {category} has advanced to level {level}.",
        "{category} research has reached level {level}.",
        "Our {category} programme has progressed to level {level}.",
    ]

    def __init__(self, game, player, category_name, level, message=None):
        super().__init__(game, player, message, intensity=0.3)
        self.category_name = category_name
        self.level = level

    def format_message(self):
        return random.choice(self.templates).format(
            category=self.category_name,
            level=self.level,
        )


class ResearchBreakthroughMessageFactory(MessageFactory):
    """Message for random research breakthroughs from lab colonies."""
    category = 'RANDOM'
    templates = [
        "Excavation of ancient ruins at {star} has contributed {rp} RP to our {category} research.",
        "Scientists at {star} recovered a buried device, advancing our {category} programme by {rp} RP.",
        "Anomalous findings at {star} have yielded {rp} RP for {category} research.",
    ]

    def __init__(self, game, player, star, category_name, rp, message=None):
        super().__init__(game, player, message, intensity=0.4)
        self.star = star
        self.category_name = category_name
        self.rp = rp

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            category=self.category_name,
            rp=self.rp,
        )


class FleetLostMessageFactory(MessageFactory):
    """Messages for fleets lost beyond map boundaries."""
    category = 'GENERAL'
    priority = True
    templates = [
        "{fleet} was lost in deep space.",
        "{fleet} has left the galaxy.",
        "{fleet} has moved beyond the bounds of the observable universe.",
        "{fleet} ventured into the void and was never seen again.",
        "Contact with {fleet} was lost as it crossed into uncharted space.",
    ]

    def __init__(self, game, player, fleet_name, message=None):
        super().__init__(game, player, message, intensity=-0.5)
        self.fleet_name = fleet_name

    def format_message(self):
        return random.choice(self.templates).format(fleet=self.fleet_name)


class FleetColonisedMessageFactory(MessageFactory):
    """Messages for successful fleet colonisation."""
    category = 'GENERAL'
    priority = True
    templates = [
        "{fleet} completed colonisation of {star}, depositing {cargo} on the surface.",
    ]

    def __init__(self, game, player, fleet_name, star, cargo_summary, message=None):
        super().__init__(game, player, message, intensity=0.5)
        self.fleet_name = fleet_name
        self.star = star
        self.cargo_summary = cargo_summary

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=self.fleet_name,
            star=format_map_object(self.star),
            cargo=self.cargo_summary,
        )


class ColoniseFailedAlreadyOwnedMessageFactory(MessageFactory):
    """Messages for colonisation attempts on already owned stars."""
    category = 'EXCEPTION'
    priority = True
    templates_same = [
        "{fleet} failed to colonise {star} because we already have a colony there.",
        "{fleet} could not colonise {star} - the world is already ours.",
        "{fleet} arrived at {star}, but we already maintain a colony there.",
    ]
    templates_other = [
        "{fleet} failed to colonise {star} because it is already colonized by {race}.",
        "{fleet} could not colonise {star} - it is owned by {race}.",
        "{fleet} arrived at {star} but found it already claimed by {race}.",
    ]

    def __init__(self, game, player, fleet, star, same_player=False, message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.fleet = fleet
        self.star = star
        self.same_player = same_player

    def format_message(self):
        if self.same_player:
            return random.choice(self.templates_same).format(
                fleet=format_map_object_reference(self.fleet),
                star=format_map_object(self.star)
            )
        return random.choice(self.templates_other).format(
            fleet=format_map_object_reference(self.fleet),
            star=format_map_object(self.star),
            race=self.star.player.name if self.star.player else "another race"
        )


class ColoniseFailedNoStarMessageFactory(MessageFactory):
    """Messages for failed colonisation attempts (no star at location)."""
    category = 'EXCEPTION'
    priority = True
    templates_with_star = [
        "{fleet} failed to colonise {star} - it was not found at {location}.",
        "Colonisation of {star} by {fleet} aborted - no planet at {location}.",
        "{fleet} arrived at {location} to colonise {star}, but found nothing.",
    ]
    templates_no_star = [
        "{fleet} aborted colonisation at {location} - no habitable world found.",
        "Colonisation order for {fleet} cancelled - no planet at {location}.",
        "{fleet} reached {location} but found no world to colonise.",
    ]

    def __init__(self, game, player, fleet, x, y, target_star=None, message=None):
        super().__init__(game, player, message, intensity=-0.2)
        self.fleet = fleet
        self.x = x
        self.y = y
        self.target_star = target_star

    def format_message(self):
        location = format_location(x=self.x, y=self.y, link=True, game=self.game)
        if self.target_star:
            return random.choice(self.templates_with_star).format(
                fleet=format_map_object_reference(self.fleet),
                star=format_map_object(self.target_star),
                location=location
            )
        else:
            return random.choice(self.templates_no_star).format(
                fleet=format_map_object_reference(self.fleet),
                location=location
            )


class BombardFailedNoStarMessageFactory(MessageFactory):
    """Messages for failed bombardment attempts (no star at location)."""
    category = 'EXCEPTION'
    priority = True
    templates = [
        "{fleet} aborted bombardment at {location} - no star was found.",
        "Bombardment order for {fleet} failed: no target star at {location}.",
        "{fleet} reached {location}, but there was no star to bombard.",
    ]

    def __init__(self, game, player, fleet, x, y, message=None):
        super().__init__(game, player, message, intensity=-0.2)
        self.fleet = fleet
        self.x = x
        self.y = y

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object_reference(self.fleet),
            location=format_location(x=self.x, y=self.y, link=True, game=self.game),
        )


class FleetBombardmentReportMessageFactory(MessageFactory):
    """Messages summarizing one year of bombardment effects."""
    category = 'COMBAT'
    priority = True

    def __init__(
        self, game, player, fleet, star_name, bomb_type,
        defenses_lost, colonists_lost, mines_lost, factories_lost, labs_lost,
        shipyards_lost, cities_lost=0, megacities_lost=0,
        administration_lost=0, dyson_sphere_lost=0,
        annihilated_colonists=0,
        integrity_lost=0, ships_lost=0, star_destroyed=False,
        perspective='attacker', attacker_fleet_name=None, star=None,
        extra_effects_text='', message=None
    ):
        super().__init__(game, player, message, intensity=-0.5)
        self.fleet = fleet
        self.star_name = star_name or "unknown star"
        self.bomb_type = bomb_type or "CONVENTIONAL"
        self.defenses_lost = int(defenses_lost or 0)
        self.colonists_lost = int(colonists_lost or 0)
        self.mines_lost = int(mines_lost or 0)
        self.factories_lost = int(factories_lost or 0)
        self.labs_lost = int(labs_lost or 0)
        self.shipyards_lost = int(shipyards_lost or 0)
        self.cities_lost = int(cities_lost or 0)
        self.megacities_lost = int(megacities_lost or 0)
        self.administration_lost = int(administration_lost or 0)
        self.dyson_sphere_lost = int(dyson_sphere_lost or 0)
        self.annihilated_colonists = int(annihilated_colonists or 0)
        self.integrity_lost = int(integrity_lost or 0)
        self.ships_lost = int(ships_lost or 0)
        self.star_destroyed = bool(star_destroyed)
        self.perspective = perspective
        self.attacker_fleet_name = attacker_fleet_name or getattr(fleet, 'name', 'Unknown Fleet')
        self.star = star
        self.extra_effects_text = str(extra_effects_text or '')

    def format_message(self):
        infra = []
        if self.mines_lost > 0:
            infra.append(f"{self.mines_lost} mines")
        if self.factories_lost > 0:
            infra.append(f"{self.factories_lost} factories")
        if self.labs_lost > 0:
            infra.append(f"{self.labs_lost} labs")
        if self.shipyards_lost > 0:
            infra.append(f"{self.shipyards_lost} shipyards")
        if self.cities_lost > 0:
            infra.append(f"{self.cities_lost} cities")
        if self.megacities_lost > 0:
            infra.append(f"{self.megacities_lost} megacities")
        if self.administration_lost > 0:
            infra.append("Administration")
        if self.dyson_sphere_lost > 0:
            infra.append("Dyson Sphere")
        infra_text = ", ".join(infra) if infra else "no infrastructure"

        star_label = (
            format_map_object(self.star)
            if self.star is not None and not self.star_destroyed
            else escape(self.star_name)
        )
        if self.star_destroyed:
            if self.perspective == 'defender':
                msg = (
                    f"{escape(self.attacker_fleet_name)} bombarded {star_label} "
                    f"({escape(self.bomb_type.title())} bombs): "
                    f"{escape(self.star_name)} was annihilated."
                )
            else:
                msg = (
                    f"{format_map_object(self.fleet)} bombarded {star_label} "
                    f"({escape(self.bomb_type.title())} bombs): "
                    f"{escape(self.star_name)} was annihilated."
                )
            if self.annihilated_colonists > 0:
                msg += f" {self.annihilated_colonists:,} colonists were killed."
        elif self.perspective == 'defender':
            msg = (
                f"{escape(self.attacker_fleet_name)} bombarded {star_label} "
                f"({escape(self.bomb_type.title())} bombs): "
                f"we lost {self.defenses_lost} defenses, "
                f"{self.colonists_lost:,} colonists, and {infra_text}."
            )
        else:
            msg = (
                f"{format_map_object(self.fleet)} bombarded {star_label} "
                f"({escape(self.bomb_type.title())} bombs): "
                f"{self.defenses_lost} defenses destroyed, "
                f"{self.colonists_lost:,} colonists killed, "
                f"{infra_text} damaged."
            )

        if self.integrity_lost > 0 or self.ships_lost > 0:
            if self.perspective == 'defender':
                msg += (
                    f" Defensive fire inflicted {self.integrity_lost}% integrity loss"
                    f" and {self.ships_lost} ships lost on the attacker."
                )
            else:
                msg += (
                    f" Defensive fire inflicted {self.integrity_lost}% integrity loss"
                    f" and {self.ships_lost} ships lost."
                )
        if self.extra_effects_text:
            msg += f" {escape(self.extra_effects_text)}"
        return msg


class StarVanishedOminousMessageFactory(MessageFactory):
    """Public warning message for star disappearance."""
    category = 'RANDOM'
    priority = False

    def __init__(self, game, player, star_name, x, y, fleet_name=None, priority=False, message=None):
        super().__init__(game, player, message, intensity=-0.9)
        self.star_name = star_name or "Unknown Star"
        self.x = x
        self.y = y
        self.fleet_name = fleet_name
        self.priority = bool(priority)

    def format_message(self):
        location = format_location(x=self.x, y=self.y, link=True, game=self.game)
        if self.fleet_name:
            return (
                f"Our astronomers report that {escape(self.star_name)} can no longer "
                f"be found in the night sky. It was previously located at {location}. "
                f"{escape(self.fleet_name)} was recently seen in the vicinity."
            )
        return (
            f"Astronomers report that {escape(self.star_name)} has mysteriously "
            f"vanished into {location}."
        )


class GenesisStarBornPublicMessageFactory(MessageFactory):
    """Public message for a newly created star."""
    category = 'RANDOM'
    priority = False

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=0.8)
        self.star = star

    def format_message(self):
        return (
            f"A brilliant new star has appeared in the night sky: "
            f"{format_map_object(self.star)}."
        )


class GenesisActivationSuccessMessageFactory(MessageFactory):
    """Owner-only success message for Genesis Device activation."""
    category = 'RANDOM'
    priority = True

    def __init__(
        self,
        game,
        player,
        fleet_name,
        star,
        destroyed_fleet_count,
        consumed_resources,
        message=None,
    ):
        super().__init__(game, player, message, intensity=1.0)
        self.fleet_name = fleet_name
        self.star = star
        self.destroyed_fleet_count = destroyed_fleet_count
        self.consumed_resources = consumed_resources or {}

    def _resource_summary(self):
        labels = {
            'ironium': 'Ironium',
            'boranium': 'Boranium',
            'germanium': 'Germanium',
            'resource_x': 'Uniquium',
            'resource_y': 'Rarium',
            'resource_z': 'Mysterium',
        }
        parts = []
        for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z'):
            amount = int(self.consumed_resources.get(key, 0) or 0)
            if amount > 0:
                parts.append(f"{amount}kt {labels[key]}")
        if not parts:
            return 'no local resources'
        if len(parts) == 1:
            return parts[0]
        return ', '.join(parts[:-1]) + ', and ' + parts[-1]

    def format_message(self):
        extra_fleets = max(0, int(self.destroyed_fleet_count or 0) - 1)
        fleet_text = (
            f"{self.fleet_name} activated its Genesis Device"
            if self.fleet_name else
            "A fleet activated its Genesis Device"
        )
        if extra_fleets > 0:
            fleet_text += f", consuming {extra_fleets} other fleet"
            if extra_fleets != 1:
                fleet_text += 's'
        return (
            f"{fleet_text} and created {format_map_object(self.star)}. "
            f"Consumed resources: {self._resource_summary()}."
        )


class GenesisFleetConsumedMessageFactory(MessageFactory):
    """Message for fleets lost to a Genesis activation by another fleet."""
    category = 'EXCEPTION'
    priority = True

    def __init__(self, game, player, fleet, star, message=None):
        super().__init__(game, player, message, intensity=-0.8)
        self.fleet = fleet
        self.star = star

    def format_message(self):
        return (
            f"{format_map_object_reference(self.fleet)} was consumed in a Genesis activation "
            f"that created {format_map_object(self.star)}."
        )


class GenesisActivationFailedMessageFactory(MessageFactory):
    """Owner-only message for a Genesis activation lost to anomaly interference."""
    category = 'EXCEPTION'
    priority = True

    def __init__(self, game, player, fleet_name, anomaly, message=None):
        super().__init__(game, player, message, intensity=-1.0)
        self.fleet_name = fleet_name
        self.anomaly = anomaly

    def format_message(self):
        return (
            f"{escape(self.fleet_name or 'A fleet')} attempted to activate a Genesis Device at "
            f"{format_map_object_reference(self.anomaly)}, but the anomaly destabilised the process. "
            f"The fleet was lost."
        )


class AnomalyTargetLostMessageFactory(MessageFactory):
    """Messages for fleets whose anomaly target vanished before arrival."""
    category = 'EXCEPTION'
    priority = True
    anomaly_fates = [
        ('evaporated', 'into'),
        ('vanished', 'at'),
        ('collapsed', 'at'),
        ('disappeared', 'at'),
    ]
    wormhole_fates = [
        ('collapsed', 'into'),
        ('evaporated', 'into'),
        ('dissipated', 'into'),
    ]

    def __init__(self, game, player, fleet, anomaly_name, anomaly_type, x, y, message=None):
        super().__init__(game, player, message, intensity=-0.5)
        self.fleet = fleet
        self.anomaly_name = anomaly_name or 'Unknown Anomaly'
        self.anomaly_type = anomaly_type or 'ANOMALY'
        self.x = x
        self.y = y

    def format_message(self):
        fleet_label = format_map_object(self.fleet)
        anomaly_label = escape(self.anomaly_name)
        location = format_space_link(self.game, self.x, self.y)
        if str(self.anomaly_type).upper() == 'WORMHOLE':
            fate, prep = random.choice(self.wormhole_fates)
            return (
                f"{fleet_label} has orders to enter {anomaly_label}, but it has "
                f"{fate} {prep} {location}."
            )
        if random.random() < 0.5:
            action = random.choice(['visit', 'investigate'])
            fate, prep = random.choice(self.anomaly_fates)
            return (
                f"{fleet_label} has orders to {action} {anomaly_label}, but it has "
                f"{fate} {prep} {location}."
            )
        return (
            f"{fleet_label} has orders to investigate {anomaly_label}, but it can no "
            f"longer be found at {location}."
        )


class ColoniseFailedNoColonistsMessageFactory(MessageFactory):
    """Messages for failed colonisation attempts (no colonists aboard)."""
    category = 'EXCEPTION'
    priority = True
    templates = [
        "{fleet} cannot colonise {star} - no colonists aboard.",
        "Colonisation of {star} by {fleet} aborted - the fleet carries no colonists.",
        "{fleet} arrived at {star} but has no colonists to establish a colony.",
    ]

    def __init__(self, game, player, fleet, star, message=None):
        super().__init__(game, player, message, intensity=-0.2)
        self.fleet = fleet
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object_reference(self.fleet),
            star=format_map_object(self.star)
        )


class ColonistsLostInSpaceMessageFactory(MessageFactory):
    """Messages for colonists lost when transferred to empty space."""
    category = 'EXCEPTION'
    priority = True
    templates = [
        "{fleet} vented {colonists}k colonists into {location}. No survivors.",
        "{colonists}k colonists from {fleet} were lost in the vacuum of {location}.",
        "{fleet} released {colonists}k colonists into {location}. They did not survive.",
    ]

    def __init__(self, game, player, fleet, colonists_kt, x, y, message=None):
        super().__init__(game, player, message, intensity=-0.6)
        self.fleet = fleet
        self.colonists_kt = colonists_kt
        self.x = x
        self.y = y

    def format_message(self):
        fleet_display = format_map_object(self.fleet)
        return random.choice(self.templates).format(
            fleet=fleet_display,
            colonists=self.colonists_kt,
            location=format_location(x=self.x, y=self.y, link=True, game=self.game)
        )


class ColonistsFailedToColoniseMessageFactory(MessageFactory):
    """Messages for colonists transferred to an unowned star failing to colonise."""
    category = 'EXCEPTION'
    priority = True
    templates = [
        "{colonists}k colonists from {fleet} perished on {star}. The colony did not survive.",
        "{fleet} delivered {colonists}k colonists to {star}, but the settlement failed.",
        "{colonists}k colonists sent to {star} from {fleet} could not sustain a colony.",
    ]

    def __init__(self, game, player, fleet, colonists_kt, star, message=None):
        super().__init__(game, player, message, intensity=-0.6)
        self.fleet = fleet
        self.colonists_kt = colonists_kt
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object_reference(self.fleet),
            colonists=self.colonists_kt,
            star=format_map_object(self.star)
        )


class ColonistsUnexpectedColonyMessageFactory(MessageFactory):
    """Messages for unexpected colonisation via transfer."""
    category = 'GENERAL'
    priority = True
    templates = [
        "{fleet} unexpectedly established a colony at {star} with {colonists}k colonists.",
        "Against the odds, {colonists}k colonists from {fleet} founded a colony at {star}.",
    ]

    def __init__(self, game, player, fleet, colonists_kt, star, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.fleet = fleet
        self.colonists_kt = colonists_kt
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object_reference(self.fleet),
            colonists=self.colonists_kt,
            star=format_map_object(self.star)
        )


class MineralGiftMessageFactory(MessageFactory):
    """Messages for minerals gifted to another player's star."""
    category = 'DIPLOMATIC'
    priority = True
    templates = [
        "{fleet} deposited minerals on {star}: {cargo}.",
        "Foreign fleet {fleet} delivered minerals to {star}: {cargo}.",
        "{fleet} left a mineral shipment on {star}: {cargo}.",
    ]

    def __init__(self, game, player, fleet, star, transfers, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.fleet = fleet
        self.star = star
        self.transfers = transfers or {}

    def _format_cargo(self):
        parts = []
        for key, amount in self.transfers.items():
            if amount > 0:
                parts.append(f"{amount}kt {format_resource_name(key)}")
        return ", ".join(parts) if parts else "no minerals"

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object_reference(self.fleet),
            star=format_map_object(self.star),
            cargo=self._format_cargo()
        )


class InvasionReportMessageFactory(MessageFactory):
    """Messages for invasions (attacker/defender)."""
    category = 'EXCEPTION'
    priority = True
    templates_attacker_win = [
        "Invasion success at {star}. We lost {attacker_losses} colonists and {fleet_losses}. Remaining forces secured the colony.",
        "Our invasion of {star} succeeded. {attacker_losses} colonists and {fleet_losses} lost.",
    ]
    templates_attacker_fail = [
        "Invasion failed at {star}. We lost {attacker_losses} colonists and {fleet_losses}.",
        "Our invasion of {star} was repelled. {attacker_losses} colonists and {fleet_losses} lost.",
    ]
    templates_defender_win = [
        "Invasion at {star} repelled. We lost {defender_losses} colonists.",
        "Our forces held {star}. Defender losses: {defender_losses} colonists.",
    ]
    templates_defender_fail = [
        "Invasion at {star} succeeded. We lost {defender_losses} colonists and the colony was captured.",
        "{star} has fallen after an invasion. Defender losses: {defender_losses} colonists.",
    ]

    def __init__(self, game, player, star, attacker_won, attacker_losses, defender_losses,
                 fleet_losses_desc, perspective='attacker', message=None):
        super().__init__(game, player, message, intensity=-0.6)
        self.star = star
        self.attacker_won = attacker_won
        self.attacker_losses = attacker_losses
        self.defender_losses = defender_losses
        self.fleet_losses_desc = fleet_losses_desc
        self.perspective = perspective

    def format_message(self):
        if self.perspective == 'attacker':
            templates = self.templates_attacker_win if self.attacker_won else self.templates_attacker_fail
            return random.choice(templates).format(
                star=format_map_object(self.star),
                attacker_losses=f"{self.attacker_losses:,}",
                fleet_losses=self.fleet_losses_desc
            )
        templates = self.templates_defender_fail if self.attacker_won else self.templates_defender_win
        return random.choice(templates).format(
            star=format_map_object(self.star),
            defender_losses=f"{self.defender_losses:,}"
        )

class FleetWarpDamageMessageFactory(MessageFactory):
    """Messages for fleet damage from exceeding safe warp speed."""
    category = 'GENERAL'
    priority = True
    templates_damage_only = [
        "{fleet} sustained {integrity_loss}% structural damage travelling at warp {warp}.",
        "Warp {warp} proved too fast for {fleet} - {integrity_loss}% integrity lost.",
        "{fleet} pushed beyond safe limits at warp {warp}, losing {integrity_loss}% integrity.",
    ]
    templates_cargo_loss = [
        "{fleet} sustained {integrity_loss}% damage at warp {warp}. {cargo_desc} was lost.",
        "At warp {warp}, {fleet} lost {integrity_loss}% integrity and {cargo_desc}.",
        "{fleet} suffered structural failure at warp {warp}: {integrity_loss}% damage, {cargo_desc} jettisoned.",
    ]
    templates_colonist_loss = [
        "{fleet} sustained {integrity_loss}% damage at warp {warp}. {colonist_deaths:,}k colonists perished.",
        "Disaster aboard {fleet} at warp {warp}: {integrity_loss}% damage, {colonist_deaths:,}k lives lost.",
        "{fleet} pushed to warp {warp} with tragic results: {integrity_loss}% damage, {colonist_deaths:,}k dead.",
    ]
    templates_cargo_and_colonist = [
        "{fleet} at warp {warp}: {integrity_loss}% damage, {cargo_desc} lost, {colonist_deaths:,}k dead.",
        "Catastrophe aboard {fleet} at warp {warp}: {integrity_loss}% structural damage, {cargo_desc} lost, {colonist_deaths:,}k colonists killed.",
    ]

    def __init__(self, game, player, fleet, warp_speed, integrity_loss,
                 cargo_losses=None, colonist_deaths=0, message=None):
        super().__init__(game, player, message, intensity=-0.4)
        self.fleet = fleet
        self.warp_speed = warp_speed
        self.integrity_loss = integrity_loss
        self.cargo_losses = cargo_losses or {}
        self.colonist_deaths = colonist_deaths

    def _format_cargo_desc(self):
        parts = []
        for resource, amount in self.cargo_losses.items():
            if amount > 0:
                parts.append(f"{amount}kt {format_resource_name(resource)}")
        return ", ".join(parts) if parts else "cargo"

    def format_message(self):
        has_cargo = any(v > 0 for v in self.cargo_losses.values())
        has_deaths = self.colonist_deaths > 0

        if has_cargo and has_deaths:
            templates = self.templates_cargo_and_colonist
        elif has_deaths:
            templates = self.templates_colonist_loss
        elif has_cargo:
            templates = self.templates_cargo_loss
        else:
            templates = self.templates_damage_only

        return random.choice(templates).format(
            fleet=format_map_object(self.fleet),
            warp=self.warp_speed,
            integrity_loss=self.integrity_loss,
            cargo_desc=self._format_cargo_desc(),
            colonist_deaths=self.colonist_deaths
        )


class FleetBussardRecoveryMessageFactory(MessageFactory):
    """Message when a fleet scavenges emergency fuel and continues moving."""
    category = 'EXCEPTION'
    templates = [
        "{fleet} gathered {fuel_gain}mg with Bussard collectors and continued at warp {warp} (ordered warp {requested_warp}).",
        "Low fuel emergency on {fleet}: Bussard collectors recovered {fuel_gain}mg, allowing warp {warp} movement (ordered warp {requested_warp}).",
        "{fleet} lacked fuel at ordered warp {requested_warp}, but scavenged {fuel_gain}mg and proceeded at warp {warp}.",
    ]

    def __init__(self, game, player, fleet, fuel_gain, warp, requested_warp, message=None):
        super().__init__(game, player, message, intensity=0.1)
        self.fleet = fleet
        self.fuel_gain = int(fuel_gain)
        self.warp = int(warp)
        self.requested_warp = int(requested_warp)

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object(self.fleet),
            fuel_gain=self.fuel_gain,
            warp=self.warp,
            requested_warp=self.requested_warp,
        )


class FleetWormholeFuelFailureMessageFactory(MessageFactory):
    """Message when a fleet cannot engage wormhole drive due to fuel shortage."""
    category = 'EXCEPTION'
    templates = [
        "{fleet} failed to engage wormhole drive due to insufficient fuel ({fuel:.1f}mg available, {required_fuel:.1f}mg required).",
        "Wormhole jump aborted for {fleet}: insufficient fuel ({fuel:.1f}mg available, {required_fuel:.1f}mg required).",
        "{fleet} could not start wormhole transit; fuel stores were too low ({fuel:.1f}mg available, {required_fuel:.1f}mg required).",
    ]

    def __init__(self, game, player, fleet, fuel, required_fuel, message=None):
        super().__init__(game, player, message, intensity=0.1)
        self.fleet = fleet
        self.fuel = float(fuel or 0.0)
        self.required_fuel = float(required_fuel or 0.0)

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object(self.fleet),
            fuel=self.fuel,
            required_fuel=self.required_fuel,
        )


class FleetWormholeJumpSuccessMessageFactory(MessageFactory):
    """Message when a fleet successfully completes a wormhole jump."""
    category = 'GENERAL'

    def __init__(self, game, player, fleet, destination_x, destination_y, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.fleet = fleet
        self.destination_x = int(destination_x)
        self.destination_y = int(destination_y)

    def format_message(self):
        return (
            "{fleet} successfully completed a wormhole jump to {location}."
        ).format(
            fleet=format_map_object(self.fleet),
            location=format_location(
                x=self.destination_x,
                y=self.destination_y,
                link=True,
                game=self.game,
            ),
        )


class FleetWarpDestroyedMessageFactory(MessageFactory):
    """Messages for fleets destroyed by exceeding safe warp speed."""
    category = 'GENERAL'
    priority = True
    templates_instant = [
        "{fleet} was torn apart at warp {warp} {location}. All hands lost.",
        "{fleet} disintegrated travelling at warp {warp} {location}.",
        "Catastrophic structural failure destroyed {fleet} at warp {warp} {location}.",
        "{fleet} exceeded its limits at warp {warp} {location} and was lost with all hands.",
    ]
    templates_accumulated = [
        "{fleet} broke apart after accumulated damage at warp {warp} {location}.",
        "Structural failures cascaded through {fleet} at warp {warp} {location}. The fleet is lost.",
        "{fleet} could not withstand further stress at warp {warp} {location} and was destroyed.",
    ]
    salvage_suffix_star = " Salvage deposited on {star}."
    salvage_suffix_space = " Salvage left at {location}."

    def __init__(self, game, player, fleet_name, warp_speed, x, y,
                 from_damage=False, salvage_created=False, salvage_location=None,
                 message=None):
        super().__init__(game, player, message, intensity=-0.8)
        self.fleet_name = fleet_name
        self.warp_speed = warp_speed
        self.x = x
        self.y = y
        self.from_damage = from_damage
        self.salvage_created = salvage_created
        self.salvage_location = salvage_location

    def _format_location(self):
        """Format the location as a star link or empty space coordinates."""
        from .models import Star
        star = Star.objects.filter(game=self.game, x=self.x, y=self.y).first()
        if star:
            return f"near {format_map_object(star)}"
        return f"in {format_location(x=self.x, y=self.y, link=True, game=self.game)}"

    def format_message(self):
        from .models import Star
        templates = self.templates_accumulated if self.from_damage else self.templates_instant
        msg = random.choice(templates).format(
            fleet=self.fleet_name,
            warp=self.warp_speed,
            location=self._format_location()
        )

        # Append salvage info if created
        if self.salvage_created and self.salvage_location:
            if isinstance(self.salvage_location, Star):
                msg += self.salvage_suffix_star.format(
                    star=format_map_object(self.salvage_location)
                )
            else:
                msg += self.salvage_suffix_space.format(
                    location=format_salvage(self.x, self.y)
                )

        return msg


class FleetWormholeDestroyedMessageFactory(MessageFactory):
    """Messages for fleets lost to wormhole instability."""
    category = 'GENERAL'
    priority = True
    templates_instant = [
        "{fleet} was lost to wormhole instability {location}.",
        "{fleet} failed to re-emerge from wormhole transit {location}.",
        "{fleet} vanished during wormhole transit {location}.",
    ]
    templates_accumulated = [
        "{fleet} broke apart under wormhole transit stresses {location}.",
        "{fleet} suffered cascading hull failures in wormhole transit {location} and was lost.",
        "{fleet} was destroyed by wormhole instability after prior structural damage {location}.",
    ]
    salvage_suffix_star = " Salvage deposited on {star}."
    salvage_suffix_space = " Salvage left at {location}."

    def __init__(self, game, player, fleet_name, x, y,
                 from_damage=False, salvage_created=False, salvage_location=None,
                 message=None):
        super().__init__(game, player, message, intensity=-0.8)
        self.fleet_name = fleet_name
        self.x = x
        self.y = y
        self.from_damage = from_damage
        self.salvage_created = salvage_created
        self.salvage_location = salvage_location

    def _format_location(self):
        """Format the location as a star link or empty space coordinates."""
        from .models import Star
        star = Star.objects.filter(game=self.game, x=self.x, y=self.y).first()
        if star:
            return f"near {format_map_object(star)}"
        return f"in {format_location(x=self.x, y=self.y, link=True, game=self.game)}"

    def format_message(self):
        from .models import Star
        templates = self.templates_accumulated if self.from_damage else self.templates_instant
        msg = random.choice(templates).format(
            fleet=self.fleet_name,
            location=self._format_location()
        )

        if self.salvage_created and self.salvage_location:
            if isinstance(self.salvage_location, Star):
                msg += self.salvage_suffix_star.format(
                    star=format_map_object(self.salvage_location)
                )
            else:
                msg += self.salvage_suffix_space.format(
                    location=format_salvage(self.x, self.y)
                )

        return msg


class FleetMergedMessageFactory(MessageFactory):
    """Messages for fleet merge completion."""
    category = 'GENERAL'
    templates = [
        "{source} has merged with {target}. Combined fleet now has {ships} ships.",
        "{source} merged into {target}, forming a fleet of {ships} ships.",
        "Fleet merger complete: {source} joined {target} ({ships} ships total).",
    ]

    def __init__(self, game, player, source_name, target_fleet, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.source_name = source_name
        self.target_fleet = target_fleet

    def format_message(self):
        return random.choice(self.templates).format(
            source=self.source_name,
            target=format_map_object(self.target_fleet),
            ships=self.target_fleet.ship_count
        )


class FleetTransferredMessageFactory(MessageFactory):
    """Messages for fleet ownership transfers initiated by the current owner."""
    category = 'GENERAL'
    priority = True
    templates_to_player = [
        "{fleet} was transferred to {recipient}.",
        "Transfer complete: {fleet} now belongs to {recipient}.",
        "{fleet} was handed over to {recipient}.",
    ]
    templates_abandoned = [
        "{fleet} was abandoned and left adrift.",
        "{fleet} was set adrift and is now abandoned.",
        "Abandonment complete: {fleet} is now an unowned derelict.",
    ]

    def __init__(self, game, player, fleet, recipient_name=None, message=None):
        super().__init__(game, player, message, intensity=0.0)
        self.fleet = fleet
        self.recipient_name = recipient_name

    def format_message(self):
        if self.recipient_name:
            return random.choice(self.templates_to_player).format(
                fleet=format_map_object_reference(self.fleet),
                recipient=self.recipient_name,
            )
        return random.choice(self.templates_abandoned).format(
            fleet=format_map_object_reference(self.fleet),
        )


class FleetReceivedMessageFactory(MessageFactory):
    """Messages for players receiving a transferred fleet."""
    category = 'GENERAL'
    priority = True
    templates = [
        "{fleet} was transferred to us by {sender}.",
        "We received {fleet} from {sender}.",
        "{sender} transferred control of {fleet} to us.",
    ]

    def __init__(self, game, player, fleet, sender_name, message=None):
        super().__init__(game, player, message, intensity=0.0)
        self.fleet = fleet
        self.sender_name = sender_name

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object_reference(self.fleet),
            sender=self.sender_name,
        )


class FleetRefueledMessageFactory(MessageFactory):
    """Messages for cross-player fuel transfers."""
    category = 'GENERAL'
    priority = True
    templates = [
        "{target_fleet} was given {fuel_amount}mg fuel by {source_fleet}.",
    ]

    def __init__(self, game, player, target_fleet, source_fleet, fuel_amount, message=None):
        super().__init__(game, player, message, intensity=0.1)
        self.target_fleet = target_fleet
        self.source_fleet = source_fleet
        self.fuel_amount = fuel_amount

    @staticmethod
    def _format_fuel_amount(amount):
        try:
            value = float(amount or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        rounded = round(value, 3)
        if int(rounded) == rounded:
            return str(int(rounded))
        return ('%.3f' % rounded).rstrip('0').rstrip('.')

    def format_message(self):
        return random.choice(self.templates).format(
            target_fleet=format_map_object_reference(self.target_fleet),
            fuel_amount=self._format_fuel_amount(self.fuel_amount),
            source_fleet=format_map_object_reference(self.source_fleet),
        )


class ColonyTransferredMessageFactory(MessageFactory):
    """Messages for colony ownership transfers initiated by the current owner."""
    category = 'GENERAL'
    priority = True
    templates = [
        "{star} was transferred to {recipient}.",
        "Transfer complete: {star} now belongs to {recipient}.",
        "{star} was handed over to {recipient}.",
    ]

    def __init__(self, game, player, star, recipient_name, message=None):
        super().__init__(game, player, message, intensity=0.0)
        self.star = star
        self.recipient_name = recipient_name

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            recipient=self.recipient_name,
        )


class ColonyReceivedMessageFactory(MessageFactory):
    """Messages for players receiving a colony transfer."""
    category = 'GENERAL'
    priority = True
    templates = [
        "{star} was transferred to us by {sender}.",
        "We received control of {star} from {sender}.",
        "{sender} transferred ownership of {star} to us.",
    ]

    def __init__(self, game, player, star, sender_name, message=None):
        super().__init__(game, player, message, intensity=0.0)
        self.star = star
        self.sender_name = sender_name

    def format_message(self):
        return random.choice(self.templates).format(
            star=format_map_object(self.star),
            sender=self.sender_name,
        )


class FleetOrdersCompletedMessageFactory(MessageFactory):
    """Message when a fleet has no remaining assigned orders."""
    category = 'GENERAL'
    templates = [
        "{fleet} has completed its assigned orders. No further orders are queued.",
    ]

    def __init__(self, game, player, fleet, message=None):
        super().__init__(game, player, message, intensity=0.0)
        self.fleet = fleet

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object(self.fleet)
        )


class FleetScuttledMessageFactory(MessageFactory):
    """Messages for fleet scuttling."""
    category = 'GENERAL'
    priority = False
    templates_no_salvage = [
        "{fleet} was scuttled {location}. No recoverable materials.",
        "{fleet} scuttled {location}. The wreckage was lost.",
        "Scuttling of {fleet} {location} complete. Nothing salvageable remained.",
    ]
    templates_salvage_star = [
        "{fleet} was scuttled at {location}. Salvage deposited on surface.",
        "{fleet} scuttled at {location}. Materials recovered to the surface.",
        "Scuttling of {fleet} at {location} complete. Salvage deposited planetside.",
    ]
    templates_salvage_space = [
        "{fleet} was scuttled {location}. Salvage left in orbit.",
        "{fleet} scuttled {location}. Debris field remains.",
        "Scuttling of {fleet} {location} complete. Salvage awaits collection.",
    ]

    def __init__(self, game, player, fleet_name, x, y,
                 salvage_created=False, salvage_location=None, message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.fleet_name = fleet_name
        self.x = x
        self.y = y
        self.salvage_created = salvage_created
        self.salvage_location = salvage_location

    def _format_location(self):
        """Format the location as a star link or empty space coordinates."""
        from .models import Star
        star = Star.objects.filter(game=self.game, x=self.x, y=self.y).first()
        if star:
            return format_map_object(star)
        return f"in {format_location(x=self.x, y=self.y, link=True, game=self.game)}"

    def format_message(self):
        from .models import Star
        if not self.salvage_created:
            templates = self.templates_no_salvage
            return random.choice(templates).format(
                fleet=self.fleet_name,
                location=self._format_location()
            )
        elif isinstance(self.salvage_location, Star):
            templates = self.templates_salvage_star
            return random.choice(templates).format(
                fleet=self.fleet_name,
                location=format_map_object(self.salvage_location)
            )
        else:
            templates = self.templates_salvage_space
            return random.choice(templates).format(
                fleet=self.fleet_name,
                location=self._format_location()
            )


class CombatMessageFactory(MessageFactory):
    """Messages for combat resolution."""
    category = 'COMBAT'
    priority = True
    templates = [
        "Engagement at {location}{opponents} concluded with a {winner} victory.",
        "Combat at {location}{opponents} ended in a {winner} victory.",
        "Battle report from {location}{opponents}: {winner} prevailed.",
    ]

    def __init__(self, game, player, winner, location,
                 fleets_destroyed=0, ships_lost=0, integrity_lost=0,
                 opponents=None,
                 enemy_fleets_destroyed=0, enemy_ships_lost=0, enemy_integrity_lost=0,
                 salvage_created=False, message=None):
        super().__init__(game, player, message, intensity=-0.2)
        self.winner = winner
        self.location = location
        self.fleets_destroyed = fleets_destroyed
        self.ships_lost = ships_lost
        self.integrity_lost = integrity_lost
        self.opponents = list(opponents or [])
        self.enemy_fleets_destroyed = enemy_fleets_destroyed
        self.enemy_ships_lost = enemy_ships_lost
        self.enemy_integrity_lost = enemy_integrity_lost
        self.salvage_created = salvage_created

    def _format_location(self):
        if isinstance(self.location, tuple):
            x, y = self.location
            return format_location(x=x, y=y, link=True, game=self.game)
        return format_map_object(self.location)

    def _format_losses(self):
        parts = []
        if self.fleets_destroyed:
            parts.append(f"{self.fleets_destroyed} fleet(s) destroyed")
        if self.ships_lost:
            parts.append(f"{self.ships_lost} ship(s) lost")
        if self.integrity_lost:
            parts.append(f"{self.integrity_lost}% integrity lost")
        return ", ".join(parts) if parts else "no significant damage"

    def _format_enemy_losses(self):
        parts = []
        if self.enemy_fleets_destroyed:
            parts.append(f"{self.enemy_fleets_destroyed} fleet(s) destroyed")
        if self.enemy_ships_lost:
            parts.append(f"{self.enemy_ships_lost} ship(s) lost")
        if self.enemy_integrity_lost:
            parts.append(f"{self.enemy_integrity_lost}% integrity lost")
        return ", ".join(parts) if parts else "no significant damage"

    def _format_salvage(self):
        return " Salvage was detected." if self.salvage_created else ""

    def _format_opponents(self):
        if not self.opponents:
            return ""
        if len(self.opponents) == 1:
            return f" against {self.opponents[0]}"
        if len(self.opponents) == 2:
            return f" against {self.opponents[0]} and {self.opponents[1]}"
        return f" against {', '.join(self.opponents[:-1])}, and {self.opponents[-1]}"

    def format_message(self):
        lead = random.choice(self.templates).format(
            location=self._format_location(),
            opponents=self._format_opponents(),
            winner=self.winner.name,
        )
        our_losses = self._format_losses()
        enemy_losses = self._format_enemy_losses()
        summary = f"Our losses were {our_losses}; enemy losses were {enemy_losses}."
        return lead + " " + summary + self._format_salvage()


class OrbitalDefenseHitMessageFactory(MessageFactory):
    """Messages when hostile orbital fleets are hit by colony defenses."""
    category = 'COMBAT'
    priority = True
    templates_attacker = [
        "{fleet} took {damage}% integrity damage from defenses at {star}.",
        "Defensive fire from {star} damaged {fleet} by {damage}% integrity.",
        "{fleet} was hit by orbital defenses at {star}; integrity reduced by {damage}%.",
    ]
    templates_defender = [
        "Defenses at {star} damaged hostile fleet {fleet} by {damage}% integrity.",
        "Defensive batteries at {star} struck {fleet} for {damage}% integrity damage.",
        "Hostile fleet {fleet} was hit by defenses at {star}; {damage}% integrity lost.",
    ]

    def __init__(self, game, player, star, fleet, damage, perspective='attacker', message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.star = star
        self.fleet = fleet
        self.damage = int(damage)
        self.perspective = perspective

    def format_message(self):
        templates = self.templates_attacker if self.perspective == 'attacker' else self.templates_defender
        return random.choice(templates).format(
            star=format_map_object(self.star),
            fleet=format_map_object_reference(self.fleet),
            damage=self.damage,
        )


class TransferRaidThwartedMessageFactory(MessageFactory):
    """Messages when a fleet raid fails while stealing from an enemy star."""
    category = 'COMBAT'
    priority = True
    templates_attacker = [
        "Fleet {fleet} tried to take {resource_desc} from {owner} at {star}, but was thwarted and took {damage}% damage.",
        "Raid on {star} failed: {fleet} could not seize {resource_desc} from {owner}, suffering {damage}% damage.",
        "Theft run at {star} was repelled; {fleet} took {damage}% damage while trying to take {resource_desc} from {owner}.",
    ]
    templates_defender = [
        "Defenses at {star} repelled a raid by {fleet}; the attackers took {damage}% damage.",
        "Raiders from {fleet} were driven off at {star}, losing {damage}% integrity.",
        "Defense systems stopped a theft attempt at {star}; {fleet} suffered {damage}% damage.",
    ]

    def __init__(self, game, player, fleet, star, owner_name, resource_desc, damage, perspective='attacker', message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.fleet = fleet
        self.star = star
        self.owner_name = owner_name
        self.resource_desc = resource_desc
        self.damage = int(damage)
        self.perspective = perspective

    def format_message(self):
        templates = self.templates_attacker if self.perspective == 'attacker' else self.templates_defender
        return random.choice(templates).format(
            fleet=format_map_object_reference(self.fleet),
            star=format_map_object(self.star),
            owner=self.owner_name,
            resource_desc=self.resource_desc,
            damage=self.damage,
        )


class TransferAbductionThwartedMessageFactory(MessageFactory):
    """Messages when a parasitic abduction attempt is repelled."""
    category = 'COMBAT'
    priority = True
    templates_attacker = [
        "Abduction attempt at {star} failed: {fleet} could not abduct colonists from {owner} and took {damage}% damage.",
        "{fleet} was repelled while attempting to abduct colonists from {owner} at {star}; {damage}% integrity was lost.",
        "Colony defenses at {star} stopped our abduction run; {fleet} took {damage}% damage.",
    ]
    templates_defender = [
        "Defenses at {star} repelled an abduction attempt by {fleet}; attackers lost {damage}% integrity.",
        "{fleet} failed to abduct colonists at {star}; defense fire inflicted {damage}% damage.",
        "Abduction raiders from {fleet} were driven off at {star}, losing {damage}% integrity.",
    ]

    def __init__(
        self,
        game,
        player,
        fleet,
        star,
        owner_name,
        damage,
        perspective='attacker',
        resource_desc=None,
        message=None,
    ):
        super().__init__(game, player, message, intensity=-0.3)
        self.fleet = fleet
        self.star = star
        self.owner_name = owner_name
        self.damage = int(damage)
        self.perspective = perspective

    def format_message(self):
        templates = self.templates_attacker if self.perspective == 'attacker' else self.templates_defender
        return random.choice(templates).format(
            fleet=format_map_object_reference(self.fleet),
            star=format_map_object(self.star),
            owner=self.owner_name,
            damage=self.damage,
        )


class TransferColonistRaidMessageFactory(MessageFactory):
    """Messages for non-allied colonist raids with heavy pickup losses."""
    category = 'COMBAT'
    priority = True
    templates_attacker = [
        "{fleet} raided {star} for colonists from {owner}: {taken}k taken, {lost}k lost during pickup resistance, {damage}% integrity damage.",
        "Colonist raid at {star}: {fleet} took {taken}k, lost {lost}k to resistance, and suffered {damage}% damage.",
        "{fleet} extracted {taken}k colonists from {owner} at {star}, but pickup losses were {lost}k and integrity loss reached {damage}%.",
    ]
    templates_defender = [
        "{fleet} raided colonists at {star}: {taken}k were taken and {lost}k were lost during pickup resistance.",
        "Raiders from {fleet} seized {taken}k colonists at {star}; pickup losses were {lost}k.",
        "A colonist raid at {star} by {fleet} resulted in {taken}k taken and {lost}k lost amid resistance.",
    ]

    def __init__(self, game, player, fleet, star, owner_name, taken_kt, lost_kt, damage, perspective='attacker', message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.fleet = fleet
        self.star = star
        self.owner_name = owner_name
        self.taken_kt = int(taken_kt or 0)
        self.lost_kt = int(lost_kt or 0)
        self.damage = int(damage or 0)
        self.perspective = perspective

    def format_message(self):
        templates = self.templates_attacker if self.perspective == 'attacker' else self.templates_defender
        return random.choice(templates).format(
            fleet=format_map_object_reference(self.fleet),
            star=format_map_object(self.star),
            owner=self.owner_name,
            taken=self.taken_kt,
            lost=self.lost_kt,
            damage=self.damage,
        )


class TransferAbductionSuccessMessageFactory(MessageFactory):
    """Messages for successful parasitic colonist abduction."""
    category = 'COMBAT'
    priority = True
    templates_attacker = [
        "{fleet} abducted {abducted}k colonists from {owner} at {star}. Fleet integrity loss: {damage}%.",
        "Successful abduction at {star}: {fleet} abducted {abducted}k colonists from {owner} ({damage}% integrity loss).",
        "{fleet} completed an abduction run at {star}, taking {abducted}k colonists from {owner}.",
    ]
    templates_defender = [
        "{fleet} abducted {abducted}k colonists from {star}. Defenses inflicted {damage}% integrity damage on the raiders.",
        "Abduction raid at {star}: {fleet} escaped with {abducted}k colonists.",
        "{fleet} carried out a colonist abduction at {star}, taking {abducted}k.",
    ]

    def __init__(self, game, player, fleet, star, owner_name, abducted_kt, damage, perspective='attacker', message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.fleet = fleet
        self.star = star
        self.owner_name = owner_name
        self.abducted_kt = int(abducted_kt or 0)
        self.damage = int(damage or 0)
        self.perspective = perspective

    def format_message(self):
        templates = self.templates_attacker if self.perspective == 'attacker' else self.templates_defender
        return random.choice(templates).format(
            fleet=format_map_object_reference(self.fleet),
            star=format_map_object(self.star),
            owner=self.owner_name,
            abducted=self.abducted_kt,
            damage=self.damage,
        )


class SalvageCollectedMessageFactory(MessageFactory):
    """Messages for salvage collection via Transfer."""
    category = 'GENERAL'
    templates = [
        "{fleet} collected salvage from {source}: {cargo}.",
        "{fleet} recovered {cargo} from {source}.",
        "Salvage operation complete. {fleet} loaded {cargo} from {source}.",
    ]

    def __init__(self, game, player, fleet, transfers, source, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.fleet = fleet
        self.transfers = transfers or {}
        self.source = source

    def _format_cargo(self):
        parts = []
        for key, amount in self.transfers.items():
            if amount > 0:
                parts.append(f"{amount}kt {format_resource_name(key).lower()}")
        return ", ".join(parts) if parts else "salvage"

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object(self.fleet),
            cargo=self._format_cargo(),
            source=self.source,
        )


class FirstContactFleetMessageFactory(MessageFactory):
    """Messages for first confirmed identification of an enemy fleet."""
    category = 'DIPLOMATIC'
    priority = True
    templates = [
        "A fleet from {race} has been identified at {location}.",
        "Contact report: vessels from {race} have been identified at {location}.",
        "First contact: a fleet from {race} has been identified at {location}.",
    ]
    first_contact_suffix = " We are no longer alone in the universe."

    def __init__(self, game, player, fleet, other_fleet, first_any=False, message=None):
        super().__init__(game, player, message, intensity=0.3)
        self.fleet = fleet
        self.other_fleet = other_fleet
        self.first_any = first_any

    def format_message(self):
        msg = random.choice(self.templates).format(
            location=format_location(
                x=self.other_fleet.x,
                y=self.other_fleet.y,
                link=True,
                game=self.game
            ),
            race=self.other_fleet.player.name
        )
        if self.first_any:
            msg += self.first_contact_suffix
        return msg


class FirstContactStarMessageFactory(MessageFactory):
    """Messages for first confirmed identification of an enemy colony."""
    category = 'DIPLOMATIC'
    priority = True
    templates = [
        "{star} has been identified as a colony of {race}.",
        "Contact report: {star} is inhabited by {race}.",
        "First contact: {star} belongs to {race}.",
    ]
    first_contact_suffix = " We are no longer alone in the universe."

    def __init__(self, game, player, fleet, star, first_any=False, message=None):
        super().__init__(game, player, message, intensity=0.3)
        self.fleet = fleet
        self.star = star
        self.first_any = first_any

    def format_message(self):
        msg = random.choice(self.templates).format(
            fleet=format_map_object(self.fleet),
            star=format_map_object(self.star),
            race=self.star.player.name
        )
        if self.first_any:
            msg += self.first_contact_suffix
        return msg


class DiplomaticStanceChangedMessageFactory(MessageFactory):
    """Message emitted when another race's stance toward us changes."""
    category = 'DIPLOMATIC'
    priority = True

    def __init__(self, game, player, source_player, stance_label_text, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.source_player = source_player
        self.stance_label_text = stance_label_text

    def format_message(self):
        race_link = diplomacy_player_link(
            self.game,
            self.source_player,
            label='Race %s' % self.source_player.name,
        )
        return '%s has changed their stance with us. They are now %s.' % (
            race_link,
            escape(self.stance_label_text),
        )


class HabitableWorldMessageFactory(MessageFactory):
    """Messages for newly discovered habitable worlds."""
    category = 'ENVIRONMENTAL'
    templates = [
        "{fleet} has discovered a habitable world at {star}.",
        "Survey report: {star} is within habitable range for our people.",
        "{fleet} reports {star} is suitable for colonisation.",
    ]

    def __init__(self, game, player, fleet, star, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.fleet = fleet
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object(self.fleet),
            star=format_map_object(self.star)
        )


class ScannerHabitableWorldRollupMessageFactory(MessageFactory):
    """Roll up newly scanned habitable stars into a single turn message."""
    category = 'ENVIRONMENTAL'
    max_listed_stars = 6

    def __init__(self, game, player, stars, message=None):
        super(ScannerHabitableWorldRollupMessageFactory, self).__init__(
            game, player, message, intensity=0.1
        )
        self.stars = list(stars or [])

    def _format_star_list(self):
        names = [format_map_object(star) for star in self.stars]
        shown = names[:self.max_listed_stars]
        remainder = len(names) - len(shown)
        if remainder <= 0:
            return ', '.join(shown)
        return '%s, and %s more' % (', '.join(shown), remainder)

    def format_message(self):
        count = len(self.stars)
        noun = 'star' if count == 1 else 'stars'
        return (
            'Long-range scanners have detected %s potentially habitable '
            '%s: %s.'
        ) % (count, noun, self._format_star_list())


class FleetBuildBlockedNoShipyardMessageFactory(MessageFactory):
    """Messages for blocked fleet construction due to no shipyard."""
    category = 'PRODUCTION'
    priority = True
    templates = [
        "Fleet production at {star} blocked - no shipyard available.",
        "Cannot build fleet at {star} - a shipyard is required.",
        "Fleet production at {star} halted. Build a shipyard first.",
    ]

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(star=format_map_object(self.star))


class FleetRepairedMessageFactory(MessageFactory):
    """Messages for fleet repair by shipyard."""
    category = 'PRODUCTION'
    templates = [
        "{fleet} repaired from {old}% to {new}% integrity at {star}.",
        "Shipyard repairs at {star} restored {fleet} from {old}% to {new}% integrity.",
        "{fleet} underwent repairs at {star}: {old}% \u2192 {new}% integrity.",
    ]

    def __init__(self, game, player, fleet, old_integrity, new_integrity, star,
                 message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.fleet = fleet
        self.old_integrity = old_integrity
        self.new_integrity = new_integrity
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=format_map_object(self.fleet),
            old=self.old_integrity,
            new=self.new_integrity,
            star=format_map_object(self.star)
        )
