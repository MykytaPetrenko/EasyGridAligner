"""Railing type dispatch and tubular Type 1 implementation."""
import bpy
from mathutils import Vector

from .stairs import _flight_layout
from .railings_rectangular import build_rectangular_railing_meshes
from .railing_parts import (
    _clean_path,
    _rounded_path,
    _landing_route,
    _sample_route,
    _railing_route,
    _append_tube,
    _append_sleeve,
    _append_post,
    _closest_on_path,
    _make_mesh,
)


EPSILON = 1e-6


def build_railing_meshes(
    stairs, rail_type='TYPE_1', rail_left=True, rail_right=True, rail_height=1.05,
    rail_inset=.08, rail_radius=.025, rail_bend_radius=.09, rail_bend_segments=6,
    rail_segments=16, rail_lower_count=4, rail_lower_radius=.008, rail_lower_clearance=.12,
    rail_post_spacing=.9, rail_post_radius=.018, rail_connector_radius=.008,
    rail_connector_length=.07, rail_coupling_length=.045, rail_coupling_thickness=.006,
    rail_lower_segments=8, rail_post_segments=16, rail_post_match_handrail=True,
    rail_connector_segments=8, rail_connector_match_post=False,
    rail_connector_mode='SEPARATE', rail_outer_enabled=True,
    rail_handrail_width=.05, rail_handrail_thickness=.025, rail_post_size=.04,
    rail_corner_length=.06, rail_corner_allowance=.002,
):
    if rail_type == 'TYPE_2':
        return build_rectangular_railing_meshes(
            stairs, rail_left=rail_left, rail_right=rail_right, rail_outer_enabled=rail_outer_enabled,
            rail_height=rail_height, rail_inset=rail_inset, rail_handrail_width=rail_handrail_width,
            rail_handrail_thickness=rail_handrail_thickness, rail_post_size=rail_post_size,
            rail_corner_length=rail_corner_length, rail_corner_allowance=rail_corner_allowance,
            rail_lower_count=rail_lower_count, rail_lower_radius=rail_lower_radius,
            rail_lower_clearance=rail_lower_clearance, rail_lower_segments=rail_lower_segments,
            rail_post_spacing=rail_post_spacing, rail_connector_radius=rail_connector_radius,
            rail_connector_length=rail_connector_length, rail_connector_mode=rail_connector_mode,
            rail_connector_segments=rail_connector_segments, rail_connector_match_post=rail_connector_match_post)
    if rail_type != 'TYPE_1':
        raise ValueError('Choose railing Type 1 or Type 2')
    if rail_height <= stairs['riser'] / 2 + rail_radius + rail_connector_length + .03:
        raise ValueError('Railing Height is too low for the posts and connectors')
    if rail_inset < max(rail_radius + rail_coupling_thickness, rail_post_radius * 1.8):
        raise ValueError('Railing Inset must keep the tubes and post bases inside the stair edge')
    if 2 * (rail_inset + rail_radius + rail_coupling_thickness) >= stairs['width']:
        raise ValueError('The stairs are too narrow for the selected railing inset and diameter')
    if rail_bend_radius <= rail_radius * 1.05:
        raise ValueError('Elbow Radius must be larger than the handrail tube radius')
    if rail_connector_radius >= rail_post_radius:
        raise ValueError('Connector Radius must be smaller than Post Radius')
    if rail_lower_count and rail_lower_clearance >= rail_height - .1:
        raise ValueError('Lower Rail Clearance must be below the handrail')
    if rail_connector_mode not in ('SEPARATE', 'INTEGRATED'):
        raise ValueError('Choose Separate Support or Integral Stem')
    post_sides = rail_segments if rail_post_match_handrail else rail_post_segments
    support_sides = post_sides if rail_connector_mode == 'INTEGRATED' or rail_connector_match_post else rail_connector_segments
    if min(rail_segments, rail_lower_segments, post_sides, support_sides) < 3:
        raise ValueError('Cylinder cross-sections must have at least three sides')
    frames, landings = _flight_layout(
        stairs['flight_count'], stairs['step_count'], stairs['width'], stairs['riser'], stairs['tread'],
        stairs['turn_angle'], stairs['turn_direction'], stairs['landing_depth'], stairs['flight_gap'],
        stairs['landing_side_overhang'], stairs['landing_end_overhang'])
    parts = {name: ([], [], []) for name in ('handrail', 'lower_rails', 'posts', 'connectors', 'couplings')}
    inner_side = 1 if stairs['turn_direction'] == 'RIGHT' else -1
    for side, enabled in ((-1, rail_left), (1, rail_right)):
        if not enabled or (stairs['flight_count'] > 1 and not rail_outer_enabled and side != inner_side):
            continue
        controls, post_bases = _railing_route(stairs, frames, landings, side, rail_inset,
                                             rail_bend_radius, rail_post_spacing)
        controls = [point + Vector((0, 0, rail_height)) for point in controls]
        path, straights = _rounded_path(controls, rail_bend_radius, rail_bend_segments, rail_radius)
        _append_tube(parts['handrail'], path, rail_radius, rail_segments)
        for start, end, start_joint, end_joint in straights:
            direction, length = (end - start).normalized(), (end - start).length
            sleeve_length = min(rail_coupling_length, length * .4)
            if sleeve_length <= EPSILON:
                continue
            if start_joint:
                _append_sleeve(parts['couplings'], start, start + direction * sleeve_length,
                               rail_radius * .99, rail_radius + rail_coupling_thickness, rail_segments)
            if end_joint:
                _append_sleeve(parts['couplings'], end - direction * sleeve_length, end,
                               rail_radius * .99, rail_radius + rail_coupling_thickness, rail_segments)
        for index in range(rail_lower_count):
            height = rail_lower_clearance + (rail_height - .1 - rail_lower_clearance) * (index + 1) / (rail_lower_count + 1)
            lower = [point + Vector((0, 0, height - rail_height)) for point in path]
            _append_tube(parts['lower_rails'], lower, rail_lower_radius, rail_lower_segments)
        placed = []
        for base in post_bases:
            if any((base - previous).length < .2 for previous in placed):
                continue
            placed.append(base)
            target = _closest_on_path(base + Vector((0, 0, rail_height - stairs['riser'] / 2)), path)
            top_z = target.z - rail_radius - rail_connector_length
            if top_z <= base.z + .025:
                raise ValueError('Railing Height leaves no room for a post at the landing')
            top = Vector((target.x, target.y, top_z))
            neck_end = Vector((target.x, target.y, target.z - rail_radius * .65))
            flange_top = base.z + .012
            collar_height = min(.018, (top_z - flange_top) * .4)
            profile = [(base.z, rail_post_radius * 1.8),
                       (flange_top, rail_post_radius * 1.8),
                       (flange_top, rail_post_radius),
                       (top_z - collar_height, rail_post_radius),
                       (top_z - collar_height, rail_post_radius * 1.12),
                       (top_z, rail_post_radius * 1.12)]
            if rail_connector_mode == 'INTEGRATED':
                profile.extend(((top_z, rail_connector_radius),
                                (neck_end.z, rail_connector_radius)))
            else:
                _append_tube(parts['connectors'], (top, neck_end), rail_connector_radius, support_sides)
            _append_post(parts['posts'], target, profile, post_sides)
    meshes = {}
    try:
        for name, part in parts.items():
            if part[1]:
                meshes[name] = _make_mesh(f'Stairs {name.replace("_", " ").title()}', part)
    except Exception:
        for mesh in meshes.values():
            bpy.data.meshes.remove(mesh)
        raise
    return meshes
