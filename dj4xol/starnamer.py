import random


class StarNamer():
    _data = ['Eridanus', 'Eridani', 'Acamar', 'Cassiopeia', 'Achird',
             'Venticuli', 'Reticuli', 'Weasel', 'Aldershot', 'Drax',
             'Exus', 'Diem', 'Corpus', 'Littleferry', 'Skeldon', 'Birmingham',
             'Exodus', 'Alfirk', 'Algedi', 'Aldulfin', 'Alfarasalkamil',
             'Scorpius', 'Acrabis', 'Scorpia', 'Crux', 'Crucis', 'Acrux',
             'Axolotl', 'Ayeyarwady', 'Areyeready', 'Baekdu', 'Bagu',
             'Bake-eo', 'Indus', 'Sectans', 'Bibha', 'Bodu', 'Bosona',
             'Cexing', 'Chechia', 'Chaophraya', 'Chalawan', 'Detroit',
             'Deltoton', 'Plymouth', 'Danfeng', 'Oceanic', 'Dombay', 'Dofida',
             'Diya', 'Dazzle', 'Blazes', 'Sparkle', 'Yll', 'Ebla', 'Izarra',
             'Dziban', 'Electra', 'Alnath', 'Hubble', 'Tycho', 'Elnath',
             'Edwin', 'Eltanin', 'Elkurud', 'Discovery', 'Oumuamua',
             'Alnitak', 'Alnilam', 'Llama', 'Aludra',
             'Alula', 'Crater', 'Ascella', 'Atakoraka', 'Apostrophe',
             'Cancer', 'Cancri', 'Acrab', 'Acubens', 'Leo', 'Leonis', 'Ledis',
             'Adhafera', 'Canis', 'Adhara', 'Andromeda', 'Andromedae', 'Adhil',
             'Taurus', 'Tauri', 'Ain', 'Arrus', 'Sagittarius', 'Sagittaria',
             'Ainalrami', 'Lyra', 'Lyrae', 'Lyrus', 'Aladfar', 'Alamak',
             'Ster', 'Estrella', 'Isotor', 'Zvezda', 'Zorka',
             'Stjer', 'Stern', 'Stilla', 'Zvaigznea', 'Estrela', 'Ulduz',
             'Albaldah', 'Aquarius', 'Aq', 'Albali', 'Aquila', 'Cygnus',
             'Cygni', 'Albireo', 'Corvus', 'Corvi', 'Alchiba', 'Ursa', 'Ursae',
             'Alcyone', 'Aldebaran', 'Cephus', 'Cephei', 'Calabra', 'Grus',
             'Gruis', 'Alderamin', 'Delphis', 'Adelphi', 'Delphini', 'Cephcus',
             'Cettei', 'Capricorn', 'Capricornus', 'Capri', 'Capricorni',
             'Pegasus', 'Pegasi', 'Leod', 'Leodi', 'Leodis', 'Leon', 'Algieba',
             'Perseus', 'Persei', 'Algol', 'Gemini', 'Algorab', 'Alioth',
             'Crateris', 'Auriga', 'Alkes', 'Almaaz', 'Almach', 'Gaus',
             'Grubis', 'Orion', 'Orinis', 'Scarra', 'Hydra', 'Corona',
             'Coronae', 'Alphecca', 'Pisces', 'Piscium', 'Alrakis', 'Alpherg',
             'Lynx', 'Abel', 'Lyncis', 'Vela', 'Velorum', 'Aquillia',
             'Aquilae', 'Alsafi', 'Vala', 'Alshain', 'Alshat', 'Altair',
             'Serpens', 'Serpentis', 'Alya', 'Alyra', 'Australis', 'Borealis',
             'Phoenix', 'Phoenicis', 'Aqua', 'Arcturus', 'Aquaria', 'Ancha',
             'Ankaa', 'Anser', 'Antares', 'Arctura', 'Aria', 'Arkab', 'Lepus',
             'Leporis', 'Hydrae', 'Boot', 'Puppis', 'Carina', 'Carinae',
             'Athebyne', 'Atuska', 'Atria', 'Triangulum', 'Trianguli', 'Avior',
             'Aires', 'Arietis', 'Liber', 'Bellatrix', 'Betelgeuse', 'Aries',
             'Airetus', 'Caph', 'Capella', 'Canopus', 'Castor', 'Castoris',
             'Castula', 'Ophiuchus', 'Cebalrai', 'Arae',
             'Chamukuy', 'Cervantes', 'Canes', 'Venatici', 'Canum',
             'Venaticorum', 'Chara', 'Charon', 'Bob', 'Chertan', 'Copernicus',
             'Cor', 'Cujam', 'Cursa', 'Hercules', 'Herculis',
             'Dalim', 'Fornax', 'Fornacis', 'Cetus', 'Coma',
             'Berenices', 'Diadem', 'Ceti', 'Debuhe', 'Virgo', 'Kubrick',
             'Clarke', 'Columba', 'Columbia', 'Columbae', 'Electris',
             'Virginis', 'Errai', 'Enif', 'Eris', 'Elgafar', 'Edmund',
             'Garnet', 'Fomalhaut', 'Helvetios', 'Centaurus', 'Centauri',
             'Izar', 'Hadar', 'Hades', 'Haedus', 'Hell', 'Dark', 'Valhalla',
             'Paradise', 'Haze', 'Kaus', 'Keid', 'Herculaneum', 'Hel', 'Hej',
             'Frost', 'Hath', 'Alderan', 'Czar', 'Mala', 'Lost', 'Found',
             'Maia', 'Ice', 'Mizar', 'Mintaka', 'Eagle', 'Libertas', 'Marfark',
             'Meissa', 'Meleph', 'Medusa', 'Merak', 'Menkar', 'Menkent',
             'London', 'Mesarthim', 'Mimosa', 'Mira', 'Mirach', 'Miram',
             'Mirzam', 'Muphrid', 'Musica', 'Goliath', 'Sparta', 'Dante',
             'Rana', 'Rama', 'Heka', 'Hoedus', 'Tyr', 'Tyl', 'Tip', 'Top',
             'Lush', 'Fire', 'Wolf', 'Smith', 'Coronis', 'Libra', 'Gert'
             'Librae', 'Chomsky', 'Atlas', 'Apache', 'Io', 'Euridae', 'Cassa',
             'Ganymede', 'Callisto', 'Proxima', 'Makemake', 'Haumea', 'Churn',
             'Chronus', 'Brea', 'Sol', 'Tellar', 'Hydroxus', 'Tallux',
             'Mercuri', 'Solus', 'Kreutz', 'Kalt', 'Hale', 'Bopp', 'Oort',
             'Kuiper', 'Sedna', 'Vulcan', 'Vulcanoid', 'Vega', 'Apex',
             'Kronos', 'Pol', 'Lox', 'Dax', 'Porto', 'Challus', 'Lloyd',
             'Tolkein', 'Weir', 'Clark', 'Beskar', 'Brisk', 'Deft', 'Dolt',
             'Frisk', 'Whisk', 'Ender', 'Never', 'Bright', 'Tee', 'Frank',
             'Poole', 'Dave', 'Bowman', 'Fright', 'Boop', 'Hailey', 'Chum',
             'Guy', 'Star', 'Yell', 'Nyota', 'Tartarus', 'Real', 'Inkanyezi',
             'Imzadi', 'Stark', 'Eden', 'Soup', 'Serene', 'Mist', 'Chow',
             'Opportunity', 'Backwards', 'Drawerof', 'Sdrawkcab', 'Isengard'
             'Sirius', 'Lalande', 'Cloud-n', 'Wise', 'Tau', 'Luyten', 'Rachael',
             'Nine', 'Six', 'Four', 'Three', 'Two', 'Titan', 'Titania', 'Rhea',
             'Oberon', 'Vesta', 'Ariel', 'Umbriel', 'Ida', 'Hyperion', 'Mimas',
             'Triton', 'Tethys', 'Janus', 'Phoebe', 'Lutetia', 'Pandora',
             'Pandorum', 'Pandoria', 'Helene', 'Mathilde', 'Doom', 'Dare',
             'Tetra', 'Karma', 'Chasma', 'Minmi', 'Toriaz', 'Nova', 'Peak',
             'Tempus', 'Tepid', 'Warm', 'Hubris', 'Baxter', 'Reed','Hole',
             'Bristolis', 'York', 'Yorke', 'Hawking', 'Einstein', 'Helium',
             'Dandy', 'Dorf', 'Silent', 'Red', 'Yellow', 'Orange', 'Blue',
             'Fizz', 'Adriana', 'Beata', 'Charmaine', 'Clarina', 'Scoff',
             'Claris', 'Elyse', 'Elysium', 'Elvira', 'Joy', 'Sorrow', 'July',
             'Rome', 'Roma', 'Kiev', 'Nitra', 'Kremnica', 'Martin', 'Goth',
             'Frankfurt', 'Dresden', 'Chemnitz', 'Leipzig', 'Arnhem',
             'Anaheim', 'Lille', 'Paris', 'Nantes', 'Reims', 'Metz', 'Babylon',
             'Ipswitch', 'Dover', 'Margate', 'Luton', 'Vik', 'Hoffell', 'Hofn',
             'Dalvik', 'Davros', 'Reykholt', 'Hella', 'Fjord', 'Polaris',
             'Russ', 'Clyde', 'Resolute', 'Leuven', 'Bruges', 'Tampico',
             'Xalapa', 'Tula', 'Gonzalez', 'Tulum', 'Apophis', 'Panama',
             'Belezas', 'Urucu', 'Ipixuna', 'Nile', 'Lux', 'Luxor', 'Idan',
             'Eve', 'Elesta', 'Evastrum', 'Floyd', 'Farstar', 'Elysia',
             'Elystia', 'Europa', 'Eurystheus', 'Eurydice', 'Eureka', 'Fall',
             'Helbt', 'Harth', 'Hoth', 'Hebrides', 'Hera', 'Hermes',
             'Hermione', 'Juno', 'Manley', 'Kerban', 'Kerbol', 'Kantor',
             'Kant', 'Koth', 'P3X-n', 'P2C-n', 'LV-n', 'NGC-n', 'M-n', 'A-n',
             'X-n', 'G-n', 'Y-n', '???-n', '2001-n', '2010-n', '2061-n',
             '2099-n', '1969-n', '1977-n', 'Messier', 'Caldwell', 'Coruscant',
             'Tatooine', 'Aulderaan', 'Naboo', 'Endor', 'Yavin', 'Kashyyyk',
             'Dagobah', 'Bespin', 'Kamino', 'Geonosis', 'Utapau', 'Mustafar',
             'Polis', 'Massa', 'Mygeeto', 'Felucia', 'Cato', 'Neimoidia',
             'Saleucami', 'Ithor', 'Kessel', 'Corellia', 'Rodia', 'Nal',
             'Dantooine', 'Bestine', 'Iridium', 'Iridia', 'Iridis',
             'Iridiumis', 'Iris', 'Trus', 'Ophiuchi', 'Cygnae', 'Cygne',
             'Cygnea', 'Cygnean', 'Signius', 'Dantus', 'Dart', 'Krell',
             'Vulcanus', 'Vulcani', 'Cetaurus', 'Centauris',
             'Pollux', 'Geminorum', 'Gliese', 'Draconis', 'Draco', 'Duna',
             'Dunai', 'Dunae', 'Dunis', 'Herschel', 'Herschelian', 'Herscheli',
             'Herschelium', 'Herschelis', 'Feynman', 'Feyn', 'Feyni',
             'Oppenheimer', 'Beowulf', 'Rigel', 'Bajor', 'Azati', 'Niobe',
             'Lankal', 'Hydri', 'Hutzel', 'Cirini', 'Magellan', 'Aquarii',
             'Bortas', 'Bopak', 'Ajiilon', 'Akaali', 'Corvan', 'Crepuscula',
             'Alcor', 'Caroli', 'Sthrlius', 'Argelius', 'Argus',
             'Cygnet', 'Galen', 'Doradus', 'Notradame', 'Erius', 'Eridon',
             'Equulei', '7A', '7B', '4F', 'Cruces', 'Deneb', 'Kaitos',
             'Deneva', 'Denika', 'Denkir', 'Dessica', 'Detrion', 'Roosevelt',
             'Guinnevere', 'Gideon', 'Dorala', 'Doraziala', 'Grynnan', 'Haika',
             'Hanolan', 'Hanon', 'Harlak', 'Gray', 'Hasparga', 'Halee',
             'Elora', 'Eminar', 'Heziea', 'Hupyria', 'Aira', 'Icobar', 'Mynos',
             'Nil', 'Nullplace', 'Indri', 'Illyria', 'Bootes',
             'Phoeneticus', 'Tyrus', 'Tyrell', 'Invictus',
             'Sculptoris', 'Pavonis', 'Kaleb', 'Kalla', 'Kalandra', 'Tuscanae',
             'Telos', 'Five', 'Finibus', 'Forcas', 'Kabrel', 'Gallum',
             'Galacrux', 'Galador', 'Galar', 'Ogat', 'Obey', 'Kessik',
             'Khitomer', 'Kholfa', 'Kiley', 'Kendren', 'Korat', 'Korinar',
             'Koralis', 'Korval', 'Kotanka', 'Organa', 'Ovion',
             'Pallas', 'Fury', 'Parada', 'Pacifica', 'X', 'P', 'Z',
             'Lorval', 'Praxis', 'Prexnak', 'Prospero', 'Octantis',
             'Lutani', 'Lysia', 'Porridge', 'Kale', 'Orchid', 'Primula',
             'Quantal', 'Korvos', 'Korvat', 'Rakon', 'Rator',
             'Megrez', 'Mericor', 'Minari', 'Miziar', 'Quantum', 'Nausicaa',
             'Romil', 'Skarra', 'Bento', 'Toroth', 'Ross', 'Rymus', 'Toron',
             'Riker', 'Romulus', 'Remus', 'Sauria', 'Vadik', 'Vault',
             'Ventax', 'Skeralyx', 'Solaris', 'Talos', 'Xantion', 'Xenia',
             'Tameron', 'Tangram', 'Chase', 'Xol', 'Exogul', 'Terra', 'Zaran',
             'Terra Firma', 'Tiber', 'Tholia', 'Well', 'Sheva', 'Septimus',
             'Setlik', 'Untari']
    _additional = ['Alpha', 'Beta', 'Delta', 'Epsilon', 'Gamma', 'Zeta', 'Eta',
                  'Theta', 'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi',
                  'Omicron', 'Pi', 'Rho', 'Sigma', 'Tau', 'Upsilon', 'Phi',
                  'Chi', 'Psi', 'Omega', 'Rama']
    _suffixes = _additional + ['Major', 'Minor', 'Star', 'Object', 'Torment',
                               'Majoris', 'Minoris', 'A', 'B', 'C', 'D', 'E',
                               'X', 'Y', 'Z', 'I', 'II', 'III', 'IV', 'V',
                               'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
    _prefixes = _additional + ['New', 'Old', 'Nova', 'Neo', 'Free', 'High',
                               'Low']
    history = []
    cluster_prefixes = [
        'Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta',
        'Theta', 'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi',
        'Omicron', 'Pi', 'Rho', 'Sigma', 'Tau', 'Upsilon', 'Phi',
        'Chi', 'Psi', 'Omega',
    ]

    def __init__(self, history=None):
        if isinstance(history, list):
            self.history = history


    def _random_name(self, index=None, chance=None):
        if chance is None:
            chance = random.randint(0,12)
        if index is None:
            index = random.randint(0, len(self._data)-1)

        name = self._data[index]

        if name.endswith('-n'):
            suffix = str(random.randint(49,499))
            return name[:-1] + suffix
        elif chance < 1:
            suffix = str(random.randint(49,499))
            return "%s-%s" % (name, suffix)
        elif chance <= 3:
            suffix = self._suffixes[random.randint(0, len(self._suffixes)-1)]
            return "%s %s" % (name, suffix)
        elif chance <= 6:
            prefix = self._prefixes[random.randint(0, len(self._prefixes)-1)]
            if prefix.endswith('-n'):
                return self._random_name()
            return "%s %s" % (prefix, name)
        elif chance <= 7:
            if random.randint(0, 3) == 0:
                return name
            prefix = self._data[random.randint(0, len(self._data)-1)]
            if prefix.endswith('-n'):
                return self._random_name()
            return "%s %s" % (prefix, name)
        else:
            return name

    #TODO: implement generator pattern

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

    def _random_root_name(self):
        while True:
            name = self._data[random.randint(0, len(self._data) - 1)]
            if name.endswith('-n'):
                continue
            return name

    def get_unique_root(self, used_roots=None):
        used_roots = used_roots or set()
        while True:
            name = self._random_root_name()
            if name in used_roots:
                continue
            if name in self.history:
                continue
            self.history.append(name)
            return name
