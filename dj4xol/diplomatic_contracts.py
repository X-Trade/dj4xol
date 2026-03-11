from __future__ import unicode_literals

from datetime import timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from .models import DiplomaticContract, GameMessage, PlayerDiplomaticStance, PlayerTechnologyGrant
from .secret_resources import SECRET_RESOURCE_KEYS, get_secret_resource_label


REQUEST_RESOURCE_CLAUSE_TYPES = (
    DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
    DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
)
IMMEDIATE_CLAUSE_TYPES = (
    DiplomaticContract.CLAUSE_NOTHING,
    DiplomaticContract.CLAUSE_TECHNOLOGY,
    DiplomaticContract.CLAUSE_STANCE,
)
HANDLED_CONTRACT_STATUSES = (
    DiplomaticContract.STATUS_ACCEPTED,
    DiplomaticContract.STATUS_FULFILLED,
    DiplomaticContract.STATUS_DECLINED,
    DiplomaticContract.STATUS_COUNTERED,
    DiplomaticContract.STATUS_EXPIRED,
    DiplomaticContract.STATUS_REVOKED,
)


def _format_readable_list(items):
    items = [item for item in items if item]
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return '%s and %s' % (items[0], items[1])
    return '%s, and %s' % (', '.join(items[:-1]), items[-1])


def _temperature_verb(temperature, subject_is_we=False):
    verb = str(temperature or '').lower() or 'propose'
    if subject_is_we:
        return verb
    if verb.endswith('s'):
        return verb
    return '%ss' % verb


def player_display_name(player, include_account=True):
    if not player:
        return 'Unknown race'
    if not include_account:
        return getattr(player, 'name', None) or 'Unknown race'
    alias = getattr(getattr(player, 'account', None), 'alias', None) or 'Unknown'
    return '%s (%s)' % (player.name, alias)


def diplomatic_actions_locked(player):
    if not player:
        return True, 'No player.'
    if bool(getattr(player, 'turned_in', False)):
        return True, 'You have already turned in.'
    game = getattr(player, 'game', None)
    next_generation = getattr(game, 'next_generation', None) if game else None
    if next_generation is not None and next_generation <= timezone.now() + timedelta(minutes=1):
        return True, 'Diplomacy is locked when the next turn is due in under one minute.'
    return False, ''


def _player_knows_secret_resource(player, resource_key):
    return bool(getattr(player, 'discovered_%s' % resource_key, False))


def resource_label_for_player(player, resource_key):
    if resource_key in SECRET_RESOURCE_KEYS:
        return get_secret_resource_label(resource_key, _player_knows_secret_resource(player, resource_key))
    if resource_key == 'ironium':
        return 'Ironium'
    if resource_key == 'boranium':
        return 'Boranium'
    if resource_key == 'germanium':
        return 'Germanium'
    if resource_key == 'colonists':
        return 'Colonists'
    return str(resource_key).title()


def format_resource_quantity_for_player(player, resource_key, quantity):
    quantity = int(quantity or 0)
    if quantity <= 0:
        return ''
    unit = 'kt'
    if resource_key == 'colonists':
        unit = 'kt'
    return '%s%s %s' % (quantity, unit, resource_label_for_player(player, resource_key))


def contract_resource_bundle(contract):
    return {
        'ironium': int(getattr(contract, 'request_ironium', 0) or 0),
        'boranium': int(getattr(contract, 'request_boranium', 0) or 0),
        'germanium': int(getattr(contract, 'request_germanium', 0) or 0),
        'resource_x': int(getattr(contract, 'request_resource_x', 0) or 0),
        'resource_y': int(getattr(contract, 'request_resource_y', 0) or 0),
        'resource_z': int(getattr(contract, 'request_resource_z', 0) or 0),
        'colonists': int(getattr(contract, 'request_colonists', 0) or 0),
    }


