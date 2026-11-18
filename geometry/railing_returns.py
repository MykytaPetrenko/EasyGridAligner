"""Flat metal handrails with downward half-circle returns at every open end."""
from math import cos, pi, sin

from .railing_parts import _trim_path
from .railings_rectangular import _append_loft, _rect_axes, _rect_offsets


def _return_rings(point, direction, width, thickness, radius, segments, sign):
    if radius <= thickness / 2:
        raise ValueError('End Return Radius must exceed half the handrail thickness')
    if segments < 3:
        raise ValueError('End Return Segments must be at least 3')
    across, normal = _rect_axes(direction)
    rings = []
    for index in range(1, segments + 1):
        angle = pi * index / segments
        center = point + sign * direction * (radius * sin(angle)) + normal * (radius * (cos(angle) - 1))
        vertical = normal * cos(angle) + sign * direction * sin(angle)
        rings.append([center + across * (x * width / 2) + vertical * (y * thickness / 2)
                      for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return rings


def returned_handrail_path(points, width, thickness, radius, segments):
    """Keep each complete end return inside the vertical plane at the route end."""
    trims = []
    for point, direction, sign in ((points[0], (points[1] - points[0]).normalized(), -1),
                                    (points[-1], (points[-1] - points[-2]).normalized(), 1)):
        outward = sign * direction
        horizontal = outward.copy()
        horizontal.z = 0
        horizontal.normalize()
        arc = _return_rings(point, direction, width, thickness, radius, segments, sign)
        section = [point + offset for offset in _rect_offsets(direction, width, thickness)]
        reach = max((vertex - point).dot(horizontal) for ring in [section, *arc] for vertex in ring)
        trims.append(reach / outward.dot(horizontal))
    length = sum((last - first).length for first, last in zip(points, points[1:]))
    if sum(trims) >= length - 1e-6:
        raise ValueError('End Return Radius is too large for this railing section')
    return _trim_path(points, *trims)


def append_returned_handrail(part, points, rings, width, thickness, radius, segments,
                              smooth=True, sharp_edges=None):
    """Share rings between the straight/mitered rail and both tangent end returns."""
    start = _return_rings(points[0], (points[1] - points[0]).normalized(),
                          width, thickness, radius, segments, -1)
    end = _return_rings(points[-1], (points[-1] - points[-2]).normalized(),
                        width, thickness, radius, segments, 1)
    combined = list(reversed(start)) + rings + end
    offset = _append_loft(part, combined, smooth_sides=smooth)
    if sharp_edges is not None:
        # Keep the rectangular section crisp while smoothing across each arc.
        sharp_edges.extend((offset + 4 * i + corner, offset + 4 * (i + 1) + corner)
                           for i in range(len(combined) - 1) for corner in range(4))
        for i in range(1, len(rings) - 1):
            ring = offset + 4 * (segments + i)
            sharp_edges.extend((ring + corner, ring + (corner + 1) % 4) for corner in range(4))
