"""
Context processors for dj4xol templates.
"""
from .version import APP_VERSION


def user_theme(request):
    """Add user's theme preference to template context."""
    theme = 'classic'
    if request.user.is_authenticated:
        if hasattr(request.user, 'dj4xol_account'):
            theme = request.user.dj4xol_account.theme or 'classic'
    return {
        'user_theme': theme,
        'app_version': APP_VERSION,
    }
