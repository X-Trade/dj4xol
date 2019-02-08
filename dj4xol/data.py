from .models import Game, Star
import random
import numpy as np


class GameFactory():
    def __init__(self, game):
        self.starnamer = StarNamer()
        self.game = game

    def add_stars(self, stars):
        for _ in range(stars):
            x = random.randint(1, self.game.map_size_x - 1)
            y = random.randint(1, self.game.map_size_y - 1)
            name = self.starnamer.get_unique()
            star = Star(game=self.game, name=name, x=x, y=y)
            star.save()


class GameTurn():
    def __init__(self, game):
        self.game = game

    def generate(self):
        self._ship_movements()

    def generate_turns(self, turns):
        for _ in range(turns):
            self.generate()

    def _ship_movements(self):
        for ship in self.game.ships.all():
            order = ship.orders.first()  # this is the current order
            if not order:
                continue
            if order.target_star:
                x = order.target_star.x
                y = order.target_star.y
            elif order.target_ship:
                x = order.target_ship.x
                y = order.target_ship.y
            elif order.x and order.y:
                x = order.x
                y = order.y
            else:
                raise Exception("invalid order %s" % (str(order.id)))

            target = np.array([x, y])
            position = np.array([ship.x, ship.y])
            vector = target - position
            distance = np.linalg.norm(vector)
            print("position: %s" % (str(position)))
            print("target:   %s" % (str(target)))
            print("vector:   %s" % (str(vector)))
            print("distance: %s" % (str(distance)))
            if int(distance) <= order.warpfactor:
                ship.x = x
                ship.y = y
                if order.repeat:
                    # this may not work....
                    neworder = order
                    neworder.id = None
                    neworder.save()
                order.delete()
            else:
                normalised_vector = vector / distance
                print("normal:   %s" % (str(normalised_vector)))
                new_position = position + (normalised_vector * order.warpfactor)
                ship.x = int(new_position[0])
                ship.y = int(new_position[1])
            ship.save()


