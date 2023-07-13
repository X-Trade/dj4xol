from .models import Game, Player, PlayerRace, GameMessage
import random
from itertools import chain

def weighted_random_choice(choices, offset, window_size=1):
        """Select a random choice from a list of choices, with a moving window based on intensity."""
        position = offset * (len(choices)-1) + random.randint(0-window_size, window_size)
        position = min(max(position, 0), len(choices)-1)
        return choices[int(position)]

class GameEvent():
    game = None
    player_race = None
    encounter_race = None

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
    intensity = 0.0

    def __init__(self, game, player_race, message=None, intensity=0.0):
        if not message:
            message = GameMessage()
            message.game = game
            message.player = player_race.player
        self.message = message
        self.intensity = intensity

    def new_message(self, intensity=None):
        if intensity is not None:
            self.intensity = intensity
        self.message.message = self.generate_message(intensity)
        return self.message

    def generate_adverb(self):
        """select from the adverbs using a moving window based on intensity"""
        if self.intensity > 0.1:
            adverbs = list(chain(self.DEFAULT_ADVERBS, self.POSITIVE_ADVERBS))
        elif self.intensity < 0.1:
            adverbs = list(chain(self.DEFAULT_ADVERBS, self.NEGATIVE_ADVERBS))
        else:
            adverbs = self.DEFAULT_ADVERBS
        
        return weighted_random_choice(adverbs, self.get_absolute_intensity(), 2)
    
    def generate_verb(self):
        """select from the verbs using a moving window based on intensity"""
        if self.intensity >= 0.0:
            verbs = list(self.POSITIVE_VERBS)
        elif self.intensity < 0.0:
            verbs = list(self.NEGATIVE_VERBS)
        
        return weighted_random_choice(verbs, self.get_absolute_intensity(), 2)
    
    def get_absolute_intensity(self):
        return min(abs(self.intensity), 1.0)
    
    def generate_message(self):
        return random.choice(self.templates).format(
            adverb=self.generate_adverb(),
            verb=self.generate_verb()
        )
    
    def format_outcome(self, item, quantity):
        verbs = self.TAKE_VERBS if quantity > 0 else self.GIVE_VERBS
        verb = weighted_random_choice(verbs, self.get_absolute_intensity(), 2)
        quantity = abs(quantity)
        return "We have {verb} {quantity} {item}. ".format(verb=verb, quantity=quantity, item=item)
    
    def append_outcome(self, item, quantity):
        self.message.message += self.format_outcome(item, quantity)


class DiplomaticMessageFactory(MessageFactory):
    templates = ["A representative of {race_formal} was recieved and {adverb} {verb}. ",
                 "A representative was dispatched to {race_formal} and was {adverb} {verb}. ",
                 "A delegation was received by {race_formal}. They were {adverb} {verb}. ",
                 "A delegation was recieved from {race_formal}. They were {adverb} {verb}. ",
                 "A party was sent to {race_formal}. They were {adverb} {verb}. "]
    
    def __init__(self, game, player_race, encounter_race, message=None, intensity=0.0):
        super(DiplomaticMessageFactory, self).__init__(game, player_race, message, intensity)
        self.encounter_race = encounter_race
        
    def generate_message(self):
        return random.choice(self.templates).format(race_formal = self.encounter_race.formal_name,
                                                    adverb=self.generate_adverb(),
                                                    verb=self.generate_verb())
