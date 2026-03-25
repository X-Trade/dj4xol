import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from .models import Account, EmailRollupLog, ServerSettings
from .diplomatic_contracts import build_incoming_contract_alert_entries

logger = logging.getLogger(__name__)

ROLLUP_CATEGORIES = ('RANDOM', 'COMBAT', 'DIPLOMATIC', 'EXCEPTION')


def _email_enabled():
    value = ServerSettings.get('enable_email', 'False')
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _get_from_email():
    contact = ServerSettings.get('server_contact', '')
    if contact:
        return contact
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@localhost')


def _get_server_url():
    return ServerSettings.get('server_url', '').rstrip('/')


def _game_url(game, base_url):
    path = reverse('dj4xol:game', args=[game.short_id])
    if base_url:
        return base_url + path
    return path


def _unsubscribe_url(account, base_url):
    path = reverse('dj4xol:unsubscribe_email', args=[account.email_unsubscribe_key])
    if base_url:
        return base_url + path
    return path


def _verify_email_url(account, base_url):
    path = reverse(
        'dj4xol:verify_email',
        args=[account.email_verification_key],
    )
    if base_url:
        return base_url + path
    return path


def _profile_url(base_url):
    path = reverse('dj4xol:profile')
    if base_url:
        return base_url + path
    return path


def _join_game_url(game, base_url):
    path = reverse('dj4xol:join_game', args=[game.short_id])
    if base_url:
        return base_url + path
    return path


def _normalise_email_theme(theme_code):
    valid = {choice[0] for choice in Account.THEME_CHOICES}
    if theme_code in valid:
        return theme_code
    return 'classic'


def _send_account_email(
    subject,
    body_text,
    from_email,
    recipient_email,
    account=None,
    html_template=None,
    html_context=None,
):
    html_enabled = bool(account and getattr(account, 'email_html_enabled', False))
    if html_enabled and html_template:
        context = dict(html_context or {})
        context.setdefault(
            'email_theme',
            _normalise_email_theme(getattr(account, 'theme', 'classic')),
        )
        context.setdefault('email_subject', subject)
        try:
            html_body = render_to_string(html_template, context)
        except Exception:
            logger.exception(
                'Failed to render HTML email template %s for %s; falling back to text.',
                html_template,
                recipient_email,
            )
        else:
            message = EmailMultiAlternatives(
                subject=subject,
                body=body_text,
                from_email=from_email,
                to=[recipient_email],
            )
            message.attach_alternative(html_body, 'text/html')
            message.send(fail_silently=False)
            return

    send_mail(
        subject=subject,
        message=body_text,
        from_email=from_email,
        recipient_list=[recipient_email],
        fail_silently=False,
    )


def _verified_account_email_allowed(account, stdout=None, label='email'):
    if not account:
        return False, 'No account'
    if not getattr(account, 'email', ''):
        return False, 'No email address'
    if not getattr(account, 'email_verified', False):
        if stdout:
            stdout.write('Email not verified; skipping %s.' % label)
        return False, 'Email not verified'
    return True, 'Allowed'


def _verified_account_for_email(recipient_email, stdout=None):
    if not recipient_email:
        return None, 'No email address'
    account = Account.objects.filter(email__iexact=recipient_email).first()
    if not account:
        if stdout:
            stdout.write(
                'No verified account matches %s; skipping invite email.'
                % recipient_email
            )
        return None, 'No verified account'
    allowed, reason = _verified_account_email_allowed(
        account,
        stdout=stdout,
        label='invite email',
    )
    if not allowed:
        return None, reason
    return account, 'Allowed'


def send_game_invite_email(game, recipient_email, inviter_name=None, dry_run=False, stdout=None):
    if not _email_enabled():
        if stdout:
            stdout.write('Email disabled; skipping invite email.')
        return False
    account, reason = _verified_account_for_email(
        recipient_email,
        stdout=stdout,
    )
    if account is None:
        return False

    base_url = _get_server_url()
    from_email = _get_from_email()
    subject = f'DJ4XOL: Invitation to join {game.name}'
    email_context = {
        'game': game,
        'inviter_name': inviter_name,
        'join_url': _join_game_url(game, base_url),
        'server_url': base_url,
    }
    body = render_to_string('dj4xol/email/game_invite.txt', email_context)

    if dry_run:
        if stdout:
            stdout.write(f'[DRY RUN] Would send invite to {account.email}')
        return False

    _send_account_email(
        subject=subject,
        body_text=body,
        from_email=from_email,
        recipient_email=account.email,
        account=account,
        html_template='dj4xol/email/game_invite.html',
        html_context=email_context,
    )
    return True


