"""Type 3: metal balusters and base rail under a contrasting continuous handrail."""
from math import ceil, sqrt

import bpy
from mathutils import Vector

from .railing_parts import _clean_path, _closest_on_path, _extend_path, _make_mesh, _railing_route, _trim_path
from .railing_timber import append_timber_cap
from .railings_rectangular import _append_loft, _corner_geometry, _rect_offsets
from .stairs import _flight_layout


EPSILON = 1e-6
UP = Vector((0, 0, 1))


def _mitered_bar_rings(points, width, thickness, vertical_offset=0.0):
    points = _clean_path(points)
    first = _rect_offsets((points[1] - points[0]).normalized(), width, thickness, vertical_offset)
    rings = [[points[0] + offset for offset in first]]
    for previous, point, following in zip(points, points[1:], points[2:]):
        data = _corner_geometry(previous, point, following, width, thickness, None, 4, vertical_offset)
        if data[-1] >= .49 * min((point - previous).length, (following - point).length):
            raise ValueError('Not enough room for the handrail/base rail miter; increase landing space or reduce the section size')
        rings.append([point + offset for offset in data[3]])
    last = _rect_offsets((points[-1] - points[-2]).normalized(), width, thickness, vertical_offset)
    rings.append([points[-1] + offset for offset in last])
    return rings


def _append_mitered_bar(part, points, width, thickness, vertical_offset=0.0):
    """A continuous rectangular member, with shared miter rings and only two caps."""
    _append_loft(part, _mitered_bar_rings(points, width, thickness, vertical_offset))


def _upright_ring(center, across, along, width, depth, height, gradient=None):
    gradient = gradient if gradient is not None else Vector((0, 0, 0))
    ring = []
    for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        offset = across * (x * width / 2) + along * (y * depth / 2)
        point = Vector((center.x + offset.x, center.y + offset.y, height + gradient.dot(offset)))
        ring.append(point)
    return ring


def _segment_axes(start, end):
    delta = end - start
    along = Vector((delta.x, delta.y, 0)).normalized()
    across = UP.cross(along)
    gradient = along * (delta.z / Vector((delta.x, delta.y, 0)).length)
    scale = sqrt(1 + gradient.length_squared)
    return across, along, gradient, scale


