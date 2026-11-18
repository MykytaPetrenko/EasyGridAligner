"""Type 2: square posts, rectangular handrails and fixed one-piece corner fittings."""
from math import cos, pi, sin

import bpy
from mathutils import Vector

from .stairs import _flight_layout
from .railing_parts import _append_tube, _clean_path, _closest_on_path, _make_mesh, _railing_route


EPSILON = 1e-6


def _rect_axes(direction):
    width = Vector((-direction.y, direction.x, 0))
    if width.length < EPSILON:
        width = Vector((1, 0, 0))
    width.normalize()
    return width, direction.cross(width).normalized()


def _rect_offsets(direction, width, thickness, vertical_offset=0.0):
    horizontal, vertical = _rect_axes(direction)
    return [horizontal * x * width / 2 + vertical * (y * thickness / 2 + vertical_offset)
            for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def _append_loft(part, rings, smooth_sides=False):
    vertices, faces, smooth = part
    offset, sides = len(vertices), len(rings[0])
    for ring in rings:
        vertices.extend(tuple(point) for point in ring)
    faces.append(tuple(offset + side for side in reversed(range(sides))))
    smooth.append(False)
    for index in range(len(rings) - 1):
        for side in range(sides):
            following = (side + 1) % sides
            faces.append((offset + index * sides + side, offset + index * sides + following,
                          offset + (index + 1) * sides + following, offset + (index + 1) * sides + side))
            smooth.append(smooth_sides)
    faces.append(tuple(offset + (len(rings) - 1) * sides + side for side in range(sides)))
    smooth.append(False)
    return offset


def _corner_geometry(previous, point, following, width, thickness, radius, sides, vertical_offset=0.0):
    incoming = (point - previous).normalized()
    outgoing = (following - point).normalized()
    normal = incoming + outgoing
    if normal.length < EPSILON:
        raise ValueError('A fixed corner connector cannot reverse direction; increase landing space')
    normal.normalize()
    denominator = incoming.dot(normal)
    if denominator <= EPSILON:
        raise ValueError('The fixed corner angle is too tight')
    if radius is None:
        first = _rect_offsets(incoming, width, thickness, vertical_offset)
        last = _rect_offsets(outgoing, width, thickness, vertical_offset)
        middle = []
        for start_offset, end_offset in zip(first, last):
            a = start_offset - incoming * start_offset.dot(normal) / denominator
            b = end_offset - outgoing * end_offset.dot(normal) / outgoing.dot(normal)
            middle.append((a + b) / 2)
    else:
        axis = Vector((0, 0, 1)) if abs(incoming.z) < .9 else Vector((1, 0, 0))
        u = incoming.cross(axis).normalized()
        v = incoming.cross(u).normalized()
        rotation = incoming.rotation_difference(outgoing)
        first = [radius * (u * cos(2 * pi * index / sides) + v * sin(2 * pi * index / sides))
                 for index in range(sides)]
        last = [rotation @ offset for offset in first]
        middle = [offset - incoming * offset.dot(normal) / denominator for offset in first]
    required = max(max(abs(offset.dot(incoming)), abs(offset.dot(outgoing))) for offset in middle) + .001
    return incoming, outgoing, first, middle, last, required


def _append_fixed_rail(straight_part, corner_part, points, width, thickness,
                        radius, sides, corner_length, allowance):
    """Trim straight members at the fitting ends; make one solid per corner."""
    points = _clean_path(points)
    corners, sharp_rings = [], []
    for previous, point, following in zip(points, points[1:], points[2:]):
        data = _corner_geometry(previous, point, following, width + 2 * allowance,
                                thickness + 2 * allowance,
                                radius + allowance if radius is not None else None, sides)
        incoming, outgoing, first, middle, last, required = data
        available = .4 * min((point - previous).length, (following - point).length)
        if available <= required:
            raise ValueError('Not enough room for a fixed corner connector; increase Edge Inset or landing space, or reduce the section size')
        distance = min(max(corner_length, required), available)
        start, end = point - incoming * distance, point + outgoing * distance
        rings = ([start + offset for offset in first], [point + offset for offset in middle],
                 [end + offset for offset in last])
        offset = _append_loft(corner_part, rings, smooth_sides=radius is not None)
        if radius is not None:
            sharp_rings.extend(tuple(sorted((offset + sides + index, offset + sides + (index + 1) % sides)))
                               for index in range(sides))
        corners.append((start, end))
    cursor = points[0]
    segments = []
    for start, end in corners:
        segments.append((cursor, start))
        cursor = end
    segments.append((cursor, points[-1]))
    for start, end in segments:
        if (end - start).length <= EPSILON:
            continue
        if radius is None:
            offsets = _rect_offsets((end - start).normalized(), width, thickness)
            _append_loft(straight_part, ([start + offset for offset in offsets],
                                        [end + offset for offset in offsets]))
        else:
            _append_tube(straight_part, (start, end), radius, sides)
    return sharp_rings


def _append_square_post(part, center, profile):
    vertices, faces, smooth = part
    offset = len(vertices)
    for height, size in profile:
        vertices.extend((center.x + x * size / 2, center.y + y * size / 2, height)
                        for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)))
    faces.append(tuple(offset + index for index in (3, 2, 1, 0)))
    smooth.append(False)
    for ring in range(len(profile) - 1):
        for index in range(4):
            following = (index + 1) % 4
            faces.append((offset + ring * 4 + index, offset + ring * 4 + following,
                          offset + (ring + 1) * 4 + following, offset + (ring + 1) * 4 + index))
            smooth.append(False)
    faces.append(tuple(offset + (len(profile) - 1) * 4 + index for index in range(4)))
    smooth.append(False)


