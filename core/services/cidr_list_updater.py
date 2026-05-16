"""Backward-compatible facade for CIDR list updater (tests patch this module)."""
from core.services.cidr import (
    antifilter,
    constants,
    db_pipeline,
    dpi,
    download,
    file_pipeline,
    games,
    geo,
    parsers,
    provider_sources,
    route_limits,
)
from core.services.cidr import _core


def _reexport(module):
    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        globals()[name] = value


for _module in (
    constants,
    provider_sources,
    download,
    parsers,
    geo,
    dpi,
    route_limits,
    games,
    antifilter,
    file_pipeline,
    db_pipeline,
    _core,
):
    _reexport(_module)
