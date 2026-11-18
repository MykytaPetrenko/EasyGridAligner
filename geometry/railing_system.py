"""Independent inner/outer mounting and landing coverage for all railing styles."""
from inspect import signature

import bmesh
import bpy
from mathutils import Matrix

from .railings import build_railing_meshes
from .railing_parts import _make_mesh, _railing_route, _trim_path
from .railing_wall import append_preview_wall, append_wall_mounts
from .stairs import _flight_layout


RAIL_DEFAULTS = {name: parameter.default for name, parameter in signature(build_railing_meshes).parameters.items()
                 if name not in ('stairs', 'handrail_only')}


def _merge_parts(batches):
    merged, created, success = {}, [], False
    try:
        names = {name for _, batch in batches for name in batch}
        for name in names:
            entries = [(frame, batch[name]) for frame, batch in batches if name in batch]
            if len(entries) == 1:
                frame, mesh = entries[0]
                mesh.transform(frame)
                merged[name] = mesh
                continue
            bm = bmesh.new()
            mesh = bpy.data.meshes.new(f'Stairs {name.replace("_", " ").title()}')
            created.append(mesh)
            merged[name] = mesh
            try:
                for frame, source in entries:
                    source.transform(frame)
                    bm.from_mesh(source)
                bm.to_mesh(mesh)
                mesh.update()
            finally:
                bm.free()
        success = True
        return merged
    except Exception:
        for mesh in created:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
    finally:
        kept = {mesh.as_pointer() for mesh in merged.values()} if success else set()
        for _, batch in batches:
            for mesh in batch.values():
                if mesh.as_pointer() not in kept and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)


def build_railing_system_meshes(
    stairs, rail_inner_mount='FLIGHT', rail_outer_mount='FLIGHT',
    rail_inner_include_landings=True, rail_outer_include_landings=True,
    rail_wall_clearance=.05, rail_wall_bracket_spacing=.9, rail_wall_plate_radius=.035,
    rail_preview_walls=False, rail_preview_wall_thickness=.15, rail_preview_wall_extra_height=.25,
    **rail_parameters,
):
    modes = (rail_inner_mount, rail_outer_mount)
    rail_parameters = RAIL_DEFAULTS | rail_parameters
    if any(mode not in ('NONE', 'FLIGHT', 'WALL') for mode in modes):
        raise ValueError('Choose None, Flight Mounted or Wall Mounted for each side')
    if modes == ('NONE', 'NONE'):
        return {}
    if 'WALL' in modes:
        if rail_wall_clearance < .02:
            raise ValueError('Wall Clearance must be at least 20 mm')
        if rail_wall_bracket_spacing <= 0 or rail_wall_plate_radius <= 0:
            raise ValueError('Wall bracket spacing and mounting plate radius must be positive')
        if rail_preview_wall_thickness <= 0 or rail_preview_wall_extra_height < 0:
            raise ValueError('Preview wall thickness must be positive and extra height cannot be negative')
    frames, landings = _flight_layout(
        stairs['flight_count'], stairs['step_count'], stairs['width'], stairs['riser'], stairs['tread'],
        stairs['turn_angle'], stairs['turn_direction'], stairs['landing_depth'], stairs['flight_gap'],
        stairs['landing_side_overhang'], stairs['landing_end_overhang'])
    inner = 1 if stairs['turn_direction'] == 'RIGHT' else -1
    batches = []
    wall_parts = {name: ([], [], []) for name in ('wall_brackets', 'wall_mount_plates', 'preview_walls')}
    try:
        for side, mode, include in ((inner, rail_inner_mount, rail_inner_include_landings),
                                    (-inner, rail_outer_mount, rail_outer_include_landings)):
            if mode == 'NONE':
                continue
            parameters = dict(rail_parameters, rail_left=side == -1, rail_right=side == 1,
                              rail_outer_enabled=True)
            wall = mode == 'WALL'
            if wall:
                rectangular = parameters['rail_type'] != 'TYPE_1'
                if parameters['rail_type'] == 'TYPE_4':
                    half_width = parameters['rail_type4_handrail_width'] / 2
                    half_height = parameters['rail_type4_handrail_thickness'] / 2
                elif parameters['rail_type'] == 'TYPE_3':
                    half_width = parameters['rail_type3_handrail_width'] / 2
                    half_height = parameters['rail_type3_handrail_thickness'] / 2 + parameters['rail_top_rail_height']
                else:
                    half_width = parameters['rail_handrail_width'] / 2 if rectangular else parameters['rail_radius']
                    half_height = parameters['rail_handrail_thickness'] / 2 if rectangular else parameters['rail_radius']
                parameters.update(handrail_only=True, rail_lower_count=0,
                                  rail_inset=half_width + rail_wall_clearance)
            sections = [(Matrix.Identity(4), stairs)] if include else [
                (frame, dict(stairs, flight_count=1, railing_start_on_landing=index > 0 and not wall))
                for index, frame in enumerate(frames)]
            for frame, section in sections:
                meshes = build_railing_meshes(section, **parameters)
                if wall:
                    meshes = {f'wall_{name}': mesh for name, mesh in meshes.items()}
                batches.append((frame, meshes))
            if wall:
                radius = parameters['rail_corner_length'] if rectangular else parameters['rail_bend_radius']
                if include:
                    route, _ = _railing_route(stairs, frames, landings, side, parameters['rail_inset'],
                                               radius, rail_wall_bracket_spacing)
                    routes = [route]
                else:
                    routes = [_railing_route(dict(stairs, flight_count=1), [frame], [], side,
                                              parameters['rail_inset'], radius, rail_wall_bracket_spacing)[0]
                              for frame in frames]
                stem_sides = parameters['rail_connector_segments']
                for route in routes:
                    if parameters['rail_type'] == 'TYPE_3':
                        route = _trim_path(route, parameters['rail_infill_start_setback'], parameters['rail_infill_end_setback'])
                    append_wall_mounts(wall_parts, route, side, parameters['rail_height'], half_width,
                                       half_height, rail_wall_clearance, rail_wall_bracket_spacing,
                                       parameters['rail_connector_radius'], stem_sides, rail_wall_plate_radius,
                                       radius, precise_underside=parameters['rail_type'] in ('TYPE_3', 'TYPE_4'))
                if rail_preview_walls:
                    # Trace the actual stair boundary. Offsetting handrail control
                    # rings can collapse the short returns at landing apertures.
                    if include:
                        wall_routes = [_railing_route(stairs, frames, landings, side, 0,
                                                       radius, rail_wall_bracket_spacing)[0]]
                    else:
                        wall_routes = [_railing_route(dict(stairs, flight_count=1), [frame], [], side,
                                                       0, radius, rail_wall_bracket_spacing)[0]
                                       for frame in frames]
                    for wall_route in wall_routes:
                        append_preview_wall(wall_parts['preview_walls'], wall_route, side,
                                            0, rail_preview_wall_thickness,
                                            parameters['rail_height'] + rail_preview_wall_extra_height,
                                            stairs['slab_height'])
        extra = {}
        batches.append((Matrix.Identity(4), extra))
        for name, part in wall_parts.items():
            if part[1]:
                extra[name] = _make_mesh(f'Stairs {name.replace("_", " ").title()}', part)
    except Exception:
        for _, batch in batches:
            for mesh in batch.values():
                bpy.data.meshes.remove(mesh)
        raise
    return _merge_parts(batches)
