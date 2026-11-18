"""Wall brackets and a removable viewport wall along the handrail route."""
from math import ceil

from mathutils import Vector

from .railing_parts import _append_tube, _clean_path, _rounded_path
from .railings_rectangular import _append_loft


EPSILON = 1e-6
UP = Vector((0, 0, 1))


def _outward(start, end, side):
    direction = end - start
    direction.z = 0
    return side * UP.cross(direction).normalized()


def append_wall_mounts(parts, base_route, side, height, section_half_width, section_half_height,
                       clearance, spacing, stem_radius, stem_sides, plate_radius, corner_margin):
    """Place brackets on straight runs, clear of bends and terminating end caps."""
    path = [point + UP * height for point in base_route]
    for segment, (start, end) in enumerate(zip(path, path[1:])):
        length = (end - start).length
        normal = _outward(start, end, side)
        margin = plate_radius + .02
        start_margin = margin + (min(corner_margin, length * .4) if segment > 0 else 0)
        end_margin = margin + (min(corner_margin, length * .4) if segment < len(path) - 2 else 0)
        available = length - start_margin - end_margin
        if available <= EPSILON:
            continue
        count = 1 if available <= spacing else ceil(available / spacing) + 1
        for index in range(count):
            distance = start_margin + available * (index / (count - 1) if count > 1 else .5)
            target = start.lerp(end, distance / length)
            # The small upright ends inside the underside of the handrail.
            tip = target - UP * (section_half_height * .65)
            arm = target - UP * (section_half_height + .065)
            plate_back = arm + normal * (section_half_width + clearance)
            face = plate_back - normal * .006
            _append_tube(parts['wall_mount_plates'], (face, plate_back), plate_radius, max(8, stem_sides))
            raw = (face + normal * .001, arm, tip)
            rounded, _ = _rounded_path(raw, max(.016, stem_radius * 2), 3, stem_radius)
            _append_tube(parts['wall_brackets'], rounded, stem_radius, stem_sides)


def append_preview_wall(part, route, side, offset, thickness, top_height, slab_height):
    """One closed wall strip; adjacent segments share their miter rings."""
    route = _clean_path(route)
    normals = [_outward(start, end, side) for start, end in zip(route, route[1:])]
    rings = []
    for index, point in enumerate(route):
        if index == 0:
            miter = normals[0]
        elif index == len(route) - 1:
            miter = normals[-1]
        else:
            miter = (normals[index - 1] + normals[index]).normalized()
            denominator = miter.dot(normals[index])
            if denominator <= EPSILON:
                raise ValueError('Wall preview cannot reverse direction at a corner')
            miter /= denominator
        inner = point + miter * offset
        outer = point + miter * (offset + thickness)
        rings.append((inner - UP * slab_height, outer - UP * slab_height,
                      outer + UP * top_height, inner + UP * top_height))
    _append_loft(part, rings)