def _account_display_name(account):
    if not account:
        return 'unknown'
    alias = getattr(account, 'alias', '') or ''
    if alias:
        return alias
    django_user = getattr(account, 'django_user', None)
    return getattr(django_user, 'username', '') or 'unknown'


def send_game_join_email(game, owner_account, joining_account, via_invitation=False, dry_run=False, stdout=None):
    if not _email_enabled():
        if stdout:
            stdout.write('Email disabled; skipping join email.')
        return False
    allowed, reason = _verified_account_email_allowed(
        owner_account,
        stdout=stdout,
        label='join email',
    )
    if not allowed:
        return False
    if not getattr(owner_account, 'email_game_updates', False):
        return False
    if owner_account == joining_account:
        return False

    base_url = _get_server_url()
    from_email = _get_from_email()
    join_source = 'invitation' if via_invitation else 'public joinability'
    subject = f'DJ4XOL: {_account_display_name(joining_account)} joined {game.name}'
    email_context = {
        'game': game,
        'owner_account': owner_account,
        'joining_account': joining_account,
        'join_source': join_source,
        'game_url': _game_url(game, base_url),
        'server_url': base_url,
        'unsubscribe_url': _unsubscribe_url(owner_account, base_url),
    }
    body = render_to_string('dj4xol/email/game_joined.txt', email_context)

    if dry_run:
        if stdout:
            stdout.write(f'[DRY RUN] Would send join email to {owner_account.email}')
        return False

    try:
        _send_account_email(
            subject=subject,
            body_text=body,
            from_email=from_email,
            recipient_email=owner_account.email,
            account=owner_account,
            html_template='dj4xol/email/game_joined.html',
            html_context=email_context,
        )
    except Exception:
        logger.exception('Failed to send join email for game %s', getattr(game, 'id', None))
        return False
    return True


def send_game_deleted_email(game, owner_account, player_account, dry_run=False, stdout=None):
    if not _email_enabled():
        if stdout:
            stdout.write('Email disabled; skipping game deletion email.')
        return False
    allowed, reason = _verified_account_email_allowed(
        player_account,
        stdout=stdout,
        label='game deletion email',
    )
    if not allowed:
        return False
    if not getattr(player_account, 'email_game_updates', False):
        return False
    if player_account == owner_account:
        return False

    base_url = _get_server_url()
    from_email = _get_from_email()
    subject = f'DJ4XOL: {game.name} was deleted'
    email_context = {
        'game': game,
        'owner_account': owner_account,
        'player_account': player_account,
        'server_url': base_url,
        'unsubscribe_url': _unsubscribe_url(player_account, base_url),
    }
    body = render_to_string('dj4xol/email/game_deleted.txt', email_context)

    if dry_run:
        if stdout:
            stdout.write(f'[DRY RUN] Would send deleted-game email to {player_account.email}')
        return False

    try:
        _send_account_email(
            subject=subject,
            body_text=body,
            from_email=from_email,
            recipient_email=player_account.email,
            account=player_account,
            html_template='dj4xol/email/game_deleted.html',
            html_context=email_context,
        )
    except Exception:
        logger.exception(
            'Failed to send game deletion email for game %s',
            getattr(game, 'id', None),
        )
        return False
    return True


