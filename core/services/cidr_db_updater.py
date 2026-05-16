"""Backward-compatible shim for CIDR DB updater service."""
from core.services.cidr import db_service


def _reexport(module):
    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        globals()[name] = value


_reexport(db_service)