def build_rectangular_railing_meshes(
    stairs, rail_left=True, rail_right=True, rail_outer_enabled=True,
    rail_height=1.05, rail_inset=.08, rail_handrail_width=.05, rail_handrail_thickness=.025,
    rail_post_size=.04, rail_corner_length=.06, rail_corner_allowance=.002,
    rail_lower_count=4, rail_lower_radius=.008, rail_lower_clearance=.12, rail_lower_segments=8,
    rail_post_spacing=.9, rail_connector_radius=.008, rail_connector_length=.07,
    rail_connector_mode='SEPARATE', rail_connector_segments=8, rail_connector_match_post=False,
    handrail_only=False,
):
    if min(rail_handrail_width, rail_handrail_thickness, rail_post_size, rail_corner_length) <= EPSILON:
        raise ValueError('Handrail, post and corner connector dimensions must be positive')
    if rail_corner_allowance < 0:
        raise ValueError('Corner connector allowance cannot be negative')
    if rail_inset < max(rail_handrail_width / 2 + rail_corner_allowance, 0 if handrail_only else rail_post_size * .8):
        raise ValueError('Edge Inset must keep the rectangular handrail and post bases inside the stair edge')
    if 2 * (rail_inset + rail_handrail_width / 2 + rail_corner_allowance) >= stairs['width']:
        raise ValueError('The stairs are too narrow for the rectangular railing section')
    if not handrail_only and rail_connector_radius >= rail_post_size / 2:
        raise ValueError('The handrail support stem must be thinner than the square post')
    if rail_connector_mode not in ('SEPARATE', 'INTEGRATED'):
        raise ValueError('Choose Separate Support or Integral Stem')
    if not handrail_only and rail_height <= stairs['riser'] / 2 + rail_handrail_thickness / 2 + rail_connector_length + .03:
        raise ValueError('Railing Height leaves no room for the square posts and supports')
    if rail_lower_count and rail_lower_clearance >= rail_height - .1:
        raise ValueError('Infill Clearance must be below the handrail')
    support_sides = 4 if rail_connector_match_post else rail_connector_segments
    if min(support_sides, rail_lower_segments) < 3:
        raise ValueError('Circular sections must have at least three sides')
    frames, landings = _flight_layout(
        stairs['flight_count'], stairs['step_count'], stairs['width'], stairs['riser'], stairs['tread'],
        stairs['turn_angle'], stairs['turn_direction'], stairs['landing_depth'], stairs['flight_gap'],
        stairs['landing_side_overhang'], stairs['landing_end_overhang'])
    parts = {name: ([], [], []) for name in ('handrail', 'lower_rails', 'posts', 'connectors',
                                          'handrail_corners', 'infill_corners')}
    sharp_infill_rings = []
    inner_side = 1 if stairs['turn_direction'] == 'RIGHT' else -1
    for side, enabled in ((-1, rail_left), (1, rail_right)):
        if not enabled or (stairs['flight_count'] > 1 and not rail_outer_enabled and side != inner_side):
            continue
        controls, bases = _railing_route(stairs, frames, landings, side, rail_inset,
                                         rail_corner_length, rail_post_spacing)
        path = [point + Vector((0, 0, rail_height)) for point in controls]
        _append_fixed_rail(parts['handrail'], parts['handrail_corners'], path,
                            rail_handrail_width, rail_handrail_thickness, None, 4,
                            rail_corner_length, rail_corner_allowance)
        if handrail_only:
            continue
        for index in range(rail_lower_count):
            height = rail_lower_clearance + (rail_height - .1 - rail_lower_clearance) * (index + 1) / (rail_lower_count + 1)
            lower = [point + Vector((0, 0, height - rail_height)) for point in path]
            sharp_infill_rings.extend(_append_fixed_rail(
                parts['lower_rails'], parts['infill_corners'], lower, 0, 0,
                rail_lower_radius, rail_lower_segments, rail_corner_length, rail_corner_allowance))
        placed = []
        for base in bases:
            if any((base - previous).length < .2 for previous in placed):
                continue
            placed.append(base)
            target = _closest_on_path(base + Vector((0, 0, rail_height - stairs['riser'] / 2)), path)
            top_z = target.z - rail_handrail_thickness / 2 - rail_connector_length
            if top_z <= base.z + .025:
                raise ValueError('Railing Height leaves no room for a post at this landing')
            flange_top = base.z + .012
            collar_height = min(.014, (top_z - flange_top) * .4)
            profile = [(base.z, rail_post_size * 1.6), (flange_top, rail_post_size * 1.6),
                       (flange_top, rail_post_size), (top_z - collar_height, rail_post_size),
                       (top_z - collar_height, rail_post_size * 1.08), (top_z, rail_post_size * 1.08)]
            stem_end = target.z - rail_handrail_thickness * .35
            if rail_connector_mode == 'INTEGRATED':
                profile.extend(((top_z, rail_connector_radius * 2), (stem_end, rail_connector_radius * 2)))
            else:
                _append_tube(parts['connectors'], (Vector((target.x, target.y, top_z)),
                                                   Vector((target.x, target.y, stem_end))),
                             rail_connector_radius, support_sides)
            _append_square_post(parts['posts'], target, profile)
    meshes = {}
    try:
        for name, part in parts.items():
            if part[1]:
                meshes[name] = _make_mesh(f'Stairs {name.replace("_", " ").title()}', part)
        if 'infill_corners' in meshes:
            sharp = set(sharp_infill_rings)
            for edge in meshes['infill_corners'].edges:
                if tuple(sorted(edge.vertices)) in sharp:
                    edge.use_edge_sharp = True
    except Exception:
        # _make_mesh owns its own failed allocation; clean up completed parts.
        for mesh in meshes.values():
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
    return meshes