def contract_resource_progress(contract):
    return {
        'ironium': int(getattr(contract, 'progress_ironium', 0) or 0),
        'boranium': int(getattr(contract, 'progress_boranium', 0) or 0),
        'germanium': int(getattr(contract, 'progress_germanium', 0) or 0),
        'resource_x': int(getattr(contract, 'progress_resource_x', 0) or 0),
        'resource_y': int(getattr(contract, 'progress_resource_y', 0) or 0),
        'resource_z': int(getattr(contract, 'progress_resource_z', 0) or 0),
        'colonists': int(getattr(contract, 'progress_colonists', 0) or 0),
    }


def format_contract_clause(contract, prefix, viewer=None, include_links=True):
    clause_type = getattr(contract, '%s_clause_type' % prefix)
    viewer = viewer or contract.sender
    if clause_type == DiplomaticContract.CLAUSE_NOTHING:
        return 'do nothing' if prefix == 'request' else 'nothing'
    if clause_type == DiplomaticContract.CLAUSE_TECHNOLOGY:
        tech = getattr(contract, '%s_technology' % prefix)
        return 'technology %s' % (getattr(tech, 'name', 'Unknown technology'))
    if clause_type == DiplomaticContract.CLAUSE_STANCE:
        stance = getattr(contract, '%s_stance' % prefix)
        return '%s stance' % (str(stance or '').title() or 'Neutral')
    if clause_type in REQUEST_RESOURCE_CLAUSE_TYPES:
        parts = []
        for resource_key, quantity in contract_resource_bundle(contract).items():
            label = format_resource_quantity_for_player(viewer, resource_key, quantity)
            if label:
                parts.append(label)
        bundle = _format_readable_list(parts) or 'supplies'
        if clause_type == DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD:
            suggested = getattr(contract, 'request_suggested_star', None)
            if suggested is not None:
                return '%s to any owned world (suggested: %s)' % (
                    bundle,
                    escape(getattr(suggested, 'name', 'Unknown')),
                )
            return '%s to any owned world' % bundle
        return '%s on a transferred fleet' % bundle
    if clause_type == DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT:
        ship_count = int(getattr(contract, '%s_ship_count' % prefix, 0) or 0)
        return 'a fleet totaling %s ships' % ship_count
    if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
        fleet = getattr(contract, '%s_fleet' % prefix)
        if fleet is None:
            return 'the promised fleet'
        label = escape(getattr(fleet, 'name', 'Unknown Fleet'))
        if include_links:
            base = reverse('dj4xol:game', args=[contract.game.short_id])
            return '<a href="%s?sel=%s">%s</a>' % (base, fleet.short_id, label)
        return label
    return clause_type