def send_generic_test_email_for_account(account, dry_run=False, stdout=None):
    """Send a plain-text test email to confirm backend delivery works."""
    if not _email_enabled():
        if stdout:
            stdout.write('Email disabled; skipping test email.')
        return False, 'Email disabled'
    allowed, reason = _verified_account_email_allowed(
        account,
        stdout=stdout,
        label='test email',
    )
    if not allowed:
        return False, reason

    base_url = _get_server_url() or 'not configured'
    profile_url = _profile_url(_get_server_url())
    unsubscribe_url = _unsubscribe_url(account, _get_server_url())
    from_email = _get_from_email()
    subject = 'DJ4XOL: Test email'
    alias = getattr(account, 'alias', '') or 'unknown'
    sent_at = timezone.now().isoformat()
    body = (
        'This is a generic DJ4XOL test email.\n\n'
        'It is intended to verify that outbound email delivery works even when '
        'there are no message-rollup updates to send.\n\n'
        'Account: {alias}\n'
        'Email: {email}\n'
        'Server URL: {server_url}\n'
        'Profile URL: {profile_url}\n'
        'Unsubscribe URL: {unsubscribe_url}\n'
        'Sent at: {sent_at}\n'
    ).format(
        alias=alias,
        email=account.email,
        server_url=base_url,
        profile_url=profile_url,
        unsubscribe_url=unsubscribe_url,
        sent_at=sent_at,
    )
    email_context = {
        'account': account,
        'alias': alias,
        'server_url': base_url,
        'profile_url': profile_url,
        'unsubscribe_url': unsubscribe_url,
        'sent_at': sent_at,
    }

    if dry_run:
        if stdout:
            stdout.write(f'[DRY RUN] Would send generic test email to {account.email}')
        return False, 'Dry run'

    _send_account_email(
        subject=subject,
        body_text=body,
        from_email=from_email,
        recipient_email=account.email,
        account=account,
        html_template='dj4xol/email/generic_test.html',
        html_context=email_context,
    )
    if stdout:
        stdout.write(f'Sent generic test email to {account.email}')
    return True, 'Sent'


def send_email_verification_for_account(account, dry_run=False, stdout=None):
    """Send a verification email for a newly registered account."""
    if not _email_enabled():
        if stdout:
            stdout.write('Email disabled; skipping verification email.')
        return False, 'Email disabled'
    if not account or not getattr(account, 'email', ''):
        return False, 'No email address'
    if not getattr(account, 'email_verification_key', ''):
        account.email_verification_key = uuid.uuid4().hex
        account.save(update_fields=['email_verification_key'])

    base_url = _get_server_url()
    from_email = _get_from_email()
    subject = 'DJ4XOL: Verify your email address'
    body = render_to_string('dj4xol/email/verify_email.txt', {
        'account': account,
        'verify_url': _verify_email_url(account, base_url),
        'profile_url': _profile_url(base_url),
        'server_url': base_url,
    })

    if dry_run:
        if stdout:
            stdout.write(
                f'[DRY RUN] Would send verification email to {account.email}'
            )
        return False, 'Dry run'

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[account.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            'Failed to send verification email for account %s',
            getattr(account, 'pk', None),
        )
        return False, 'Send failure'
    return True, 'Sent'


def _build_rollup_entries(account, base_url):
    entries = []
    total_messages = 0
    any_new_turn = False

    players = list(
        account.players.select_related('game').filter(game__ended=False)
    )
    if not players:
        return entries, total_messages, any_new_turn, players

    last_logs = {}
    for log in EmailRollupLog.objects.filter(player__in=players).order_by('-sent_at'):
        if log.player_id not in last_logs:
            last_logs[log.player_id] = log

    new_turn_by_player = {}
    for player in players:
        last_log = last_logs.get(player.id)
        last_year = last_log.year if last_log else None
        has_new_turn = (last_year is None) or (player.game.year > int(last_year))
        new_turn_by_player[player.id] = has_new_turn
        if has_new_turn:
            any_new_turn = True

    for player in players:
        alert_messages = [
            {
                'year': entry['year'],
                'priority': True,
                'text': entry['text'],
            }
            for entry in build_incoming_contract_alert_entries(player)
        ]
        qs = player.messages.filter(
            models.Q(priority=True) | models.Q(category__in=ROLLUP_CATEGORIES)
        ).order_by('-priority', '-year', '-id')
        if player.last_seen_year is not None:
            qs = qs.filter(year__gt=player.last_seen_year)
        messages = list(qs)
        if not messages and not alert_messages:
            continue

        entry_messages = alert_messages + [
            {
                'year': msg.year,
                'priority': bool(msg.priority),
                'text': strip_tags(msg.message or ''),
            }
            for msg in messages
        ]
        entries.append({
            'player': player,
            'game': player.game,
            'game_url': _game_url(player.game, base_url),
            'has_new_turn': new_turn_by_player.get(player.id, False),
            'messages': entry_messages,
        })
        total_messages += len(entry_messages)

    entries.sort(key=lambda item: (
        not item['has_new_turn'],
        item['game'].name.lower(),
    ))

    return entries, total_messages, any_new_turn, players


