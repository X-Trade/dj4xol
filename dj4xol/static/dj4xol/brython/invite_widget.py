import json

from browser import ajax, document, html, timer, window


def by_id(node_id):
    try:
        return document[node_id]
    except KeyError:
        return None


raw_input = by_id("id_invitations")
lookup_url_input = by_id("invite-lookup-url")
host = by_id("invite-widget-host")

if raw_input is not None and host is not None and host.attrs.get("data-invite-mounted") != "1":
    host.attrs["data-invite-mounted"] = "1"
    host.clear()

    lookup_url = ""
    if lookup_url_input is not None:
        lookup_url = lookup_url_input.value

    raw_input.style.display = "none"

    widget = html.DIV(Class="invite-token-widget")
    chips = html.DIV(Class="invite-token-chips")
    text_input = html.INPUT(
        type="text",
        Class="invite-token-input",
        autocomplete="off",
        spellcheck="false",
        autocorrect="off",
        autocapitalize="none",
        placeholder="Type aliases or usernames",
    )
    suggestions = html.DIV(Class="invite-suggestions")
    widget <= chips
    widget <= text_input
    host <= widget
    host <= suggestions

    tokens = []
    state = {
        "debounce_id": None,
        "blur_id": None,
    }

    def _token_values():
        return [token["value"] for token in tokens]

    def _update_hidden_input():
        raw_input.value = ", ".join(_token_values())

    def _token_exists(value):
        lowered = value.lower()
        for token in tokens:
            if token["value"].lower() == lowered:
                return True
        return False

    def _remove_token(value):
        lowered = value.lower()
        kept = []
        for token in tokens:
            if token["value"].lower() != lowered:
                kept.append(token)
        tokens[:] = kept
        render_tokens()

    def render_tokens():
        chips.clear()
        for token in tokens:
            chip = html.SPAN(Class="invite-chip")
            chip <= html.SPAN(token["label"], Class="invite-chip-label")
            remove_btn = html.BUTTON("x", Class="invite-chip-remove", type="button")

            def _on_remove(ev, value=token["value"]):
                ev.preventDefault()
                _remove_token(value)

            remove_btn.bind("click", _on_remove)
            chip <= remove_btn
            chips <= chip
        _update_hidden_input()

    def _add_token(value, label=None):
        clean_value = (value or "").strip()
        if not clean_value or _token_exists(clean_value):
            return
        token_label = (label or clean_value).strip() or clean_value
        tokens.append({
            "value": clean_value,
            "label": token_label,
        })
        render_tokens()

    def _clear_suggestions():
        suggestions.clear()
        suggestions.style.display = "none"

    def _render_suggestions(items):
        suggestions.clear()
        if not items:
            suggestions.style.display = "none"
            return
        for item in items:
            label = item.get("label", "") or item.get("value", "")
            value = item.get("value", "")
            option = html.DIV(label, Class="invite-suggestion")

            def _on_pick(ev, picked_value=value, picked_label=label):
                ev.preventDefault()
                _add_token(picked_value, picked_label)
                text_input.value = ""
                _clear_suggestions()
                text_input.focus()

            option.bind("mousedown", _on_pick)
            suggestions <= option
        suggestions.style.display = "block"

    def _lookup(query, callback):
        if not lookup_url:
            callback([])
            return
        req = ajax.ajax()

        def complete(_ev):
            if req.status != 200:
                callback([])
                return
            try:
                payload = json.loads(req.text or "{}")
                callback(payload.get("results", []))
            except Exception:
                callback([])

        req.bind("complete", complete)
        url = "%s?q=%s" % (lookup_url, window.encodeURIComponent(query))
        req.open("GET", url, True)
        req.send()

    def _resolve_token(raw_token):
        token = (raw_token or "").strip()
        if not token:
            return

        if "@" not in token:
            _add_token(token, token)
            return

        # Only exact email matches are resolved server-side to alias.
        def on_results(results):
            for item in results:
                if item.get("match") == "email":
                    _add_token(item.get("value", token), item.get("label", token))
                    return
            _add_token(token, token)

        _lookup(token, on_results)

    def _consume_text_as_tokens():
        text = (text_input.value or "").strip()
        if not text:
            return
        for part in text.split(","):
            _resolve_token(part)
        text_input.value = ""
        _clear_suggestions()

    def _on_input(_ev):
        text = (text_input.value or "").strip()
        if state["debounce_id"] is not None:
            timer.clear_timeout(state["debounce_id"])
        if not text or "," in text:
            _clear_suggestions()
            return
        if "@" not in text and len(text) < 2:
            _clear_suggestions()
            return

        def trigger():
            _lookup(text, _render_suggestions)

        state["debounce_id"] = timer.set_timeout(trigger, 140)

    def _on_keydown(ev):
        if ev.key in ("Enter", "Tab", ","):
            ev.preventDefault()
            _consume_text_as_tokens()
            return
        if ev.key == "Backspace" and not text_input.value and tokens:
            ev.preventDefault()
            _remove_token(tokens[-1]["value"])

    def _on_blur(_ev):
        def delayed_commit():
            _consume_text_as_tokens()
            _clear_suggestions()

        state["blur_id"] = timer.set_timeout(delayed_commit, 120)

    def _on_focus(_ev):
        if state["blur_id"] is not None:
            timer.clear_timeout(state["blur_id"])

    for part in (raw_input.value or "").split(","):
        clean = part.strip()
        if clean:
            _add_token(clean, clean)

    text_input.bind("input", _on_input)
    text_input.bind("keydown", _on_keydown)
    text_input.bind("blur", _on_blur)
    text_input.bind("focus", _on_focus)
