from .models import Game, Player, GameMessage
import random
from itertools import chain
from django.utils.html import escape


def map_object_link(obj):
    """Format a map object (Star/Fleet) as a clickable link."""
    from django.urls import reverse
    name = escape(obj.name)
    base_url = reverse('dj4xol:game', args=[obj.game.short_id])
    return f'<a href="{base_url}?x={obj.x}&y={obj.y}&sel={obj.short_id}&locate=1">{name}</a>'


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
        return random.choice(self.templates).format(race_formal=self.encounter_player.formal_name,
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
            star=map_object_link(self.star),
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
            star=map_object_link(self.star),
            deaths=self.deaths
        )


class ColonyAbandonedMessageFactory(MessageFactory):
    """Messages for when a colony is completely depopulated."""
    category = 'POPULATION'
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
        return random.choice(self.templates).format(star=map_object_link(self.star))


class PlanetoidEventMessageFactory(MessageFactory):
    """Messages for rogue planetoid environmental effects."""
    category = 'RANDOM'
    templates = [
        "A rogue planetoid passed through the {star} system and {adverb} {verb} planetary conditions.",
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
            star=map_object_link(self.star),
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
        return random.choice(self.templates).format(star=map_object_link(self.star), qty=self.qty)


class MiningDiscoveryMessageFactory(MessageFactory):
    """Messages for resource discoveries."""
    category = 'RANDOM'
    templates = [
        "A meteor impact on {star} exposed {qty} units of {resource}.",
        "Seismic activity on {star} revealed deposits of {qty} {resource}.",
        "Volcanic activity on {star} brought {qty} units of {resource} to the surface.",
    ]

    def __init__(self, game, player, star, qty, resource, message=None):
        super().__init__(game, player, message, intensity=0.3)
        self.star = star
        self.qty = qty
        self.resource = resource

    def format_message(self):
        return random.choice(self.templates).format(
            star=map_object_link(self.star),
            qty=self.qty,
            resource=self.resource
        )


class ColonyVanishedMessageFactory(MessageFactory):
    """Messages for mysterious colony disappearance (extreme negative)."""
    category = 'RANDOM'
    templates = [
        "The colony on {star} went dark without warning and survey ships found all structures intact but empty.",
        "Contact with {star} was lost and rescue teams found the colony abandoned with no survivors or explanation.",
        "The population of {star} vanished after an anomalous energy signature was detected.",
    ]

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=-1.0)
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(star=map_object_link(self.star))


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
        return random.choice(self.templates).format(star=map_object_link(self.star), qty=self.qty)


class MiningAccidentResourcesMessageFactory(MessageFactory):
    """Messages for mining accidents with resource loss."""
    category = 'RANDOM'
    templates = [
        "A storage facility breach on {star} resulted in the loss of {qty} units of {resource}.",
        "Volcanic activity on {star} destroyed {qty} {resource} in storage.",
        "An equipment malfunction on {star} resulted in the loss of {qty} {resource}.",
    ]

    def __init__(self, game, player, star, qty, resource, message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.star = star
        self.qty = qty
        self.resource = resource

    def format_message(self):
        return random.choice(self.templates).format(
            star=map_object_link(self.star),
            qty=self.qty,
            resource=self.resource
        )


class FleetBuiltMessageFactory(MessageFactory):
    """Messages for fleet construction completion."""
    category = 'PRODUCTION'
    templates = [
        "Construction of {fleet} completed at {star}.",
        "{fleet} has been commissioned at {star}.",
        "The shipyards at {star} have finished constructing {fleet}.",
    ]

    def __init__(self, game, player, star, fleet, message=None):
        super().__init__(game, player, message, intensity=0.3)
        self.star = star
        self.fleet = fleet

    def format_message(self):
        return random.choice(self.templates).format(
            star=map_object_link(self.star),
            fleet=map_object_link(self.fleet)
        )


class MineBuiltMessageFactory(MessageFactory):
    """Messages for mine construction completion."""
    category = 'PRODUCTION'
    templates = [
        "A new mine has been constructed at {star}.",
        "Mining operations have expanded at {star}.",
        "Construction of a new mine completed at {star}.",
    ]

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            star=map_object_link(self.star)
        )


class FactoryBuiltMessageFactory(MessageFactory):
    """Messages for factory construction completion."""
    category = 'PRODUCTION'
    templates = [
        "A new factory has been constructed at {star}.",
        "Industrial capacity has expanded at {star}.",
        "Construction of a new factory completed at {star}.",
    ]

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            star=map_object_link(self.star)
        )


class FleetLostMessageFactory(MessageFactory):
    """Messages for fleets lost beyond map boundaries."""
    category = 'GENERAL'
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
