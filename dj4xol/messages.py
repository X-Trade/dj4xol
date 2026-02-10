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
            star=map_object_link(self.star),
            qty=self.qty,
            resource=self.resource
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


class ProductionSummaryMessageFactory(MessageFactory):
    """Messages for summarized production completion (mines, factories, defenses)."""
    category = 'PRODUCTION'

    # Templates for different quantities - {count} and {star} placeholders
    # Only generate messages for 4+ items
    TEMPLATES = {
        'mine': {
            'plural': [
                "{count} mines were constructed at {star}.",
                "Mining operations expanded significantly at {star} - {count} new mines operational.",
                "{count} new mines completed at {star}.",
            ],
        },
        'factory': {
            'plural': [
                "{count} factories were built at {star}.",
                "Industrial capacity at {star} expanded with {count} new factories.",
                "{count} new factories completed at {star}.",
            ],
        },
        'defense': {
            'plural': [
                "{count} defense installations were completed at {star}.",
                "Planetary defenses at {star} strengthened with {count} new installations.",
                "{count} new defenses constructed at {star}.",
            ],
        },
    }

    def __init__(self, game, player, star, production_type, count, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.star = star
        self.production_type = production_type  # 'mine', 'factory', or 'defense'
        self.count = count

    def format_message(self):
        templates = self.TEMPLATES.get(self.production_type, {}).get('plural', [])
        if not templates:
            return f"{self.count} {self.production_type}s completed at {map_object_link(self.star)}."
        return random.choice(templates).format(
            count=self.count,
            star=map_object_link(self.star)
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
    templates = [
        "{fleet} has established a colony at {star}. Deposited {cargo} and {bonus}kt salvaged materials.",
        "Colony established at {star} by {fleet}. {cargo} unloaded, {bonus}kt bonus materials recovered.",
        "{fleet} completed colonisation of {star}. Cargo transferred: {cargo}. Salvage: {bonus}kt.",
    ]

    def __init__(self, game, player, fleet_name, star, cargo_summary, bonus_materials, message=None):
        super().__init__(game, player, message, intensity=0.5)
        self.fleet_name = fleet_name
        self.star = star
        self.cargo_summary = cargo_summary
        self.bonus_materials = bonus_materials

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=self.fleet_name,
            star=map_object_link(self.star),
            cargo=self.cargo_summary,
            bonus=self.bonus_materials
        )


class ColoniseFailedNoStarMessageFactory(MessageFactory):
    """Messages for failed colonisation attempts (no star at location)."""
    category = 'EXCEPTION'
    priority = True
    templates_with_star = [
        "{fleet} failed to colonise {star} - it was not found at ({x}, {y}).",
        "Colonisation of {star} by {fleet} aborted - no planet at ({x}, {y}).",
        "{fleet} arrived at ({x}, {y}) to colonise {star}, but found nothing.",
    ]
    templates_no_star = [
        "{fleet} aborted colonisation at ({x}, {y}) - no habitable world found.",
        "Colonisation order for {fleet} cancelled - no planet at ({x}, {y}).",
        "{fleet} reached ({x}, {y}) but found no world to colonise.",
    ]

    def __init__(self, game, player, fleet_name, x, y, target_star=None, message=None):
        super().__init__(game, player, message, intensity=-0.2)
        self.fleet_name = fleet_name
        self.x = x
        self.y = y
        self.target_star = target_star

    def format_message(self):
        if self.target_star:
            return random.choice(self.templates_with_star).format(
                fleet=self.fleet_name,
                star=map_object_link(self.target_star),
                x=self.x,
                y=self.y
            )
        else:
            return random.choice(self.templates_no_star).format(
                fleet=self.fleet_name,
                x=self.x,
                y=self.y
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

    def __init__(self, game, player, fleet_name, star, message=None):
        super().__init__(game, player, message, intensity=-0.2)
        self.fleet_name = fleet_name
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=self.fleet_name,
            star=map_object_link(self.star)
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
                parts.append(f"{amount}kt {resource}")
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
            fleet=map_object_link(self.fleet),
            warp=self.warp_speed,
            integrity_loss=self.integrity_loss,
            cargo_desc=self._format_cargo_desc(),
            colonist_deaths=self.colonist_deaths
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
    salvage_suffix_space = " Salvage left at ({x}, {y})."

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
            return f"near {map_object_link(star)}"
        return f"in empty space ({self.x}, {self.y})"

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
                    star=map_object_link(self.salvage_location)
                )
            else:
                msg += self.salvage_suffix_space.format(x=self.x, y=self.y)

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
            target=map_object_link(self.target_fleet),
            ships=self.target_fleet.ship_count
        )