class StarNamer():
    data = ['Eridanus', 'Eridani', 'Acamar', 'Cassiopeia', 'Achird', 'Scorpius',
            'Acrab', 'Scorpii', 'Crux', 'Crucis', 'Acrux', 'Cancer', 'Cancri',
            'Acubens', 'Leo', 'Leonis', 'Leodis', 'Adhafera', 'Canis', 'Adhara',
            'Andromeda', 'Andromedae', 'Adhil', 'Taurus', 'Tauri', 'Ain',
            'Sagittarius', 'Sagittarii', 'Ainalrami', 'Lyra', 'Lyrae',
            'Aladfar', 'Alamak', 'Albaldah', 'Aquarius', 'Aquarii', 'Albali',
            'Cygnus', 'Cygni', 'Albireo', 'Corvus', 'Corvi', 'Alchiba', 'Ursa',
            'Ursae', 'Alcor', 'Alcyone', 'Aldebaran', 'Cepheus', 'Cephei',
            'Grus', 'Gruis', 'Alderamin', 'Draco', 'Draconis', 'Delphinus',
            'Delphini', 'Cepheus', 'Cephei', 'Capricorn', 'Capricornus',
            'Capricorni', 'Pegasus', 'Pegasi', 'Leod', 'Leodi', 'Leodis',
            'Algieba', 'Perseus', 'Persei', 'Algol', 'Gemini', 'Geminorum',
            'Alioth', 'Crateris', 'Auriga', 'Alkes', 'Almaaz', 'Almach', 'Grus',
            'Gruis', 'Orion', 'Orinis', 'Scorpius', 'Hydra', 'Corona',
            'Alphecca', 'Pisces', 'Piscium', 'Alrakis', 'Alpherg', 'Lynx',
            'Lyncis', 'Vela', 'Velorum', 'Aquila', 'Aquilae', 'Alsafi',
            'Alshain', 'Alshat', 'Altair', 'Serpens', 'Serpentis', 'Alya',
            'Australis', 'Borealis', 'Phoenix', 'Phoenicis', 'Aquarius',
            'Aquarii', 'Ancha', 'Ankaa', 'Anser', 'Antares', 'Arcturus',
            'Arkab', 'Lepus', 'Leporis', 'Hydrae', 'Bootes', 'Puppis', 'Carina',
            'Carinae', 'Athebyne', 'Atlas', 'Atria', 'Triangulum', 'Trianguli',
            'Avior', 'Aires', 'Arietis', 'Libra', 'Bellatrix', 'Betelgeuse',
            'Aries', 'Arietis', 'Caph', 'Capella', 'Canopus', 'Castor',
            'Castula', 'Ophiuchus', 'Cebalrai', 'Arae', 'Chalawan', 'Chamukuy',
            'Cervantes', 'Canes', 'Venatici', 'Canum', 'Venaticorum', 'Chara',
            'Charon', 'Bob', 'Chertan', 'Copernicus', 'Cor', 'Caroli', 'Cujam',
            'Cursa', 'Hercules', 'Herculis', 'Dalim', 'Fornax', 'Fornacis',
            'Deneb', 'Cetus', 'Coma', 'Berenices', 'Diadem', 'Ceti', 'Dubhe',
            'Virgo', 'Kubrick', 'Clarke', 'Columba', 'Columbia', 'Columbae',
            'Electra', 'Virginis', 'Errai', 'Enif', 'Eris', 'Elgafar', 'Edmund',
            'Garnet', 'Fomalhaut', 'Helvetios', 'Centaurus', 'Centauri', 'Izar',
            'Hadar', 'Hades', 'Haedus', 'Hell', 'Dark', 'Valhalla', 'Paradise',
            'Heze', 'Kaus', 'Keid', 'Herculaneum', 'Hel', 'Hej', 'Frost',
            'Hoth', 'Alderan', 'Izar', 'Maia', 'Lost', 'Found', 'Maia', 'Ice',
            'Eagle', 'Libertas', 'Marfark', 'Meissa', 'Meleph', 'Medusa',
            'Merak', 'Menkar', 'Menkent', 'London', 'Mesarthim', 'Mimosa',
            'Mira', 'Mirach', 'Miram', 'Mirzam', 'Muphrid', 'Musica', 'Goliath',
            'Sparta', 'Dante', 'Rana', 'Rama', 'Heka', 'Hoedus', 'Tyr', 'Tyl',
            'Tip', 'Top', 'Freedom', 'Lush', 'Fire', 'Wolf', 'Smith', 'Coronae',
            'Libra', 'Librae', 'Chomsky', 'Atlas', 'Apache', 'Io', 'Europa',
            'Ganymede', 'Callisto', 'Proxima', 'Makemake', 'Haumea', 'Mercury',
            'Soil', 'Kreutz', 'Kalt', 'Hale', 'Bopp', 'Oort', 'Kuiper', 'Sedna',
            'Vulcan', 'Vulcanoid', 'Vega', 'Apex', 'Sirius', 'Lalande', 'Cloud',
            'Wise', 'Tau', 'Luyten', 'Ross', 'Nine', 'Six', 'Four', 'Three',
            'Two', 'Titan', 'Titania', 'Rhea', 'Oberon', 'Vesta', 'Ariel',
            'Umbriel', 'Ida', 'Hyperion', 'Mimas', 'Triton', 'Tethys', 'Janus',
            'Phoebe', 'Lutetia', 'Pandora', 'Pandorum', 'Pandoria', 'Helene',
            'Mathilde', 'Doom', 'Dare', 'Tetra', 'Karma', 'Chasma', 'Mini',
            'Toriaz', 'Nova', 'Peak', 'Tempus', 'Tepid', 'Warm', 'Hubris',
            'Baxter', 'Reading', 'Bristol', 'York', 'Yorke', 'Hawking',
            'Helium', 'Dandy', 'Dorf', 'Silent', 'Red', 'Yellow', 'Orange',
            'Blue', 'Fizz', 'Adriana', 'Beata', 'Charmaine', 'Clarina',
            'Claris', 'Elyse', 'Elysium', 'Elvira', 'Joy', 'Sorrow', 'July',
            'Rome', 'Roma', 'Kiev', 'Nitra', 'Kremnica', 'Martin', 'Frankfurt',
            'Dresden', 'Chemnitz', 'Leipzig', 'Arnhem', 'Anaheim', 'Lille',
            'Paris', 'Nantes', 'Reims', 'Metz', 'Ipswitch', 'Dover', 'Margate',
            'Luton', 'Vik', 'Hoffell', 'Hofn', 'Dalvik', 'Davros', 'Reykholt',
            'Hella', 'Fjord', 'Polaris', 'Ross', 'Clyde', 'Resolute', 'Leuven',
            'Bruges', 'Tampico', 'Xalapa', 'Tula', 'Gonzalez', 'Tulum',
            'Panama', 'Belezas', 'Urucu', 'Ipixuna', 'Nile', 'Lux', 'Luxor',
            'LV-n', 'NGC-n', 'M-n', 'A-n', 'X-n', 'Messier']
    additional = ['Alpha', 'Beta', 'Delta', 'Epsilon', 'Gamma']
    suffixes = additional + ['Major', 'Minor', 'Star', 'Object', 'Majoris']
    history = []

    def _random_name(self):
        chance = random.randint(0,12)
        print(chance)
        index = random.randint(0, len(self.data)-1)
        name = self.data[index]
        if name.endswith('-n'):
            suffix = str(random.randint(49,499))
            return name[:-1] + suffix
        elif chance < 1:
            suffix = str(random.randint(49,499))
            return "%s-%s" % (name, suffix)
        elif chance <= 3:
            suffix = self.suffixes[random.randint(0, len(self.suffixes)-1)]
            return "%s %s" % (name, suffix)
        elif chance == 4:
            prefix = self.data[random.randint(0, len(self.data)-1)]
            if prefix.endswith('-n'):
                return self._random_name()
            return "%s %s" % (prefix, name)
        else:
            return name


    def get(self):
        name = self._random_name()
        self.history.append(name)
        return name

    def get_unique(self):
        while True:
            name = self._random_name()
            if not name in self.history:
                break

        self.history.append(name)
        return name
