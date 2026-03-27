from __future__ import unicode_literals

from .ai_players import ai_module_uses_micromanager_behavior

from datetime import timedelta
import hashlib
import random

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from .map_object_rules import format_map_link
from .models import DiplomaticContract, GameMessage, PlayerDiplomaticStance, PlayerTechnologyGrant, Report
from .player_labels import player_bracket_label
from .secret_resources import SECRET_RESOURCE_KEYS, get_secret_resource_label


REQUEST_RESOURCE_CLAUSE_TYPES = (
    DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
    DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
)
IMMEDIATE_CLAUSE_TYPES = (
    DiplomaticContract.CLAUSE_NOTHING,
    DiplomaticContract.CLAUSE_TECHNOLOGY,
    DiplomaticContract.CLAUSE_STANCE,
    DiplomaticContract.CLAUSE_REPORT,
    DiplomaticContract.CLAUSE_VAGUE_THREAT,
)
APPLY_ON_ACCEPT_CLAUSE_TYPES = IMMEDIATE_CLAUSE_TYPES + (
    DiplomaticContract.CLAUSE_SPECIFIC_FLEET,
    DiplomaticContract.CLAUSE_SPECIFIC_COLONY,
)
HANDLED_CONTRACT_STATUSES = (
    DiplomaticContract.STATUS_ACCEPTED,
    DiplomaticContract.STATUS_FULFILLED,
    DiplomaticContract.STATUS_DECLINED,
    DiplomaticContract.STATUS_COUNTERED,
    DiplomaticContract.STATUS_EXPIRED,
    DiplomaticContract.STATUS_REVOKED,
)

REPORT_TIER_ORDER = {
    'ownership': 0,
    'basic': 1,
    'advanced': 2,
    'encounter': 3,
}

