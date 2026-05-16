"""Antifilter overlap index for DB-backed filtering."""
import bisect
import ipaddress
import time

from core.services.cidr.constants import _ANTIFILTER_INDEX_CACHE

def _build_antifilter_overlap_index(cidr_strs):
    """Build sorted ranges + prefix-max-end array for O(log n) overlap queries.

    Returns (ranges, starts, max_ends) where:
      ranges    = sorted list of (start_int, end_int)
      starts    = [r[0] for r in ranges]  (for bisect)
      max_ends  = prefix-max of end values so max_ends[i] = max(e for ranges[0..i])
    """
    ranges = []
    for c in cidr_strs:
        try:
            net = ipaddress.ip_network(c, strict=False)
            if net.prefixlen > 0:
                ranges.append((int(net.network_address), int(net.broadcast_address)))
        except ValueError:
            pass
    ranges.sort()
    starts = [r[0] for r in ranges]
    max_ends = []
    cur = -1
    for _, e in ranges:
        cur = max(cur, e)
        max_ends.append(cur)
    return ranges, starts, max_ends

def _cidr_overlaps_index(cidr_str, ranges, starts, max_ends):
    """O(log n) overlap check: does cidr_str overlap with any range in the index?"""
    if not ranges:
        return False
    try:
        net = ipaddress.ip_network(cidr_str, strict=False)
        ps = int(net.network_address)
        pe = int(net.broadcast_address)
        idx = bisect.bisect_right(starts, pe) - 1
        if idx < 0:
            return False
        # max_ends[idx] = max end among all ranges whose start <= pe
        # if that max end >= ps, at least one range overlaps [ps, pe]
        return max_ends[idx] >= ps
    except ValueError:
        return False

def _cidr_contained_in_index(cidr_str, ranges, starts, max_ends):
    """O(log n) containment check: is cidr_str a subnet of ANY range in the index?

    A CIDR [ps, pe] is contained in range [rs, re] when rs <= ps AND re >= pe.
    Using the prefix-max-end array: find rightmost range with start <= ps,
    then check if its max_end >= pe.
    """
    if not ranges:
        return False
    try:
        net = ipaddress.ip_network(cidr_str, strict=False)
        ps = int(net.network_address)
        pe = int(net.broadcast_address)
        idx = bisect.bisect_right(starts, ps) - 1
        if idx < 0:
            return False
        return max_ends[idx] >= pe
    except ValueError:
        return False

def _load_antifilter_index():
    """Load antifilter index from DB (5-minute in-process cache)."""
    now_ts = time.time()
    if _ANTIFILTER_INDEX_CACHE["index"] is not None and now_ts < float(_ANTIFILTER_INDEX_CACHE["expires_at"]):
        return _ANTIFILTER_INDEX_CACHE["index"]

    from core.models import AntifilterCidr, AntifilterMeta
    meta = AntifilterMeta.query.first()
    if not meta or meta.refresh_status not in ("ok", "partial") or (meta.cidr_count or 0) == 0:
        return None
    rows = AntifilterCidr.query.with_entities(AntifilterCidr.cidr).all()
    index = _build_antifilter_overlap_index([r.cidr for r in rows])
    _ANTIFILTER_INDEX_CACHE["index"] = index
    _ANTIFILTER_INDEX_CACHE["expires_at"] = now_ts + 300.0
    return index

