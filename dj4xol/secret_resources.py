from .mineral_rules import SECRET_RESOURCE_KEYS

SECRET_RESOURCE_SETTING_KEYS = {
    'resource_x': 'secret_resource_x_name',
    'resource_y': 'secret_resource_y_name',
    'resource_z': 'secret_resource_z_name',
}

SECRET_RESOURCE_DEFAULT_NAMES = {
    'resource_x': 'Uniquium',
    'resource_y': 'Rarium',
    'resource_z': 'Mysterium',
}


def get_secret_resource_name(resource_key):
    setting_key = SECRET_RESOURCE_SETTING_KEYS.get(resource_key)
    if not setting_key:
        return resource_key
    from .models import ServerSettings
    return ServerSettings.get(setting_key, SECRET_RESOURCE_DEFAULT_NAMES.get(resource_key, resource_key))


def is_secret_resource_key(resource_key):
    return resource_key in SECRET_RESOURCE_KEYS


def secret_resource_inventory_field(resource_key):
    return f'{resource_key}_inventory'


def secret_resource_yield_field(resource_key):
    return f'{resource_key}_yield'


def get_secret_resource_label(resource_key, discovered):
    if discovered:
        return get_secret_resource_name(resource_key)
    return '???'
