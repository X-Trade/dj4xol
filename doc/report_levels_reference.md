# Report Levels Reference

This is a developer-facing reference for the report tiers used by the
report cache, detail panel, scanner reports, and encounter reports.

## Report Tiers

The code currently uses four report tiers:

- `ownership`
- `basic`
- `advanced`
- `encounter`

Higher tiers override lower tiers for the same player/object report.

## Acquisition By Game Type

### Scanners-Yes Games

- Basic scanners at range create `basic` reports.
- Advanced scanners at range create `advanced` reports.
- Direct visits create `encounter` reports.
- Encounter fleet cargo is only included if an advanced scanner source is
  present at that location.

### No-Scanners Games

- All stars and fleets are visible on the map immediately.
- No ranged scanner reports are generated.
- Reports are learned by visiting the object directly.
- The visiting fleet's scanner level determines the visit tier:
  - no scanners: `ownership`
  - basic scanners: `basic`
  - advanced scanners: `advanced`
  - exceptionally strong advanced scanners currently escalate to
    `encounter`

## Stars

### Ownership

- Name and position
- Owner only

### Basic

- Name and position
- Environmentals
- Habitability summary:
  - capacity
  - survivable / not survivable
- No ownership
- No population
- No minerals
- No infrastructure

### Advanced

- Everything from `basic`
- Ownership
- Population
- Mineral yields
- Surface mineral deposits
- No infrastructure

### Encounter

- Everything from `advanced`
- Infrastructure:
  - mines
  - factories and available BP
  - labs and available RP
  - colony scanner ranges
  - defenses
  - shipyards
  - jobs / employment

## Fleets

### Ownership

- Name and position
- Owner only

### Basic

- Position
- Motion summary data:
  - heading
  - travel warp
- Fleet identity remains obfuscated in scanners-yes games
- No owner
- No composition
- No cargo

### Advanced

- Everything from `basic`
- Ownership
- Ship count
- Integrity
- No capability breakdown
- No cargo by default

### Encounter

- Everything from `advanced`
- Fleet capabilities:
  - max safe warp
  - bombs
  - miners
  - fuel factory
  - wormhole drive
  - scanner ranges
- Fleet cargo/inventory only when the encounter is accompanied by an
  advanced scanner source

## Salvage

### Ownership

- Name and position
- Salvage type
- Total minerals

### Basic

- Name and position
- Total minerals
- Salvage type is shown for normal salvage
- Ancient debris keeps its type hidden
- No mineral breakdown

### Advanced / Encounter

- Name and position
- Salvage type
- Full mineral inventory breakdown

## Anomalies

### Ownership

- Name and position

### Basic

- Name and position
- Anomaly type

### Advanced / Encounter

- Name and position
- Anomaly type
- Description
- Heading
- Stability
- Wormhole pairing data where relevant

## Important Distinctions

- In scanners-yes games, ranged `advanced` star reports reveal ownership,
  population, and minerals, but not infrastructure.
- Infrastructure is intended to be an encounter-level reveal.
- In scanners-yes games, ranged `basic` fleet reports reveal presence and
  motion, but not identity or composition.
- Fleet cargo is stricter than fleet composition. Cargo is an
  encounter-plus-advanced-scanner reveal, not a normal ranged advanced
  reveal.
