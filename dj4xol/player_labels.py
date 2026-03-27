"""Shared helpers for rendering player labels in UI text."""

AI_MODULE_LABELS = {
    'micromanager': 'Micromanager',
    'expansionist': 'Expansionist',
    'idle': 'Idle',
    'openai': 'OpenAI-Compatible',
}


def ai_module_label(module_code):
    """Return a readable AI module label from a stored module code."""
    code = str(module_code or '').strip()
    if not code:
        return 'AI'
    normalised = code.lower()
    label = AI_MODULE_LABELS.get(normalised)
    if label:
        return label
    words = [
        ('AI' if token == 'ai' else token.capitalize())
        for token in normalised.replace('-', '_').split('_')
        if token
    ]
    if not words:
        return 'AI'
    return ' '.join(words)


def player_bracket_label(player, unknown='Unknown'):
    """Return the bracket text shown after a player name."""
    if not player:
        return str(unknown or 'Unknown')
    account = getattr(player, 'account', None)
    alias = getattr(account, 'alias', None)
    if alias:
        return str(alias)
    if bool(getattr(player, 'is_ai', False)):
        return ai_module_label(getattr(player, 'ai_module', ''))
    return str(unknown or 'Unknown')


def player_name_with_bracket(player, name=None, unknown_name='Unknown race', unknown_label='Unknown'):
    """Return a player name with a human/AI descriptor in brackets."""
    if not player:
        return str(unknown_name or 'Unknown race')
    player_name = str(name or getattr(player, 'name', None) or getattr(player, 'plural_name', None) or unknown_name)
    return '%s (%s)' % (player_name, player_bracket_label(player, unknown=unknown_label))