def format_contract_clause_as_form_phrase(contract, prefix, viewer=None, include_links=True, sender_is_viewer=False):
    clause_type = getattr(contract, '%s_clause_type' % prefix)
    viewer = viewer or contract.sender
    if prefix == 'request':
        if clause_type == DiplomaticContract.CLAUSE_NOTHING:
            return 'do nothing'
        if clause_type == DiplomaticContract.CLAUSE_TECHNOLOGY:
            tech = getattr(contract, '%s_technology' % prefix)
            object_pronoun = 'us' if sender_is_viewer else 'them'
            return 'grant %s technology %s' % (object_pronoun, getattr(tech, 'name', 'Unknown technology'))
        if clause_type == DiplomaticContract.CLAUSE_STANCE:
            stance = str(getattr(contract, '%s_stance' % prefix) or '').lower() or 'neutral'
            possessive = 'their' if sender_is_viewer else 'our'
            return 'set %s stance to %s' % (possessive, stance)
        if clause_type == DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD:
            base = format_contract_clause(contract, prefix, viewer=viewer, include_links=include_links)
            return 'deliver %s' % base
        if clause_type == DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET:
            bundle = format_contract_clause(contract, prefix, viewer=viewer, include_links=include_links)
            if bundle.endswith(' on a transferred fleet'):
                bundle = bundle[:-22]
            object_pronoun = 'us' if sender_is_viewer else 'them'
            return 'give %s a fleet carrying %s' % (object_pronoun, bundle)
        if clause_type == DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT:
            ship_count = int(getattr(contract, '%s_ship_count' % prefix, 0) or 0)
            object_pronoun = 'us' if sender_is_viewer else 'them'
            return 'give %s a fleet of %s ships' % (object_pronoun, ship_count)
    if prefix == 'offer':
        if clause_type == DiplomaticContract.CLAUSE_NOTHING:
            return 'do nothing'
        if clause_type == DiplomaticContract.CLAUSE_TECHNOLOGY:
            tech = getattr(contract, '%s_technology' % prefix)
            object_pronoun = 'them' if sender_is_viewer else 'us'
            return 'grant %s technology %s' % (object_pronoun, getattr(tech, 'name', 'Unknown technology'))
        if clause_type == DiplomaticContract.CLAUSE_STANCE:
            stance = str(getattr(contract, '%s_stance' % prefix) or '').lower() or 'neutral'
            possessive = 'our' if sender_is_viewer else 'their'
            return 'set %s stance to %s' % (possessive, stance)
        if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
            fleet = getattr(contract, '%s_fleet' % prefix)
            if fleet is None:
                object_pronoun = 'them' if sender_is_viewer else 'us'
                return 'give %s the promised fleet' % object_pronoun
            label = escape(getattr(fleet, 'name', 'Unknown Fleet'))
            if include_links:
                base = reverse('dj4xol:game', args=[contract.game.short_id])
                label = '<a href="%s?sel=%s">%s</a>' % (base, fleet.short_id, label)
            object_pronoun = 'them' if sender_is_viewer else 'us'
            return 'give %s %s' % (object_pronoun, label)
    return format_contract_clause(contract, prefix, viewer=viewer, include_links=include_links)


def format_contract_summary(contract, viewer=None, include_links=True, include_sender_account=True):
    viewer = viewer or contract.recipient
    request_text = format_contract_clause(contract, 'request', viewer=viewer, include_links=include_links)
    offer_text = format_contract_clause(contract, 'offer', viewer=viewer, include_links=include_links)
    sender_label = escape(player_display_name(contract.sender, include_account=include_sender_account))
    sender_is_viewer = getattr(contract.sender, 'id', None) == getattr(viewer, 'id', None)
    joiner = (
        'or else'
        if contract.offer_condition_type == DiplomaticContract.CONDITION_OR_ELSE
        else 'in exchange for'
    )
    return '%s %s %s %s %s.' % (
        sender_label,
        _temperature_verb(contract.temperature, subject_is_we=sender_is_viewer),
        request_text,
        joiner,
        offer_text,
    )


def format_contract_statement(contract, viewer=None, include_links=True, include_sender_account=True, emphasize_actions=False):
    viewer = viewer or contract.recipient
    sender_is_viewer = getattr(contract.sender, 'id', None) == getattr(viewer, 'id', None)
    request_text = format_contract_clause_as_form_phrase(
        contract,
        'request',
        viewer=viewer,
        include_links=include_links,
        sender_is_viewer=sender_is_viewer,
    )
    offer_text = format_contract_clause_as_form_phrase(
        contract,
        'offer',
        viewer=viewer,
        include_links=include_links,
        sender_is_viewer=sender_is_viewer,
    )
    if emphasize_actions:
        request_text = '<em>%s</em>' % request_text
        offer_text = '<em>%s</em>' % offer_text
    first_subject = 'We' if sender_is_viewer else escape(player_display_name(contract.sender, include_account=include_sender_account))
    request_subject = (
        escape(player_display_name(contract.recipient, include_account=include_sender_account))
        if sender_is_viewer else
        'we'
    )
    second_subject = 'we' if sender_is_viewer else 'they'
    joiner = (
        'or else'
        if contract.offer_condition_type == DiplomaticContract.CONDITION_OR_ELSE
        else 'in exchange'
    )
    return '%s %s that %s %s, %s %s %s.' % (
        first_subject,
        _temperature_verb(contract.temperature, subject_is_we=sender_is_viewer),
        request_subject,
        request_text,
        joiner,
        second_subject,
        offer_text,
    )