VAGUE_THREAT_PHRASES = (
    'threaten dire consequences',
    'promise certain ruin',
    'vow to rain destruction on your worlds',
    'warn that we will do something about it',
    'hint at a most unpleasant response',
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
    return verb


def vague_threat_phrase(contract):
    if contract is None:
        return VAGUE_THREAT_PHRASES[0]
    seed = (
        str(getattr(contract, 'short_id', '') or '') or
        str(getattr(contract, 'id', '') or '') or
        '%s-%s-%s' % (
            getattr(contract, 'sender_id', 0),
            getattr(contract, 'recipient_id', 0),
            getattr(contract, 'created_at', ''),
        )
    )
    digest = hashlib.sha1(seed.encode('utf-8')).hexdigest()
    index = int(digest[:8], 16) % len(VAGUE_THREAT_PHRASES)
    return VAGUE_THREAT_PHRASES[index]


def player_display_name(player, include_account=True):
    if not player:
        return 'Unknown race'
    race_name = (
        getattr(player, 'plural_name', None) or
        getattr(player, 'name', None) or
        'Unknown race'
    )
    if not include_account:
        return race_name
    return '%s (%s)' % (race_name, player_bracket_label(player, unknown='Unknown'))


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


def _format_contract_map_target(game, obj, fallback_label):
    label = escape(getattr(obj, 'name', fallback_label))
    if obj is None:
        return label
    base = reverse('dj4xol:game', args=[game.short_id])
    return format_map_link(
        base,
        getattr(obj, 'x', 0),
        getattr(obj, 'y', 0),
        getattr(obj, 'name', fallback_label),
        short_id=getattr(obj, 'short_id', None),
    )


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
    if clause_type == DiplomaticContract.CLAUSE_VAGUE_THREAT:
        return vague_threat_phrase(contract)
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
        if include_links:
            return _format_contract_map_target(contract.game, fleet, 'Unknown Fleet')
        return escape(getattr(fleet, 'name', 'Unknown Fleet'))
    if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        star = getattr(contract, '%s_star' % prefix)
        if star is None:
            return 'the promised colony'
        if include_links:
            return 'colony %s' % _format_contract_map_target(contract.game, star, 'Unknown Colony')
        return 'colony %s' % escape(getattr(star, 'name', 'Unknown Colony'))
    if clause_type == DiplomaticContract.CLAUSE_REPORT:
        label = format_report_trade_label(
            getattr(contract, '%s_report_target_type' % prefix, ''),
            getattr(contract, '%s_report_target_id' % prefix, None),
            contract.game,
            include_links=include_links,
        )
        return 'report on %s' % label
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
        if clause_type == DiplomaticContract.CLAUSE_REPORT:
            object_pronoun = 'us' if sender_is_viewer else 'them'
            report_text = format_contract_clause(contract, prefix, viewer=viewer, include_links=include_links)
            return 'grant %s %s' % (object_pronoun, report_text)
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
        if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
            colony = format_contract_clause(contract, prefix, viewer=viewer, include_links=include_links)
            object_pronoun = 'us' if sender_is_viewer else 'them'
            return 'give %s %s' % (object_pronoun, colony)
    if prefix == 'offer':
        if clause_type == DiplomaticContract.CLAUSE_NOTHING:
            return 'do nothing'
        if clause_type == DiplomaticContract.CLAUSE_VAGUE_THREAT:
            return vague_threat_phrase(contract)
        if clause_type == DiplomaticContract.CLAUSE_TECHNOLOGY:
            tech = getattr(contract, '%s_technology' % prefix)
            object_pronoun = 'them' if sender_is_viewer else 'us'
            return 'grant %s technology %s' % (object_pronoun, getattr(tech, 'name', 'Unknown technology'))
        if clause_type == DiplomaticContract.CLAUSE_REPORT:
            object_pronoun = 'them' if sender_is_viewer else 'us'
            report_text = format_contract_clause(contract, prefix, viewer=viewer, include_links=include_links)
            return 'grant %s %s' % (object_pronoun, report_text)
        if clause_type == DiplomaticContract.CLAUSE_STANCE:
            stance = str(getattr(contract, '%s_stance' % prefix) or '').lower() or 'neutral'
            possessive = 'our' if sender_is_viewer else 'their'
            return 'set %s stance to %s' % (possessive, stance)
        if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
            fleet = getattr(contract, '%s_fleet' % prefix)
            if fleet is None:
                object_pronoun = 'them' if sender_is_viewer else 'us'
                return 'give %s the promised fleet' % object_pronoun
            if include_links:
                label = _format_contract_map_target(contract.game, fleet, 'Unknown Fleet')
            else:
                label = escape(getattr(fleet, 'name', 'Unknown Fleet'))
            object_pronoun = 'them' if sender_is_viewer else 'us'
            return 'give %s %s' % (object_pronoun, label)
        if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
            colony = format_contract_clause(contract, prefix, viewer=viewer, include_links=include_links)
            object_pronoun = 'them' if sender_is_viewer else 'us'
            return 'give %s %s' % (object_pronoun, colony)
    return format_contract_clause(contract, prefix, viewer=viewer, include_links=include_links)


def format_contract_summary(contract, viewer=None, include_links=True, include_sender_account=True):
    return format_contract_statement(
        contract,
        viewer=viewer,
        include_links=include_links,
        include_sender_account=include_sender_account,
        emphasize_actions=False,
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


def _contract_counterparty_short_id(contract, viewer):
    if contract is None:
        return ''
    if getattr(contract.sender, 'id', None) == getattr(viewer, 'id', None):
        return getattr(contract.recipient, 'short_id', '')
    return getattr(contract.sender, 'short_id', '')


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
            'offer_star',
            'request_star',
            'request_suggested_star',
        ).order_by('expires_year', 'created_at')
    )
    entries = []
    for contract in contracts:
        if contract.offer_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
            ensure_specific_fleet_report(contract)
        if contract.offer_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
            ensure_specific_colony_report(contract)
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
            request_clause_type__in=REQUEST_RESOURCE_CLAUSE_TYPES + (DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT,),
            sender__in=[player],
        ).select_related(
            'sender',
            'sender__account',
            'recipient',
            'recipient__account',
            'request_technology',
            'offer_technology',
            'offer_fleet',
            'offer_star',
            'request_star',
            'request_suggested_star',
        ).order_by('-accepted_year', '-created_at')
    ) + list(
        DiplomaticContract.objects.filter(
            game=player.game,
            status=DiplomaticContract.STATUS_ACCEPTED,
            request_clause_type__in=REQUEST_RESOURCE_CLAUSE_TYPES + (DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT,),
            recipient__in=[player],
        ).select_related(
            'sender',
            'sender__account',
            'recipient',
            'recipient__account',
            'request_technology',
            'offer_technology',
            'offer_fleet',
            'offer_star',
            'request_star',
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
                    target_short_id=_contract_counterparty_short_id(contract, player),
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


def _contract_status_message_text(contract, viewer, event_key, summary):
    if not contract or not viewer:
        return summary
    sender = getattr(contract, 'sender', None)
    recipient = getattr(contract, 'recipient', None)
    sender_name = getattr(sender, 'plural_name', None) or getattr(sender, 'name', 'Unknown')
    recipient_name = getattr(recipient, 'plural_name', None) or getattr(recipient, 'name', 'Unknown')
    if event_key == 'accepted':
        if getattr(viewer, 'id', None) == getattr(sender, 'id', None):
            return 'Diplomatic request accepted by %s: %s' % (recipient_name, summary)
        return 'We accepted diplomatic request from %s: %s' % (sender_name, summary)
    if event_key == 'declined':
        if getattr(viewer, 'id', None) == getattr(sender, 'id', None):
            return 'Diplomatic request declined by %s: %s' % (recipient_name, summary)
        return 'We declined diplomatic request from %s: %s' % (sender_name, summary)
    if event_key == 'expired':
        if getattr(viewer, 'id', None) == getattr(sender, 'id', None):
            return 'Diplomatic request to %s expired: %s' % (recipient_name, summary)
        return 'Diplomatic request from %s expired: %s' % (sender_name, summary)
    return 'Diplomatic request %s: %s' % (event_key, summary)


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
    if _created:
        _apply_reverse_engineering_reward(
            player,
            technology,
            year=year,
        )
    return grant


def _create_reverse_engineering_message(player, year, text):
    GameMessage.objects.create(
        game=player.game,
        player=player,
        year=int(year or 0),
        category='RESEARCH',
        message=text,
        priority=False,
    )


def _apply_reverse_engineering_reward(player, technology, year=None):
    if not player or technology is None or technology.category_id is None:
        return
    from .research import ensure_player_research_rows, apply_research_bonus_rp, get_level_requirement

    rows = ensure_player_research_rows(player)
    row = None
    for candidate in rows:
        if candidate.category_id == technology.category_id:
            row = candidate
            break
    if row is None:
        return

    current_level = int(row.current_level or 0)
    gifted_level = int(getattr(technology, 'level', 0) or 0)
    if gifted_level < current_level + 3:
        return

    if year is None:
        year = player.game.year if getattr(player, 'game', None) is not None else 0

    roll = random.randint(1, 3)
    if roll == 3:
        _create_reverse_engineering_message(
            player,
            year,
            "Reverse engineering of gifted technology %s yielded no immediate breakthroughs."
            % getattr(technology, 'name', 'Unknown technology'),
        )
        return

    if roll == 1:
        gifted_req = get_level_requirement(technology.category_id, gifted_level, player=player)
        current_req_level = max(1, current_level + 1)
        current_req = get_level_requirement(technology.category_id, current_req_level, player=player)
        rp_gap = max(
            1,
            int(gifted_req.get('rp_cost', 0) or 0) - int(current_req.get('rp_cost', 0) or 0),
        )
        fraction = random.uniform(0.20, 0.50)
        bonus_rp = max(1, int(round(float(rp_gap) * float(fraction))))
        result = apply_research_bonus_rp(player, technology.category_id, bonus_rp)
        text = (
            "Reverse engineering of gifted technology %s yielded %s RP in %s."
            % (getattr(technology, 'name', 'Unknown technology'), bonus_rp, technology.category.name)
        )
        if result and int(result.get('new_level', 0)) > int(result.get('old_level', 0)):
            text += " Level increased to %s." % int(result['new_level'])
        _create_reverse_engineering_message(player, year, text)
        return

    jump = random.randint(1, 2)
    target_level = min(gifted_level, current_level + jump)
    if target_level <= current_level:
        _create_reverse_engineering_message(
            player,
            year,
            "Reverse engineering of gifted technology %s yielded no immediate breakthroughs."
            % getattr(technology, 'name', 'Unknown technology'),
        )
        return
    row.current_level = int(target_level)
    row.save(update_fields=['current_level'])
    _create_reverse_engineering_message(
        player,
        year,
        "Reverse engineering of gifted technology %s advanced %s to level %s."
        % (getattr(technology, 'name', 'Unknown technology'), technology.category.name, int(target_level)),
    )


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


def _report_tier_rank(tier):
    return REPORT_TIER_ORDER.get(str(tier or '').lower(), -1)


def _report_target_model(target_type):
    from .models import Anomaly, Fleet, Salvage, Star

    models = {
        'star': Star,
        'fleet': Fleet,
        'anomaly': Anomaly,
        'salvage': Salvage,
    }
    return models.get(str(target_type or '').lower())


def _resolve_report_target(game, target_type, target_id):
    model = _report_target_model(target_type)
    if model is None or not target_id or game is None:
        return None
    return model.objects.filter(game=game, id=target_id).first()


def _qualifying_report_for_trade(player, target_type, target_id):
    if not player or not target_type or not target_id:
        return None
    report = Report.objects.filter(
        player=player,
        target_type=target_type,
        target_id=target_id,
    ).first()
    if report is None:
        normalized_target_type = str(target_type or '').lower()
        target = _resolve_report_target(getattr(player, 'game', None), normalized_target_type, target_id)
        owner_field = 'player_id'
        if (
            target is not None and
            getattr(target, owner_field, None) == getattr(player, 'id', None) and
            normalized_target_type in ('star', 'fleet')
        ):
            from .turn import GameTurn

            GameTurn(player.game)._create_or_update_report(
                player,
                normalized_target_type,
                target,
                player.game.year,
                report_tier='ownership',
            )
            report = Report.objects.filter(
                player=player,
                target_type=normalized_target_type,
                target_id=target.id,
            ).first()
            if report is not None:
                return report
        return None
    data = report.get_report_data()
    rank = _report_tier_rank(data.get('report_tier'))
    if target_type == 'star':
        if data.get('player_name'):
            return report
        return None
    if target_type == 'fleet':
        return report
    if target_type == 'anomaly':
        return report if rank >= _report_tier_rank('advanced') else None
    if target_type == 'salvage':
        if rank >= _report_tier_rank('advanced') and data.get('salvage_type') == 'ANCIENT_DEBRIS':
            return report
    return None


def _shared_report_data(source_report, recipient=None):
    if source_report is None:
        return None
    data = dict(source_report.get_report_data() or {})
    target_type = source_report.target_type
    if target_type in ('star', 'fleet'):
        unknown = list(data.get('unknown_secret_resources') or [])
        for key in SECRET_RESOURCE_KEYS:
            if recipient is not None and bool(getattr(recipient, 'discovered_%s' % key, False)):
                continue
            present = key in unknown
            if target_type == 'star':
                present = present or int(data.get('%s_yield' % key, 0) or 0) > 0
            present = present or int(data.get('%s_inventory' % key, 0) or 0) > 0
            if not present:
                continue
            if key not in unknown:
                unknown.append(key)
        data['unknown_secret_resources'] = unknown
        data['report_tier'] = data.get('report_tier') or 'advanced'
        return data
    if target_type in ('anomaly', 'salvage'):
        if _report_tier_rank(data.get('report_tier')) < _report_tier_rank('advanced'):
            return None
        data['report_tier'] = data.get('report_tier') or 'advanced'
        return data
    return None


def format_report_trade_label(target_type, target_id, game, include_links=False):
    target = _resolve_report_target(game, target_type, target_id)
    target_type = str(target_type or '').lower()
    if target_type == 'star':
        label = escape(getattr(target, 'name', None) or 'Unknown Colony')
        if include_links and target is not None:
            label = _format_contract_map_target(game, target, 'Unknown Colony')
        return 'colony %s' % label
    if target_type == 'anomaly':
        label = escape(getattr(target, 'name', None) or 'Unknown Anomaly')
        if include_links and target is not None:
            label = _format_contract_map_target(game, target, 'Unknown Anomaly')
        return 'anomaly %s' % label
    if target_type == 'salvage':
        label = escape(getattr(target, 'name', None) or 'Unknown Ancient Debris')
        if include_links and target is not None:
            label = _format_contract_map_target(game, target, 'Unknown Ancient Debris')
        return 'ancient debris %s' % label
    return 'unknown report'


def _grant_report_trade(contract, prefix):
    from .messages import UnexplainedScanContactMessageFactory

    if prefix == 'request':
        grant_source = contract.recipient
        grant_target = contract.sender
    else:
        grant_source = contract.sender
        grant_target = contract.recipient
    target_type = getattr(contract, '%s_report_target_type' % prefix, '')
    target_id = getattr(contract, '%s_report_target_id' % prefix, None)
    source_report = _qualifying_report_for_trade(grant_source, target_type, target_id)
    if source_report is None:
        return False
    shared = _shared_report_data(source_report, recipient=grant_target)
    if shared is None:
        return False
    existing = Report.objects.filter(
        player=grant_target,
        target_type=target_type,
        target_id=target_id,
    ).first()
    incoming_rank = _report_tier_rank(shared.get('report_tier'))
    source_rank = _report_tier_rank((source_report.get_report_data() or {}).get('report_tier'))
    old_unknown = []
    new_unknown = list((shared or {}).get('unknown_secret_resources') or [])
    should_warn = False
    if existing is not None:
        existing_data = existing.get_report_data()
        old_unknown = list((existing_data or {}).get('unknown_secret_resources') or [])
        existing_rank = _report_tier_rank(existing_data.get('report_tier'))
        if existing_rank > incoming_rank:
            return True
        should_warn = bool(
            target_type == 'star' and
            source_rank >= _report_tier_rank('advanced') and
            new_unknown and
            any(key not in old_unknown for key in new_unknown)
        )
        if (
            existing_rank == incoming_rank and
            int(existing.year or 0) >= int(source_report.year or 0) and
            not should_warn
        ):
            return True
        existing.year = source_report.year
        existing.game = contract.game
        existing.set_report_data(shared)
        existing.save()
    else:
        report = Report.objects.create(
            game=contract.game,
            player=grant_target,
            year=source_report.year,
            target_type=target_type,
            target_id=target_id,
            cached_report='{}',
        )
        report.set_report_data(shared)
        report.save()
        should_warn = bool(
            target_type == 'star' and
            source_rank >= _report_tier_rank('advanced') and
            new_unknown
        )
    if should_warn:
        factory = UnexplainedScanContactMessageFactory(
            contract.game,
            grant_target,
            target=_resolve_report_target(contract.game, target_type, target_id),
            subject='traces of an unexplained material',
        )
        msg = factory.new_message()
        msg.year = contract.game.year
        msg.save()
    return True


def _colony_clause_parties(contract, prefix):
    if prefix == 'request':
        return contract.recipient, contract.sender
    return contract.sender, contract.recipient


def _specific_colony_clause_available(contract, prefix):
    grant_source, _grant_target = _colony_clause_parties(contract, prefix)
    star = getattr(contract, '%s_star' % prefix)
    return bool(
        star is not None and
        star.game_id == contract.game_id and
        star.player_id == getattr(grant_source, 'id', None)
    )


def _evacuate_colony_to_owner_fleets(star, owner):
    if star is None or owner is None:
        return 0
    try:
        colony_kt = max(0, int(star.colonists or 0) // 1000)
    except (TypeError, ValueError):
        colony_kt = 0
    if colony_kt <= 10:
        return 0

    max_transfer_kt = min(
        int((int(star.colonists or 0) * 0.75) // 1000),
        max(0, colony_kt - 10),
    )
    if max_transfer_kt <= 0:
        return 0

    transferred_kt = 0
    fleets = owner.fleets.filter(
        game=star.game,
        x=star.x,
        y=star.y,
    ).order_by('id')
    for fleet in fleets:
        remaining = max_transfer_kt - transferred_kt
        if remaining <= 0:
            break
        capacity = max(0, int(getattr(fleet, 'cargo_remaining', 0) or 0))
        if capacity <= 0:
            continue
        load_kt = min(remaining, capacity)
        if load_kt <= 0:
            continue
        fleet.colonists = int(getattr(fleet, 'colonists', 0) or 0) + load_kt
        fleet.save(update_fields=['colonists'])
        transferred_kt += load_kt

    if transferred_kt > 0:
        star.colonists = max(0, int(star.colonists or 0) - (transferred_kt * 1000))
        star.save(update_fields=['colonists'])
    return transferred_kt


def _transfer_specific_colony_clause(contract, prefix, handle_homeworld_loss=True):
    grant_source, grant_target = _colony_clause_parties(contract, prefix)
    star = getattr(contract, '%s_star' % prefix)
    if not _specific_colony_clause_available(contract, prefix):
        return False

    from .messages import ColonyReceivedMessageFactory, ColonyTransferredMessageFactory

    _evacuate_colony_to_owner_fleets(star, grant_source)
    star.player = grant_target
    star.save(update_fields=['player'])
    sender_msg = ColonyTransferredMessageFactory(
        contract.game,
        grant_source,
        star,
        grant_target.name,
    ).new_message()
    sender_msg.year = contract.game.year
    sender_msg.save()
    recipient_msg = ColonyReceivedMessageFactory(
        contract.game,
        grant_target,
        star,
        grant_source.name,
    ).new_message()
    recipient_msg.year = contract.game.year
    recipient_msg.save()
    if handle_homeworld_loss:
        _handle_diplomatic_homeworld_loss(contract.game, grant_source, star)
    return True


def _apply_specific_colony_exchange(contract):
    if not _specific_colony_clause_available(contract, 'request'):
        return False, 'request_unavailable'
    if not _specific_colony_clause_available(contract, 'offer'):
        return False, 'offer_unavailable'

    _transfer_specific_colony_clause(contract, 'request', handle_homeworld_loss=False)
    _transfer_specific_colony_clause(contract, 'offer', handle_homeworld_loss=False)
    request_source, _request_target = _colony_clause_parties(contract, 'request')
    offer_source, _offer_target = _colony_clause_parties(contract, 'offer')
    request_star = contract.request_star
    offer_star = contract.offer_star
    _handle_diplomatic_homeworld_loss(contract.game, request_source, request_star)
    _handle_diplomatic_homeworld_loss(contract.game, offer_source, offer_star)
    return True, ''


def _handle_diplomatic_homeworld_loss(game, player, lost_star):
    if player is None or lost_star is None:
        return
    if int(getattr(player, 'homeworld_id', 0) or 0) != int(getattr(lost_star, 'id', 0) or 0):
        return
    from .turn import GameTurn

    turn = GameTurn(game)
    if bool(getattr(player, 'fixed_homeworld', False)):
        turn._defeat_player(
            player,
            lost_star_id=lost_star.id,
            location=(lost_star.x, lost_star.y),
        )
        return
    replacement = player.stars.exclude(id=lost_star.id).order_by('-colonists', 'id').first()
    if replacement is None:
        turn._defeat_player(
            player,
            lost_star_id=lost_star.id,
            location=(lost_star.x, lost_star.y),
        )
        return
    player.homeworld = replacement
    player.save(update_fields=['homeworld'])


def _apply_clause_immediately(contract, prefix, year):
    clause_type = getattr(contract, '%s_clause_type' % prefix)
    if clause_type not in APPLY_ON_ACCEPT_CLAUSE_TYPES:
        return False
    if prefix == 'request':
        grant_source = contract.recipient
        grant_target = contract.sender
    else:
        grant_source = contract.sender
        grant_target = contract.recipient

    if clause_type == DiplomaticContract.CLAUSE_NOTHING:
        return True
    if clause_type == DiplomaticContract.CLAUSE_VAGUE_THREAT:
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
    if clause_type == DiplomaticContract.CLAUSE_REPORT:
        return _grant_report_trade(contract, prefix)
    if clause_type == DiplomaticContract.CLAUSE_STANCE:
        stance = getattr(contract, '%s_stance' % prefix)
        _set_pending_stance(grant_source, grant_target, stance)
        return True
    if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
        from .messages import FleetReceivedMessageFactory, FleetTransferredMessageFactory

        fleet = getattr(contract, '%s_fleet' % prefix)
        if fleet is None or fleet.game_id != contract.game_id or fleet.player_id != grant_source.id:
            return False
        fleet.orders.all().delete()
        fleet.player = grant_target
        fleet.travel_warp = 0
        fleet.save(update_fields=['player', 'travel_warp'])
        if _is_micromanager_ai_player(grant_target):
            _queue_fleet_to_nearest_owned_colony(fleet, grant_target)
        sender_msg = FleetTransferredMessageFactory(
            contract.game,
            grant_source,
            fleet,
            recipient_name=grant_target.name,
        ).new_message()
        sender_msg.year = contract.game.year
        sender_msg.save()
        recipient_msg = FleetReceivedMessageFactory(
            contract.game,
            grant_target,
            fleet,
            grant_source.name,
        ).new_message()
        recipient_msg.year = contract.game.year
        recipient_msg.save()
        return True
    if clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        return _transfer_specific_colony_clause(contract, prefix, handle_homeworld_loss=True)
    return False


def _queue_fleet_to_nearest_owned_colony(fleet, player):
    from .models import FleetOrders

    if fleet is None or player is None:
        return False
    if int(getattr(fleet, 'game_id', 0) or 0) != int(getattr(player, 'game_id', 0) or 0):
        return False
    if int(getattr(fleet, 'player_id', 0) or 0) != int(getattr(player, 'id', 0) or 0):
        return False

    best_star = None
    best_key = None
    origin_x = int(getattr(fleet, 'x', 0) or 0)
    origin_y = int(getattr(fleet, 'y', 0) or 0)
    for star in player.stars.all():
        dx = int(getattr(star, 'x', 0) or 0) - origin_x
        dy = int(getattr(star, 'y', 0) or 0) - origin_y
        distance_sq = (dx * dx) + (dy * dy)
        # Prefer nearest colony, break ties by higher population then stable id.
        key = (
            distance_sq,
            -int(getattr(star, 'colonists', 0) or 0),
            int(getattr(star, 'id', 0) or 0),
        )
        if best_key is None or key < best_key:
            best_key = key
            best_star = star

    if best_star is None:
        return False
    if (
        int(getattr(best_star, 'x', 0) or 0) == origin_x and
        int(getattr(best_star, 'y', 0) or 0) == origin_y
    ):
        return False

    try:
        safe_warp = int(getattr(fleet, 'max_safe_warp', 5) or 5)
    except (TypeError, ValueError):
        safe_warp = 5
    try:
        cloaked_warp = int(getattr(fleet, 'max_cloaked_warp', 0) or 0)
    except (TypeError, ValueError):
        cloaked_warp = 0
    move_warp = cloaked_warp if cloaked_warp > 0 else safe_warp
    move_warp = max(1, min(13, move_warp))

    FleetOrders.objects.create(
        game=fleet.game,
        fleet=fleet,
        order_type='MOVE',
        repeat=False,
        warpfactor=move_warp,
        original_warpfactor=move_warp,
        overmax_risk_checked=False,
        target_star=best_star,
        target_kind='OBJECT',
        target_short_id=best_star.short_id,
        x=int(best_star.x),
        y=int(best_star.y),
    )
    return True


def _is_micromanager_ai_player(player):
    if player is None:
        return False
    if not bool(getattr(player, 'is_ai', False)):
        return False
    return ai_module_uses_micromanager_behavior(getattr(player, 'ai_module', ''))


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
    if clause_type in APPLY_ON_ACCEPT_CLAUSE_TYPES:
        return contract.status == DiplomaticContract.STATUS_FULFILLED
    return False


def _mark_contract_fulfilled(contract, year):
    contract.status = DiplomaticContract.STATUS_FULFILLED
    contract.fulfilled_year = year
    contract.handled_year = year
    contract.save(update_fields=['status', 'fulfilled_year', 'handled_year', 'updated_at'])
    sender_summary = format_contract_summary(
        contract,
        viewer=contract.sender,
        include_links=False,
        include_sender_account=False,
    )
    recipient_summary = format_contract_summary(
        contract,
        viewer=contract.recipient,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(
        contract.sender,
        contract,
        'Diplomatic request fulfilled: %s' % sender_summary,
        priority=True,
    )
    _create_contract_status_message(
        contract.recipient,
        contract,
        'Diplomatic request fulfilled: %s' % recipient_summary,
        priority=True,
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
    sender_summary = format_contract_summary(
        contract,
        viewer=contract.sender,
        include_links=False,
        include_sender_account=False,
    )
    recipient_summary = format_contract_summary(
        contract,
        viewer=contract.recipient,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(
        contract.sender,
        contract,
        _contract_status_message_text(contract, contract.sender, 'expired', sender_summary),
        priority=True,
    )
    _create_contract_status_message(
        contract.recipient,
        contract,
        _contract_status_message_text(contract, contract.recipient, 'expired', recipient_summary),
        priority=True,
    )


def ensure_specific_fleet_report(contract):
    if (
        contract.offer_clause_type != DiplomaticContract.CLAUSE_SPECIFIC_FLEET or
        contract.offer_fleet is None or
        not bool(getattr(contract, 'offer_fleet_include_report', True))
    ):
        return
    source_report = _qualifying_report_for_trade(
        contract.sender,
        'fleet',
        contract.offer_fleet.id,
    )
    if source_report is None:
        return
    shared = _shared_report_data(source_report, recipient=contract.recipient)
    if shared is None:
        return
    report, _created = Report.objects.get_or_create(
        game=contract.game,
        player=contract.recipient,
        target_type='fleet',
        target_id=contract.offer_fleet.id,
        defaults={
            'year': source_report.year,
            'cached_report': '{}',
        },
    )
    report.year = source_report.year
    report.game = contract.game
    report.set_report_data(shared)
    report.save()


def ensure_specific_colony_report(contract):
    if contract.offer_clause_type != DiplomaticContract.CLAUSE_SPECIFIC_COLONY or contract.offer_star is None:
        return
    source_report = _qualifying_report_for_trade(
        contract.sender,
        'star',
        contract.offer_star.id,
    )
    if source_report is None:
        return
    shared = _shared_report_data(source_report, recipient=contract.recipient)
    if shared is None:
        return
    report, _created = Report.objects.get_or_create(
        game=contract.game,
        player=contract.recipient,
        target_type='star',
        target_id=contract.offer_star.id,
        defaults={
            'year': source_report.year,
            'cached_report': '{}',
        },
    )
    report.year = source_report.year
    report.game = contract.game
    report.set_report_data(shared)
    report.save()


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

    colony_contracts = DiplomaticContract.objects.filter(
        game=game,
        status__in=[DiplomaticContract.STATUS_SENT, DiplomaticContract.STATUS_ACCEPTED],
        request_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_COLONY,
    ).select_related('request_star', 'sender', 'recipient')
    for contract in colony_contracts:
        star = contract.request_star
        if star is None or star.game_id != game.id or star.player_id != contract.recipient_id:
            _expire_contract(contract, game.year, apply_consequence=False)

    offered_colony_contracts = DiplomaticContract.objects.filter(
        game=game,
        status__in=[DiplomaticContract.STATUS_SENT, DiplomaticContract.STATUS_ACCEPTED],
        offer_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_COLONY,
    ).select_related('offer_star', 'sender', 'recipient')
    for contract in offered_colony_contracts:
        star = contract.offer_star
        if star is None or star.game_id != game.id or star.player_id != contract.sender_id:
            _expire_contract(contract, game.year, apply_consequence=False)

    expirable = DiplomaticContract.objects.filter(
        game=game,
        status__in=[DiplomaticContract.STATUS_SENT, DiplomaticContract.STATUS_ACCEPTED],
    ).select_related('sender', 'recipient')
    for contract in expirable:
        if bool(getattr(contract.sender, 'defeated', False)) or bool(getattr(contract.recipient, 'defeated', False)):
            _expire_contract(contract, game.year, apply_consequence=False)
            continue
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

    sender_summary = format_contract_summary(
        contract,
        viewer=contract.sender,
        include_links=False,
        include_sender_account=False,
    )
    recipient_summary = format_contract_summary(
        contract,
        viewer=contract.recipient,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(
        contract.sender,
        contract,
        _contract_status_message_text(contract, contract.sender, 'accepted', sender_summary),
        priority=True,
    )
    _create_contract_status_message(
        contract.recipient,
        contract,
        _contract_status_message_text(contract, contract.recipient, 'accepted', recipient_summary),
        priority=True,
    )

    if (
        contract.request_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY and
        contract.offer_condition_type == DiplomaticContract.CONDITION_EXCHANGE and
        contract.offer_clause_type == DiplomaticContract.CLAUSE_SPECIFIC_COLONY
    ):
        ok, reason = _apply_specific_colony_exchange(contract)
        if not ok:
            _expire_contract(
                contract,
                contract.game.year,
                apply_consequence=(reason == 'request_unavailable'),
            )
            if reason == 'offer_unavailable':
                return False, 'Request could not be completed because the offered clause is no longer available.'
            return False, 'Request could not be completed because the requested clause is no longer available.'
        _mark_contract_fulfilled(contract, contract.game.year)
        return True, 'Request accepted and fulfilled.'

    if contract.request_clause_type in APPLY_ON_ACCEPT_CLAUSE_TYPES:
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
    sender_summary = format_contract_summary(
        contract,
        viewer=contract.sender,
        include_links=False,
        include_sender_account=False,
    )
    recipient_summary = format_contract_summary(
        contract,
        viewer=contract.recipient,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(
        contract.sender,
        contract,
        _contract_status_message_text(contract, contract.sender, 'declined', sender_summary),
        priority=True,
    )
    _create_contract_status_message(
        contract.recipient,
        contract,
        _contract_status_message_text(contract, contract.recipient, 'declined', recipient_summary),
        priority=True,
    )
    return True, 'Request declined.'


@transaction.atomic
def extend_contract(contract, acting_player, extra_years):
    if not contract or not acting_player or contract.sender_id != acting_player.id:
        return False, 'Request not found.'
    if contract.status != DiplomaticContract.STATUS_SENT:
        return False, 'Only unanswered requests can be extended.'
    locked, reason = diplomatic_actions_locked(acting_player)
    if locked:
        return False, reason
    try:
        years = int(extra_years)
    except (TypeError, ValueError):
        return False, 'Extension years must be a whole number.'
    if years <= 0:
        return False, 'Extension years must be at least 1.'
    if years > 200:
        return False, 'Extension years must be 200 or less.'
    contract.expires_year = int(contract.expires_year or 0) + years
    contract.save(update_fields=['expires_year', 'updated_at'])
    return True, 'Request extended.'


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
    if int(contract.sent_year or 0) != int(contract.game.year or 0):
        _create_contract_status_message(contract.sender, contract, 'Diplomatic request revoked: %s' % summary)
        _create_contract_status_message(contract.recipient, contract, 'Diplomatic request revoked: %s' % summary)
    return True, 'Request revoked.'


def mark_countered(original_contract, new_contract):
    if original_contract is None or new_contract is None:
        return
    original_contract.status = DiplomaticContract.STATUS_COUNTERED
    original_contract.handled_year = original_contract.game.year
    original_contract.save(update_fields=['status', 'handled_year', 'updated_at'])
    sender_summary = format_contract_summary(
        original_contract,
        viewer=original_contract.sender,
        include_links=False,
        include_sender_account=False,
    )
    recipient_summary = format_contract_summary(
        original_contract,
        viewer=original_contract.recipient,
        include_links=False,
        include_sender_account=False,
    )
    _create_contract_status_message(
        original_contract.sender,
        original_contract,
        'Diplomatic request countered: %s' % sender_summary,
    )
    _create_contract_status_message(
        original_contract.recipient,
        original_contract,
        'Diplomatic request countered: %s' % recipient_summary,
    )


def _apply_offer_on_completion(contract, year):
    if contract.offer_condition_type == DiplomaticContract.CONDITION_OR_ELSE:
        return True
    if contract.offer_clause_type in (
        DiplomaticContract.CLAUSE_NOTHING,
        DiplomaticContract.CLAUSE_VAGUE_THREAT,
    ):
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
            'offer_star',
            'request_star',
            'request_suggested_star',
        ).order_by('-created_at')
    )


def player_contract_queryset(player):
    if not player:
        return DiplomaticContract.objects.none()
    return DiplomaticContract.objects.filter(
        game=player.game,
    ).filter(
        Q(sender=player) | Q(recipient=player),
    ).select_related(
        'sender',
        'sender__account',
        'recipient',
        'recipient__account',
        'request_technology',
        'offer_technology',
        'offer_fleet',
        'offer_star',
        'request_star',
        'request_suggested_star',
    )


def list_player_contracts(player, status='sent', direction='both', oldest_first=False):
    qs = player_contract_queryset(player)
    mode = str(status or '').strip().lower()
    if mode == 'sent':
        qs = qs.filter(status=DiplomaticContract.STATUS_SENT)
    elif mode == 'active':
        qs = qs.filter(
            status__in=[
                DiplomaticContract.STATUS_SENT,
                DiplomaticContract.STATUS_ACCEPTED,
            ]
        )
    elif mode in ('all', ''):
        pass
    else:
        qs = qs.filter(status=str(status or '').strip().upper())

    side = str(direction or '').strip().lower()
    if side == 'incoming':
        qs = qs.filter(recipient=player)
    elif side == 'outgoing':
        qs = qs.filter(sender=player)

    if oldest_first:
        qs = qs.order_by('sent_year', 'created_at', 'id')
    else:
        qs = qs.order_by('-sent_year', '-created_at', '-id')
    return list(qs)


def get_player_contract_by_short_id(player, short_id):
    token = str(short_id or '').strip().lower()
    if not token:
        return None
    return player_contract_queryset(player).filter(short_id=token).first()


def contract_action_permissions(contract, acting_player):
    if contract is None or acting_player is None:
        return {
            'can_accept': False,
            'can_decline': False,
            'can_revoke': False,
            'can_extend': False,
        }
    unanswered = contract.status == DiplomaticContract.STATUS_SENT
    return {
        'can_accept': bool(unanswered and contract.recipient_id == acting_player.id),
        'can_decline': bool(unanswered and contract.recipient_id == acting_player.id),
        'can_revoke': bool(unanswered and contract.sender_id == acting_player.id),
        'can_extend': bool(unanswered and contract.sender_id == acting_player.id),
    }


def perform_contract_action(contract, acting_player, action, extra_years=None):
    op = str(action or '').strip().lower()
    if op == 'accept':
        return accept_contract(contract, acting_player)
    if op == 'decline':
        return decline_contract(contract, acting_player)
    if op == 'revoke':
        return revoke_contract(contract, acting_player)
    if op == 'extend':
        return extend_contract(contract, acting_player, extra_years)
    return False, 'Unknown contract action: %s' % action