def _send_rollup_email(account, entries, total_messages, players, dry_run, stdout):
    base_url = _get_server_url()
    from_email = _get_from_email()
    subject = 'DJ4XOL: Priority message rollup'
    email_context = {
        'account': account,
        'games': entries,
        'profile_url': _profile_url(base_url),
        'unsubscribe_url': _unsubscribe_url(account, base_url),
    }
    body = render_to_string('dj4xol/email/message_rollup.txt', email_context)

    if dry_run:
        if stdout:
            stdout.write(
                f'[DRY RUN] Would send rollup to {account.email} '
                f'({len(entries)} game(s), {total_messages} message(s))'
            )
        return False

    _send_account_email(
        subject=subject,
        body_text=body,
        from_email=from_email,
        recipient_email=account.email,
        account=account,
        html_template='dj4xol/email/message_rollup.html',
        html_context=email_context,
    )

    message_counts = {entry['player'].id: len(entry['messages']) for entry in entries}
    for player in players:
        EmailRollupLog.objects.create(
            account=account,
            player=player,
            game=player.game,
            year=int(player.game.year),
            message_count=message_counts.get(player.id, 0),
        )
    if stdout:
        stdout.write(
            f'Sent rollup to {account.email} '
            f'({len(entries)} game(s), {total_messages} message(s))'
        )
    return True


def send_message_rollup_for_account(account, ignore_frequency=False, dry_run=False, stdout=None):
    if not _email_enabled():
        if stdout:
            stdout.write('Email disabled; skipping rollups.')
        return False, 'Email disabled'
    allowed, reason = _verified_account_email_allowed(
        account,
        stdout=stdout,
        label='rollups',
    )
    if not allowed:
        return False, reason
    if not account.email_game_updates:
        return False, 'Email updates disabled'

    rollups_per_day = int(account.email_game_rollups_per_day or 0)
    if rollups_per_day <= 0:
        return False, 'Rollups disabled'

    if not ignore_frequency:
        last_sent = (
            EmailRollupLog.objects
            .filter(account=account)
            .order_by('-sent_at')
            .first()
        )
        if last_sent:
            interval = timedelta(seconds=86400.0 / float(rollups_per_day))
            if last_sent.sent_at + interval > timezone.now():
                return False, 'Rollup interval not reached'

    base_url = _get_server_url()
    entries, total_messages, any_new_turn, players = _build_rollup_entries(
        account, base_url
    )
    if total_messages <= 0:
        return False, 'No new messages'
    if not any_new_turn:
        return False, 'No new turns'

    try:
        _send_rollup_email(account, entries, total_messages, players, dry_run, stdout)
    except Exception as exc:
        logger.exception('Failed sending rollup to %s: %s', account.email, exc)
        if stdout:
            stdout.write(f'Failed rollup for {account.email}: {exc}')
        return False, str(exc)

    return True, 'Sent'


def send_message_rollups(dry_run=False, stdout=None):
    if not _email_enabled():
        if stdout:
            stdout.write('Email disabled; skipping rollups.')
        return 0

    now = timezone.now()
    sent = 0

    accounts = (
        Account.objects
        .filter(email_game_updates=True, email_verified=True)
        .exclude(email='')
        .prefetch_related('players__game')
    )

    for account in accounts:
        rollups_per_day = int(account.email_game_rollups_per_day or 0)
        if rollups_per_day <= 0:
            continue
        last_sent = (
            EmailRollupLog.objects
            .filter(account=account)
            .order_by('-sent_at')
            .first()
        )
        if last_sent:
            interval = timedelta(seconds=86400.0 / float(rollups_per_day))
            if last_sent.sent_at + interval > now:
                continue

        base_url = _get_server_url()
        entries, total_messages, any_new_turn, players = _build_rollup_entries(
            account, base_url
        )
        if total_messages <= 0:
            continue
        if not any_new_turn:
            continue

        try:
            _send_rollup_email(account, entries, total_messages, players, dry_run, stdout)
        except Exception as exc:
            logger.exception('Failed sending rollup to %s: %s', account.email, exc)
            if stdout:
                stdout.write(f'Failed rollup for {account.email}: {exc}')
            continue

        sent += 1

    return sent