def contract_link(contract, label, target_short_id=None):
    base = reverse('dj4xol:diplomacy', args=[contract.game.short_id])
    target = target_short_id or getattr(contract.sender, 'short_id', '')
    return '<a href="%s?target=%s&contract=%s">%s</a>' % (
        base,
        target,
        contract.short_id,
        escape(label),
    )


def build_incoming_contract_alert_entries(player):
    if not player:
        return []
    contracts = list(
        DiplomaticContract.objects.filter(
            recipient=player,
            status=DiplomaticContract.STATUS_SENT,
        ).select_related(
            'sender',
            'sender__account',
            'request_technology',
            'offer_technology',
            'offer_fleet',
            'request_suggested_star',
        ).order_by('expires_year', 'created_at')
    )
    entries = []
    for contract in contracts:
        if contract.offer_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
            ensure_specific_fleet_report(contract)
        message = '%s Expires Year %s.' % (
            format_contract_summary(
                contract,
                viewer=player,
                include_links=True,
                include_sender_account=False,
            ),
            int(contract.expires_year or 0),
        )
        entries.append({
            'short_id': 'contract-%s' % contract.short_id,
            'year': int(contract.sent_year or contract.game.year or 0),
            'category': 'DIPLOMATIC',
            'priority': True,
            'diplomatic_priority': True,
            'message': '%s %s' % (
                message,
                contract_link(contract, 'Respond', target_short_id=getattr(contract.sender, 'short_id', '')),
            ),
            'text': 'Diplomatic request: %s Expires Year %s.' % (
                format_contract_summary(
                    contract,
                    viewer=player,
                    include_links=False,
                    include_sender_account=False,
                ),
                int(contract.expires_year or 0),
            ),
        })
    return entries


def build_unfulfilled_contract_alert_entries(player):
    if not player:
        return []
    contracts = list(
        DiplomaticContract.objects.filter(
            game=player.game,
            status=DiplomaticContract.STATUS_ACCEPTED,
            sender__in=[player],
        ).select_related(
            'sender',
            'sender__account',
            'recipient',
            'recipient__account',
            'request_technology',
            'offer_technology',
            'offer_fleet',
            'request_suggested_star',
        ).order_by('-accepted_year', '-created_at')
    ) + list(
        DiplomaticContract.objects.filter(
            game=player.game,
            status=DiplomaticContract.STATUS_ACCEPTED,
            recipient__in=[player],
        ).select_related(
            'sender',
            'sender__account',
            'recipient',
            'recipient__account',
            'request_technology',
            'offer_technology',
            'offer_fleet',
            'request_suggested_star',
        ).order_by('-accepted_year', '-created_at')
    )
    seen = set()
    entries = []
    for contract in contracts:
        if contract.id in seen:
            continue
        seen.add(contract.id)
        request_text = format_contract_clause(
            contract,
            'request',
            viewer=player,
            include_links=False,
        )
        if contract.sender_id == player.id:
            text = 'Awaiting from %s: %s. Complete by Year %s.' % (
                player_display_name(contract.recipient, include_account=False),
                request_text,
                int(contract.expires_year or contract.game.year or 0),
            )
        else:
            text = 'You owe %s: %s. Complete by Year %s.' % (
                player_display_name(contract.sender, include_account=False),
                request_text,
                int(contract.expires_year or contract.game.year or 0),
            )
        entries.append({
            'short_id': 'active-contract-%s' % contract.short_id,
            'year': int(contract.accepted_year or contract.game.year or 0),
            'category': 'DIPLOMATIC',
            'priority': True,
            'diplomatic_priority': True,
            'message': '%s %s' % (
                text,
                contract_link(
                    contract,
                    'View',
                    target_short_id=getattr(contract.sender, 'short_id', ''),
                ),
            ),
            'text': text,
        })
    return entries