def build_baluster_railing_meshes(
    stairs, rail_left=True, rail_right=True, rail_outer_enabled=True,
    rail_height=1.05, rail_inset=.08, rail_post_spacing=.9, rail_post_size=.04,
    rail_type3_handrail_width=.065, rail_type3_handrail_thickness=.04,
    rail_baluster_spacing=.12, rail_baluster_width=.016, rail_baluster_depth=.025,
    rail_base_rail_width=.03, rail_base_rail_height=.035, rail_base_clearance=.05,
    rail_top_rail_height=.015,
    rail_corner_length=.06, handrail_only=False,
    rail_start_extension=.05, rail_end_extension=.05,
    rail_infill_start_setback=.05, rail_infill_end_setback=.05, cap_options=None,
):
    dimensions = (rail_type3_handrail_width, rail_type3_handrail_thickness)
    if min(dimensions) <= EPSILON:
        raise ValueError('Handrail dimensions must be positive')
    if rail_top_rail_height <= EPSILON or rail_top_rail_height >= rail_base_rail_height:
        raise ValueError('Top Rail Thickness must be positive and smaller than Bottom Rail Thickness')
    if rail_base_rail_width <= EPSILON or rail_base_rail_width > rail_type3_handrail_width:
        raise ValueError('The metal rail width must fit beneath the handrail')
    if rail_inset < max(rail_type3_handrail_width / 2, 0 if handrail_only else rail_post_size * .9):
        raise ValueError('Edge Inset must keep the handrail and post base plates inside the stair edge')
    if 2 * (rail_inset + rail_type3_handrail_width / 2) >= stairs['width']:
        raise ValueError('The stairs are too narrow for this handrail width and inset')
    base_offset = stairs['riser'] + rail_base_clearance + rail_base_rail_height / 2
    if not handrail_only:
        if min(rail_baluster_spacing, rail_baluster_width, rail_baluster_depth,
               rail_base_rail_width, rail_base_rail_height, rail_post_size) <= EPSILON or rail_base_clearance < 0:
            raise ValueError('Metal section sizes and spacing must be positive; Bottom Clearance cannot be negative')
        if rail_baluster_spacing <= rail_baluster_depth:
            raise ValueError('Baluster Spacing must be greater than Baluster Depth')
        if rail_baluster_width > min(rail_base_rail_width, rail_type3_handrail_width):
            raise ValueError('Baluster Width must fit inside the handrail and bottom rail widths')
        scale = sqrt(1 + (stairs['riser'] / stairs['tread']) ** 2)
        if rail_height - (rail_type3_handrail_thickness / 2 + rail_top_rail_height) * scale <= base_offset + rail_base_rail_height * scale / 2 + .05:
            raise ValueError('Railing Height leaves no room for the vertical balusters')
    frames, landings = _flight_layout(
        stairs['flight_count'], stairs['step_count'], stairs['width'], stairs['riser'], stairs['tread'],
        stairs['turn_angle'], stairs['turn_direction'], stairs['landing_depth'], stairs['flight_gap'],
        stairs['landing_side_overhang'], stairs['landing_end_overhang'])
    wood, metal = ([], [], []), ([], [], [])
    wood_sharp_edges = []
    inner = 1 if stairs['turn_direction'] == 'RIGHT' else -1
    for side, enabled in ((-1, rail_left), (1, rail_right)):
        if not enabled or (stairs['flight_count'] > 1 and not rail_outer_enabled and side != inner):
            continue
        route, bases = _railing_route(stairs, frames, landings, side, rail_inset,
                                         rail_corner_length, rail_post_spacing)
        cap_path = [point + UP * rail_height for point in _extend_path(route, rail_start_extension, rail_end_extension)]
        cap_rings = _mitered_bar_rings(cap_path, rail_type3_handrail_width, rail_type3_handrail_thickness)
        append_timber_cap(wood, cap_path, cap_rings, rail_type3_handrail_width, rail_type3_handrail_thickness,
                          smooth=stairs.get('use_smooth_shading', True), sharp_edges=wood_sharp_edges,
                          **(cap_options or {}))
        controls = _trim_path(route, rail_infill_start_setback, rail_infill_end_setback)
        # Offset within the cross-section, perpendicular to each run. This
        # shares the timber underside plane on slopes and at mitered turns.
        _append_mitered_bar(metal, [point + UP * rail_height for point in controls],
                            rail_base_rail_width, rail_top_rail_height,
                            -(rail_type3_handrail_thickness + rail_top_rail_height) / 2)
        if handrail_only:
            continue
        _append_mitered_bar(metal, [point + UP * base_offset for point in controls],
                            rail_base_rail_width, rail_base_rail_height)
        # Posts anchor to actual tread tops. Add corner posts on flat landings.
        for previous, point, following in zip(controls, controls[1:], controls[2:]):
            if abs(previous.z - point.z) < EPSILON and abs(following.z - point.z) < EPSILON:
                bases.append(point)
        post_centers = []
        for base in bases:
            target, segment = _closest_on_path(base - UP * stairs['riser'] / 2, controls, with_segment=True)
            original_target = _closest_on_path(base - UP * stairs['riser'] / 2, route)
            if (target - original_target).length > EPSILON:
                continue
            if any((target - existing).length < max(.1, rail_post_size * 2) for existing in post_centers):
                continue
            post_centers.append(target)
            across, along, gradient, scale = _segment_axes(*segment)
            # Wide posts reach the metal top rail's upper plane; thin balusters stop below it.
            top = target.z + rail_height - rail_type3_handrail_thickness * scale / 2
            if top <= base.z + .025:
                raise ValueError('Railing Height leaves no room for a supporting post')
            flange_top = base.z + .012
            rings = [_upright_ring(target, across, along, width, width, height, slope)
                     for width, height, slope in (
                         (rail_post_size * 1.8, base.z, None),
                         (rail_post_size * 1.8, flange_top, None),
                         (rail_post_size, flange_top, None), (rail_post_size, top, gradient))]
            _append_loft(metal, rings)
        for start, end in zip(controls, controls[1:]):
            across, along, gradient, scale = _segment_axes(start, end)
            length = Vector((end.x - start.x, end.y - start.y, 0)).length
            count = max(1, ceil(length / rail_baluster_spacing))
            margin = max(rail_baluster_depth, rail_type3_handrail_width) / 2 + .005
            for index in range(count):
                distance = length * (index + .5) / count
                if distance < margin or length - distance < margin:
                    continue
                center = start.lerp(end, distance / length)
                if any(Vector((center.x - post.x, center.y - post.y, 0)).length
                       < (rail_post_size + rail_baluster_depth) / 2 + .005 for post in post_centers
                       if abs(center.z - post.z) < stairs['riser']):
                    continue
                bottom = center.z + base_offset + rail_base_rail_height * scale / 2
                top = center.z + rail_height - (rail_type3_handrail_thickness / 2 + rail_top_rail_height) * scale
                _append_loft(metal, [_upright_ring(center, across, along, rail_baluster_width,
                                                  rail_baluster_depth, height, gradient)
                                    for height in (bottom, top)])
    if not wood[1]:
        return {}
    vertices, faces, smooth = wood
    wood_faces, offset = len(faces), len(vertices)
    vertices.extend(metal[0])
    faces.extend(tuple(index + offset for index in face) for face in metal[1])
    smooth.extend(metal[2])
    mesh = _make_mesh('Stairs Vertical Baluster Railing', wood, sharp_edges=wood_sharp_edges)
    try:
        for face in mesh.polygons:
            face.material_index = 1 if face.index < wood_faces else 0
        return {'balustrade': mesh}
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
