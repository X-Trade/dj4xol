from browser import document


def by_id(node_id):
    try:
        return document[node_id]
    except KeyError:
        return None


alias_input = by_id("id_alias")
username_input = by_id("id_username")
meta = by_id("onboarding-profile-meta")

if alias_input is not None:
    if username_input is not None:
        state = {
            "manual_override": False,
            "last_synced": alias_input.value.strip(),
        }

        def sync_alias_from_username(_ev=None):
            username_value = username_input.value.strip()
            alias_value = alias_input.value.strip()
            should_sync = (
                (not state["manual_override"])
                or (alias_value == state["last_synced"])
                or (not alias_value)
            )
            if should_sync:
                alias_input.value = username_value
                state["last_synced"] = username_value

        def on_alias_input(_ev):
            alias_value = alias_input.value.strip()
            username_value = username_input.value.strip()
            if alias_value == username_value:
                state["manual_override"] = False
                state["last_synced"] = alias_value
            elif alias_value != state["last_synced"]:
                state["manual_override"] = True

        username_input.bind("input", sync_alias_from_username)
        alias_input.bind("input", on_alias_input)
        sync_alias_from_username()
    else:
        # Server-side prefill remains the source of truth; this only fills when blank.
        django_username = ""
        if meta is not None:
            django_username = (meta.attrs.get("data-django-username") or "").strip()
        if django_username and not alias_input.value.strip():
            alias_input.value = django_username
