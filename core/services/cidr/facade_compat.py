"""Resolve patchable settings from the cidr_list_updater facade module."""


def get_attr(name):
    from core.services import cidr_list_updater

    return getattr(cidr_list_updater, name)


def call(name, *args, **kwargs):
    return get_attr(name)(*args, **kwargs)
