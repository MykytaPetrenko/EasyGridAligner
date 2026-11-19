"""Landmark-driven support posts and fixed-pitch vertical infill for all railing styles."""
from math import ceil, floor
from typing import NamedTuple

from mathutils import Vector

from .railing_parts import _closest_on_path, _landing_route, _trim_path


EPSILON = 1e-6


class PostPlacement(NamedTuple):
    base: Vector
    target: Vector
    segment: tuple
    mandatory: bool


def flight_post_steps(step_count, every_steps, mode):
    """Keep terminal treads in either mode; balance only on integer tread indices."""
    if every_steps < 1 or int(every_steps) != every_steps:
        raise ValueError('Steps per Post must be a positive integer')
    if mode not in ('BALANCED', 'EVERY_N'):
        raise ValueError('Choose Balanced Treads or Every N Steps for flight posts')
    last = step_count - 1
    if last <= 0:
        return [0]
    if mode == 'EVERY_N':
        return sorted(set(range(0, step_count, every_steps)) | {last})
    intervals = max(1, ceil(last / every_steps))
    return [floor(last * i / intervals + .5) for i in range(intervals + 1)]


def _locate(point, path, prefer_flat=False, horizontal=True):
    target, segment = _closest_on_path(point, path, with_segment=True)
    if (target - point).length > EPSILON:
        return None
    if prefer_flat:
        for start, end in zip(path, path[1:]):
            if abs(start.z - end.z) <= EPSILON and (_closest_on_path(point, (start, end)) - point).length <= EPSILON:
                segment = (start, end)
                break
    distance = 0.0
    for start, end in zip(path, path[1:]):
        if start is segment[0]:
            return target, segment, distance + ((target - start).xy.length if horizontal else (target - start).length)
        distance += (end - start).xy.length if horizontal else (end - start).length
    return None


def plan_railing_posts(stairs, frames, landings, path, side, inset, corner_length,
                         every_steps=2, step_mode='BALANCED', landing_auto=True,
                         landing_spacing=.6, post_size=.04):
    """Place mandatory tread/landing supports before filling each straight span."""
    indices = flight_post_steps(stairs['step_count'], every_steps, step_mode)
    spacing = stairs['tread'] * every_steps if landing_auto else landing_spacing
    if spacing <= EPSILON:
        raise ValueError('Landing Post Spacing must be positive')
    x = side * (stairs['width'] / 2 - inset)
    candidates = []
    for frame in frames:
        for step in indices:
            target = frame @ Vector((x, -(step + .5) * stairs['tread'], (step + .5) * stairs['riser']))
            base = frame @ Vector((x, -(step + .5) * stairs['tread'], (step + 1) * stairs['riser']))
            candidates.append((base, target, step in (0, stairs['step_count'] - 1), 3))
    inner = 1 if stairs['turn_direction'] == 'RIGHT' else -1
    minimum = post_size * 1.8 + .005
    for landing in landings:
        route = _trim_path(_landing_route(stairs, landing, side, inset, corner_length),
                           0, stairs['tread'] / 2)
        tight_gap = side == inner and stairs['flight_gap'] < max(2 * inset, post_size * 3.6)
        for index, point in enumerate(route):
            if index in (0, len(route) - 1) or not tight_gap:
                candidates.append((point, point, True, 3 if index == len(route) - 1 else 2 if index == 0 else 1))
        if tight_gap:
            continue
        for start, end in zip(route, route[1:]):
            length = (end - start).length
            intervals = max(1, min(floor(length / spacing + .5), floor(length / minimum)))
            for index in range(1, intervals):
                point = start.lerp(end, index / intervals)
                candidates.append((point, point, False, 0))
    placed = {}
    for base, point, mandatory, priority in candidates:
        located = _locate(point, path, prefer_flat=abs(base.z - point.z) <= EPSILON)
        if located is None:
            continue
        target, segment, distance = located
        key = tuple(round(value, 6) for value in target)
        if key not in placed or priority > placed[key][1]:
            placed[key] = (distance, priority, PostPlacement(base, target, segment, mandatory))
    # A nearby landing start or elbow can be served by the tread/transition
    # support already there. Keep exact tread spacing and the upper-flight anchor.
    clearance = max(stairs['tread'] / 2, post_size * 1.8 + .005)
    kept = []
    for distance, priority, placement in sorted(placed.values(), key=lambda item: (-item[1], item[0])):
        if priority < 3 and any(abs(placement.base.z - other.base.z) < EPSILON
                                and (placement.base - other.base).xy.length <= clearance + EPSILON
                                for _, other in kept):
            continue
        kept.append((distance, placement))
    return [placement for _, placement in sorted(kept, key=lambda item: item[0])]


def post_bounded_rail_path(path, posts, start_setback=0.0, end_setback=0.0):
    """Keep a lower member inside the first/last actual supports on this route."""
    stations = [located[2] for post in posts if (located := _locate(post, path, horizontal=False)) is not None]
    if len(stations) < 2:
        return []
    length = sum((end - start).length for start, end in zip(path, path[1:]))
    start = max(min(stations), start_setback)
    end = max(length - max(stations), end_setback)
    if length - start - end <= EPSILON:
        return []
    return _trim_path(path, start, end)


def fixed_bay_infill(path, posts, spacing, post_size, depth, dense=False):
    """Center a fixed-pitch infill group in every bay, leaving residual end gaps."""
    if spacing <= depth:
        raise ValueError('Baluster Spacing must be greater than Baluster Depth')
    distances = sorted({round(located[2], 8) for post in posts
                        if (located := _locate(post, path)) is not None})
    segments = []
    station = 0.0
    for start, end in zip(path, path[1:]):
        length = (end - start).xy.length
        segments.append((start, end, station, station + length))
        station += length
    margin = (post_size + depth) / 2 + .005
    result = []
    for start_distance, end_distance in zip(distances, distances[1:]):
        length = end_distance - start_distance
        if length < 2 * margin - EPSILON:
            continue
        count = floor((length - 2 * margin + EPSILON) / spacing) + (1 if dense else 0)
        if count <= 0:
            continue
        first = start_distance + (length - (count - 1) * spacing) / 2
        for index in range(count):
            distance = first + index * spacing
            for start, end, low, high in segments:
                if low - EPSILON <= distance <= high + EPSILON:
                    result.append((start.lerp(end, (distance - low) / (high - low)), (start, end)))
                    break
    return result