class FleetScuttledMessageFactory(MessageFactory):
    """Messages for fleet scuttling."""
    category = 'GENERAL'
    priority = True
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
            return map_object_link(star)
        return f"in empty space ({self.x}, {self.y})"

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
                location=map_object_link(self.salvage_location)
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
        "Combat at {location}. {winner} prevailed. {losses} {salvage}",
        "Battle report: {location}. {winner} won. {losses} {salvage}",
        "Engagement at {location} ended. {winner} holds the field. {losses} {salvage}",
    ]

    def __init__(self, game, player, winner, location,
                 fleets_destroyed=0, ships_lost=0, integrity_lost=0,
                 salvage_created=False, message=None):
        super().__init__(game, player, message, intensity=-0.2)
        self.winner = winner
        self.location = location
        self.fleets_destroyed = fleets_destroyed
        self.ships_lost = ships_lost
        self.integrity_lost = integrity_lost
        self.salvage_created = salvage_created

    def _format_location(self):
        if isinstance(self.location, tuple):
            x, y = self.location
            return f"({x}, {y})"
        return map_object_link(self.location)

    def _format_losses(self):
        parts = []
        if self.fleets_destroyed:
            parts.append(f"{self.fleets_destroyed} fleet(s) destroyed")
        if self.ships_lost:
            parts.append(f"{self.ships_lost} ship(s) lost")
        if self.integrity_lost:
            parts.append(f"{self.integrity_lost}% integrity lost")
        if not parts:
            return "No significant losses reported."
        return "Losses: " + ", ".join(parts) + "."

    def _format_salvage(self):
        return "Salvage detected." if self.salvage_created else "No salvage detected."

    def format_message(self):
        return random.choice(self.templates).format(
            location=self._format_location(),
            winner=self.winner.name,
            losses=self._format_losses(),
            salvage=self._format_salvage()
        )


class SalvageCollectedMessageFactory(MessageFactory):
    """Messages for salvage collection via Transfer."""
    category = 'GENERAL'
    templates = [
        "{fleet} collected salvage: {cargo}.",
        "{fleet} recovered {cargo} from the debris field.",
        "Salvage operation complete. {fleet} loaded {cargo}.",
    ]

    def __init__(self, game, player, fleet, iron, bor, germ, message=None):
        super().__init__(game, player, message, intensity=0.2)
        self.fleet = fleet
        self.iron = iron
        self.bor = bor
        self.germ = germ

    def _format_cargo(self):
        parts = []
        if self.iron > 0:
            parts.append(f"{self.iron}kt ironium")
        if self.bor > 0:
            parts.append(f"{self.bor}kt boranium")
        if self.germ > 0:
            parts.append(f"{self.germ}kt germanium")
        return ", ".join(parts) if parts else "nothing"

    def format_message(self):
        return random.choice(self.templates).format(
            fleet=map_object_link(self.fleet),
            cargo=self._format_cargo()
        )


class FleetBuildBlockedNoShipyardMessageFactory(MessageFactory):
    """Messages for blocked fleet construction due to no shipyard."""
    category = 'PRODUCTION'
    priority = True
    templates = [
        "Fleet construction at {star} blocked - no shipyard available.",
        "Cannot build fleet at {star} - a shipyard is required.",
        "Fleet production at {star} halted. Build a shipyard first.",
    ]

    def __init__(self, game, player, star, message=None):
        super().__init__(game, player, message, intensity=-0.3)
        self.star = star

    def format_message(self):
        return random.choice(self.templates).format(star=map_object_link(self.star))


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
            fleet=map_object_link(self.fleet),
            old=self.old_integrity,
            new=self.new_integrity,
            star=map_object_link(self.star)
        )
