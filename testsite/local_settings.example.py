"""Local development overrides.

Copy to local_settings.py and adjust as needed.
"""

from .settings import *  # noqa: F401,F403

# Example overrides:
DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "admin@localhost"
# ALLOWED_HOSTS = ['localhost', '127.0.0.1']
# STATIC_URL = '/static/'
