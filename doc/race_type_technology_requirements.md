# Race Type Technology Requirements

Technology items can include a `race_type` entry in `params_json` to gate that one item by `ServerRaceType`. This only affects the technology item itself: players can still keep researching the category level, but gated items are hidden from their Research screen and ignored by backend tech-effect lookups.

Supported expressions are intentionally small and safe:

- `JOAT`
- `is WAR`
- `not JOAT`
- `has has_superweapon`
- `has defence_multiplier > 1.2`
- `has has_advanced_remoteminers`

Rules:

- `CODE`, `is CODE`, and `not CODE` match the race type `code`.
- `has FIELD` checks whether a boolean or value-like field is truthy.
- `has FIELD OP VALUE` supports `=`, `==`, `!=`, `>`, `<`, `>=`, `<=`.
- Field names must be simple identifiers from `ServerRaceType`.
- Values are parsed as booleans (`true/false`, `yes/no`, `on/off`), integers, floats, or plain text.

Examples:

- `{"race_type": "not WAR"}` means Warmongers cannot use that technology.
- `{"race_type": "SCI"}` means only Scientists can use it.
- `{"race_type": "has has_advanced_remoteminers"}` means the item is available only to race types with that trait enabled.

The Technology Directory still shows gated items and explains the requirement in English. Gameplay-facing systems treat the requirement as a hard access gate when selecting unlocked technology effects.