def build_player_message_feed(player, limit=1000, include_seen_filter=True):
    if not player:
        return []
    alerts = build_incoming_contract_alert_entries(player) + build_unfulfilled_contract_alert_entries(player)
    messages_qs = player.messages.order_by('-priority', '-year', '-id')
    if include_seen_filter and player.messages_seen_year is not None:
        messages_qs = messages_qs.filter(year__gte=player.messages_seen_year)
    messages = [{
        'short_id': msg.short_id,
        'year': msg.year,
        'category': msg.category,
        'priority': bool(msg.priority),
        'diplomatic_priority': False,
        'message': msg.message,
        'text': str(msg.message or ''),
    } for msg in messages_qs[:limit]]
    feed = alerts + messages
    return feed[:limit]


def _create_contract_status_message(player, contract, text, priority=False):
    if not player:
        return
    msg = GameMessage.objects.create(
        game=contract.game,
        player=player,
        year=contract.game.year,
        category='DIPLOMATIC',
        priority=priority,
        message=text,
    )
    return msg


def grant_player_technology(player, technology, source_contract=None, granted_by_player=None, year=None):
    if not player or technology is None:
        return None
    if year is None:
        if source_contract is not None and getattr(source_contract, 'game', None) is not None:
            year = source_contract.game.year
        else:
            year = 0
    defaults = {
        'source_contract': source_contract,
        'granted_by_player': granted_by_player,
        'granted_year': int(year or 0),
    }
    grant, _created = PlayerTechnologyGrant.objects.get_or_create(
        player=player,
        technology=technology,
        defaults=defaults,
    )
    return grant


def _set_pending_stance(source_player, target_player, stance):
    if not source_player or not target_player:
        return
    stance = str(stance or '').upper()
    row, _created = PlayerDiplomaticStance.objects.get_or_create(
        player=source_player,
        target_player=target_player,
        defaults={'stance': stance, 'pending_stance': stance},
    )
    if row.pending_stance != stance:
        row.pending_stance = stance
        row.save(update_fields=['pending_stance'])


def _player_currently_has_technology(player, technology):
    if not player or technology is None:
        return False
    from .research import get_player_unlocked_technologies

    unlocked_ids = {tech.id for tech in get_player_unlocked_technologies(player)}
    return technology.id in unlocked_ids


def _apply_clause_immediately(contract, prefix, year):
    clause_type = getattr(contract, '%s_clause_type' % prefix)
    if clause_type not in IMMEDIATE_CLAUSE_TYPES + (DiplomaticContract.CLAUSE_SPECIFIC_FLEET,):
        return False
    if prefix == 'request':
        grant_source = contract.recipient
        grant_target = contract.sender
    else:
        grant_source = contract.sender
        grant_target = contract.recipient

    if clause_type == DiplomaticContract.CLAUSE_NOTHING:
        return True
    if clause_type == DiplomaticContract.CLAUSE_TECHNOLOGY:
        technology = getattr(contract, '%s_technology' % prefix)
        if not _player_currently_has_technology(grant_source, technology):
            return False
        grant_player_technology(
            grant_target,
            technology,
            source_contract=contract,
            granted_by_player=grant_source,
            year=year,
        )
        return True
    if clause_type == DiplomaticContract.CLAUSE_STANCE:
        stance = getattr(contract, '%s_stance' % prefix)
        _set_pending_stance(grant_source, grant_target, stance)
        return True
    if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
        fleet = getattr(contract, '%s_fleet' % prefix)
        if fleet is None or fleet.game_id != contract.game_id or fleet.player_id != grant_source.id:
            return False
        fleet.orders.all().delete()
        fleet.player = grant_target
        fleet.save(update_fields=['player'])
        return True
    return False


def _resource_progress_complete(contract):
    bundle = contract_resource_bundle(contract)
    progress = contract_resource_progress(contract)
    for key, required in bundle.items():
        if int(required or 0) > int(progress.get(key, 0) or 0):
            return False
    return True


def contract_request_complete(contract):
    clause_type = contract.request_clause_type
    if clause_type in REQUEST_RESOURCE_CLAUSE_TYPES:
        return _resource_progress_complete(contract)
    if clause_type == DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT:
        return int(contract.progress_ship_count or 0) >= int(contract.request_ship_count or 0)
    if clause_type in IMMEDIATE_CLAUSE_TYPES:
        return contract.status == DiplomaticContract.STATUS_FULFILLED
    return False


def _mark_contract_fulfilled(contract, year):
    contract.status = DiplomaticContract.STATUS_FULFILLED
    contract.fulfilled_year = year
    contract.handled_year = year
    contract.save(update_fields=['status', 'fulfilled_year', 'handled_year', 'updated_at'])
    summary = format_contract_summary(
        contract,
        viewer=contract.sender,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(
        contract.sender,
        contract,
        'Diplomatic request fulfilled: %s' % summary,
    )
    _create_contract_status_message(
        contract.recipient,
        contract,
        'Diplomatic request fulfilled: %s' % summary,
    )


def _apply_condition_consequence(contract):
    if contract.offer_condition_type != DiplomaticContract.CONDITION_OR_ELSE:
        return
    if contract.offer_clause_type == DiplomaticContract.CLAUSE_STANCE:
        _set_pending_stance(contract.sender, contract.recipient, contract.offer_stance)
        return
    _apply_clause_immediately(contract, 'offer', contract.game.year)


def _expire_contract(contract, year, apply_consequence=False):
    if contract.status in HANDLED_CONTRACT_STATUSES:
        return
    contract.status = DiplomaticContract.STATUS_EXPIRED
    contract.handled_year = year
    contract.save(update_fields=['status', 'handled_year', 'updated_at'])
    if apply_consequence:
        _apply_condition_consequence(contract)
    summary = format_contract_summary(
        contract,
        viewer=contract.sender,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(
        contract.sender,
        contract,
        'Diplomatic request expired: %s' % summary,
        priority=(contract.offer_condition_type == DiplomaticContract.CONDITION_OR_ELSE),
    )
    _create_contract_status_message(
        contract.recipient,
        contract,
        'Diplomatic request expired: %s' % summary,
        priority=(contract.offer_condition_type == DiplomaticContract.CONDITION_OR_ELSE),
    )


def ensure_specific_fleet_report(contract):
    if contract.offer_clause_type != DiplomaticContract.CLAUSE_SPECIFIC_FLEET or contract.offer_fleet is None:
        return
    from .turn import GameTurn

    turn = GameTurn(contract.game)
    turn._create_or_update_report(
        contract.recipient,
        'fleet',
        contract.offer_fleet,
        contract.game.year,
        report_tier='encounter',
        include_cargo=True,
    )


def refresh_contract_integrity(game):
    if not game:
        return
    contracts = DiplomaticContract.objects.filter(
        game=game,
        status__in=[DiplomaticContract.STATUS_SENT, DiplomaticContract.STATUS_ACCEPTED],
        offer_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_FLEET,
    ).select_related('offer_fleet', 'sender', 'recipient')
    for contract in contracts:
        fleet = contract.offer_fleet
        if fleet is None or fleet.game_id != game.id or fleet.player_id != contract.sender_id:
            _expire_contract(contract, game.year, apply_consequence=False)

    expirable = DiplomaticContract.objects.filter(
        game=game,
        status__in=[DiplomaticContract.STATUS_SENT, DiplomaticContract.STATUS_ACCEPTED],
    ).select_related('sender', 'recipient')
    for contract in expirable:
        if int(game.year or 0) > int(contract.expires_year or 0):
            _expire_contract(contract, game.year, apply_consequence=True)


@transaction.atomic
def accept_contract(contract, acting_player):
    if not contract or not acting_player or contract.recipient_id != acting_player.id:
        return False, 'Request not found.'
    if contract.status != DiplomaticContract.STATUS_SENT:
        return False, 'Request is no longer awaiting a response.'
    locked, reason = diplomatic_actions_locked(acting_player)
    if locked:
        return False, reason

    contract.status = DiplomaticContract.STATUS_ACCEPTED
    contract.accepted_year = contract.game.year
    if int(contract.extend_on_accept_years or 0) > 0:
        contract.expires_year = int(contract.expires_year or 0) + int(contract.extend_on_accept_years or 0)
    contract.save(update_fields=['status', 'accepted_year', 'expires_year', 'updated_at'])

    summary = format_contract_summary(
        contract,
        viewer=acting_player,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(contract.sender, contract, 'Diplomatic request accepted: %s' % summary)
    _create_contract_status_message(contract.recipient, contract, 'Diplomatic request accepted: %s' % summary)

    if contract.request_clause_type in IMMEDIATE_CLAUSE_TYPES:
        if not _apply_clause_immediately(contract, 'request', contract.game.year):
            _expire_contract(contract, contract.game.year, apply_consequence=True)
            return False, 'Request could not be completed because the requested clause is no longer available.'
        if (
            contract.offer_condition_type == DiplomaticContract.CONDITION_EXCHANGE and
            not _apply_clause_immediately(contract, 'offer', contract.game.year)
        ):
            _expire_contract(contract, contract.game.year, apply_consequence=False)
            return False, 'Request could not be completed because the offered clause is no longer available.'
        _mark_contract_fulfilled(contract, contract.game.year)
        return True, 'Request accepted and fulfilled.'

    return True, 'Request accepted.'


@transaction.atomic
def decline_contract(contract, acting_player):
    if not contract or not acting_player or contract.recipient_id != acting_player.id:
        return False, 'Request not found.'
    if contract.status != DiplomaticContract.STATUS_SENT:
        return False, 'Request is no longer awaiting a response.'
    locked, reason = diplomatic_actions_locked(acting_player)
    if locked:
        return False, reason
    contract.status = DiplomaticContract.STATUS_DECLINED
    contract.handled_year = contract.game.year
    contract.save(update_fields=['status', 'handled_year', 'updated_at'])
    _apply_condition_consequence(contract)
    summary = format_contract_summary(
        contract,
        viewer=acting_player,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(contract.sender, contract, 'Diplomatic request declined: %s' % summary, priority=(contract.offer_condition_type == DiplomaticContract.CONDITION_OR_ELSE))
    _create_contract_status_message(contract.recipient, contract, 'Diplomatic request declined: %s' % summary, priority=(contract.offer_condition_type == DiplomaticContract.CONDITION_OR_ELSE))
    return True, 'Request declined.'


@transaction.atomic
def revoke_contract(contract, acting_player):
    if not contract or not acting_player or contract.sender_id != acting_player.id:
        return False, 'Request not found.'
    if contract.status != DiplomaticContract.STATUS_SENT:
        return False, 'Only unanswered requests can be revoked.'
    locked, reason = diplomatic_actions_locked(acting_player)
    if locked:
        return False, reason
    contract.status = DiplomaticContract.STATUS_REVOKED
    contract.handled_year = contract.game.year
    contract.save(update_fields=['status', 'handled_year', 'updated_at'])
    summary = format_contract_summary(
        contract,
        viewer=acting_player,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(contract.sender, contract, 'Diplomatic request revoked: %s' % summary)
    _create_contract_status_message(contract.recipient, contract, 'Diplomatic request revoked: %s' % summary)
    return True, 'Request revoked.'


def mark_countered(original_contract, new_contract):
    if original_contract is None or new_contract is None:
        return
    original_contract.status = DiplomaticContract.STATUS_COUNTERED
    original_contract.handled_year = original_contract.game.year
    original_contract.save(update_fields=['status', 'handled_year', 'updated_at'])
    summary = format_contract_summary(
        original_contract,
        viewer=original_contract.sender,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(
        original_contract.sender,
        original_contract,
        'Diplomatic request countered: %s' % summary,
    )
    _create_contract_status_message(
        original_contract.recipient,
        original_contract,
        'Diplomatic request countered: %s' % summary,
    )


def _apply_offer_on_completion(contract, year):
    if contract.offer_condition_type == DiplomaticContract.CONDITION_OR_ELSE:
        return True
    if contract.offer_clause_type == DiplomaticContract.CLAUSE_NOTHING:
        return True
    return _apply_clause_immediately(contract, 'offer', year)


def _maybe_complete_contract(contract, year):
    if not contract_request_complete(contract):
        return False
    if not _apply_offer_on_completion(contract, year):
        _expire_contract(contract, year, apply_consequence=False)
        return False
    _mark_contract_fulfilled(contract, year)
    return True


def _allocate_resource_progress(contract, available):
    changed_fields = []
    for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z', 'colonists'):
        required = int(getattr(contract, 'request_%s' % key, 0) or 0)
        if required <= 0:
            continue
        current = int(getattr(contract, 'progress_%s' % key, 0) or 0)
        if current >= required:
            continue
        amount = min(int(available.get(key, 0) or 0), required - current)
        if amount <= 0:
            continue
        setattr(contract, 'progress_%s' % key, current + amount)
        available[key] = int(available.get(key, 0) or 0) - amount
        changed_fields.append('progress_%s' % key)
    if changed_fields:
        contract.save(update_fields=changed_fields + ['updated_at'])
    return available


def apply_world_resource_delivery(provider_player, receiving_player, bundle, year, star=None):
    if not provider_player or not receiving_player or provider_player.id == receiving_player.id:
        return
    available = {key: int(bundle.get(key, 0) or 0) for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z', 'colonists')}
    contracts = DiplomaticContract.objects.filter(
        game=provider_player.game,
        sender=receiving_player,
        recipient=provider_player,
        status=DiplomaticContract.STATUS_ACCEPTED,
        request_clause_type=DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
    ).order_by('accepted_year', 'created_at')
    for contract in contracts:
        if not any(int(available.get(key, 0) or 0) > 0 for key in available):
            break
        available = _allocate_resource_progress(contract, available)
        _maybe_complete_contract(contract, year)


def apply_give_fleet_delivery(provider_player, receiving_player, fleet, cargo_bundle, ship_count, year):
    if not provider_player or not receiving_player or provider_player.id == receiving_player.id:
        return
    available_resources = {
        key: int(cargo_bundle.get(key, 0) or 0)
        for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z', 'colonists')
    }
    ships_remaining = int(ship_count or 0)
    contracts = DiplomaticContract.objects.filter(
        game=provider_player.game,
        sender=receiving_player,
        recipient=provider_player,
        status=DiplomaticContract.STATUS_ACCEPTED,
        request_clause_type__in=[
            DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
            DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT,
        ],
    ).order_by('accepted_year', 'created_at')
    for contract in contracts:
        if contract.request_clause_type == DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET:
            available_resources = _allocate_resource_progress(contract, available_resources)
            _maybe_complete_contract(contract, year)
            continue
        if contract.request_clause_type == DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT:
            required = max(0, int(contract.request_ship_count or 0) - int(contract.progress_ship_count or 0))
            if required <= 0:
                _maybe_complete_contract(contract, year)
                continue
            allocated = min(required, ships_remaining)
            if allocated > 0:
                contract.progress_ship_count = int(contract.progress_ship_count or 0) + allocated
                contract.save(update_fields=['progress_ship_count', 'updated_at'])
                ships_remaining -= allocated
                _maybe_complete_contract(contract, year)
            if ships_remaining <= 0 and not any(int(available_resources.get(key, 0) or 0) > 0 for key in available_resources):
                break


def pair_contracts(player, other_player):
    if not player or not other_player:
        return []
    return list(
        DiplomaticContract.objects.filter(
            game=player.game,
            sender__in=[player, other_player],
            recipient__in=[player, other_player],
        ).select_related(
            'sender',
            'sender__account',
            'recipient',
            'recipient__account',
            'request_technology',
            'offer_technology',
            'offer_fleet',
            'request_suggested_star',
        ).order_by('-created_at')
    )
