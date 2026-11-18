"""Type 1 tubular railings following stair flights and intermediate landings."""
from math import acos, ceil, cos, floor, pi, sin, tan

import bmesh
import bpy
from mathutils import Quaternion, Vector

from .stairs import _flight_layout


EPSILON = 1e-6


def _clean_path(points):
    result = []
    for point in points:
        point = Vector(point)
        if result and (point - result[-1]).length < EPSILON:
            continue
        while len(result) > 1:
            first = result[-1] - result[-2]
            second = point - result[-1]
            if first.normalized().dot(second.normalized()) < 1 - EPSILON:
                break
            result.pop()
        result.append(point)
    return result


def _rounded_path(points, radius, segments, pipe_radius):
    points = _clean_path(points)
    corners = []
    for previous, point, following in zip(points, points[1:], points[2:]):
        incoming, outgoing = point - previous, following - point
        u, v = incoming.normalized(), outgoing.normalized()
        angle = acos(max(-1.0, min(1.0, u.dot(v))))
        normal = u.cross(v)
        if normal.length < EPSILON:
            raise ValueError('Railing turn reverses direction; increase the landing depth or gap')
        normal.normalize()
        distance = min(radius * tan(angle / 2), .4 * incoming.length, .4 * outgoing.length)
        actual_radius = distance / tan(angle / 2)
        if actual_radius <= pipe_radius * 1.05:
            raise ValueError('Not enough room for the railing elbow; increase landing space or reduce tube diameter')
        start, end = point - u * distance, point + v * distance
        center = start + normal.cross(u) * actual_radius
        steps = max(2, ceil(segments * angle / (pi / 2)))
        arc = [center + Quaternion(normal, angle * index / steps) @ (start - center)
               for index in range(steps + 1)]
        arc[0], arc[-1] = start, end
        corners.append(arc)
    dense, straights = [points[0]], []
    for index, arc in enumerate(corners):
        straights.append((dense[-1].copy(), arc[0].copy(), index > 0, True))
        dense.extend(arc)
    straights.append((dense[-1].copy(), points[-1].copy(), bool(corners), False))
    dense.append(points[-1])
    return _clean_path(dense), straights


def _landing_route(p, landing, side, inset, radius):
    width, gap = p['width'], p['flight_gap']
    length = p['step_count'] * p['tread']
    sign = 1 if p['turn_direction'] == 'RIGHT' else -1
    x = side * (width / 2 - inset)
    y = -length
    low_x, high_x, far_y, _ = landing['bounds']
    near_depth = max(inset, 2 * radius)
    points = [(x, y)]
    inner = side == sign
    if p['turn_angle'] == '180':
        next_x = sign * (width + gap) - x
        bridge_y = max(far_y + inset, y - near_depth) if inner else far_y + inset
        if inner:
            points.extend(((x, bridge_y), (next_x, bridge_y)))
        else:
            outer_x = low_x + inset if side < 0 else high_x - inset
            next_outer_x = high_x - inset if side < 0 else low_x + inset
            points.extend(((outer_x, y - near_depth), (outer_x, bridge_y),
                           (next_outer_x, bridge_y), (next_outer_x, y - near_depth)))
        points.append((next_x, y))
    else:
        next_x = sign * (width / 2 + gap)
        next_y = y - width / 2 - gap + sign * side * (width / 2 - inset)
        if inner:
            if gap > 2 * inset + EPSILON:
                # The gap exposes a rectangular landing projection. Follow
                # its near and outgoing edges instead of cutting across it.
                edge_x = next_x - sign * inset
                edge_y = landing['bounds'][3] - inset
                points.extend(((x, edge_y), (edge_x, edge_y), (edge_x, next_y)))
            else:
                # A projection narrower than the two inset margins collapses
                # to the compact corner route.
                points.append((x, next_y))
        else:
            outer_x = low_x + inset if sign > 0 else high_x - inset
            bridge_y = far_y + inset
            points.extend(((outer_x, y - near_depth), (outer_x, bridge_y)))
            if abs(bridge_y - next_y) > 2 * radius:
                corner_x = next_x - sign * near_depth
                points.extend(((corner_x, bridge_y), (corner_x, next_y)))
        points.append((next_x, next_y))
    height = landing['height']
    return _clean_path([landing['frame'] @ Vector((px, py, height)) for px, py in points])


def _sample_route(points, spacing):
    lengths = [(end - start).length for start, end in zip(points, points[1:])]
    total = sum(lengths)
    count = max(1, ceil(total / spacing))
    result = []
    for index in range(1, count):
        remaining = total * index / count
        for start, end, length in zip(points, points[1:], lengths):
            if remaining <= length:
                result.append(start.lerp(end, remaining / length))
                break
            remaining -= length
    return result


def _railing_route(p, frames, landings, side, inset, radius, spacing):
    x = side * (p['width'] / 2 - inset)
    length, height = p['step_count'] * p['tread'], p['step_count'] * p['riser']
    controls = [frames[0] @ Vector((x, 0, 0))]
    posts = []
    stride = max(1, floor(spacing / Vector((p['tread'], p['riser'])).length))
    for index, frame in enumerate(frames):
        controls.append(frame @ Vector((x, -length, height)))
        steps = sorted(set(range(0, p['step_count'], stride)) | {p['step_count'] - 1})
        for step in steps:
            posts.append(frame @ Vector((x, -(step + .5) * p['tread'], (step + 1) * p['riser'])))
        if index < len(landings):
            route = _landing_route(p, landings[index], side, inset, radius)
            controls.extend(route[1:])
            posts.extend(_sample_route(route, spacing))
    return _clean_path(controls), posts


def _append_tube(part, points, radius, sides):
    vertices, faces, smooth = part
    points = _clean_path(points)
    if len(points) < 2 or (points[-1] - points[0]).length < EPSILON:
        return
    offset = len(vertices)
    previous_u = None
    for index, center in enumerate(points):
        if index == 0:
            tangent = (points[1] - center).normalized()
        elif index == len(points) - 1:
            tangent = (center - points[index - 1]).normalized()
        else:
            tangent = ((center - points[index - 1]).normalized()
                       + (points[index + 1] - center).normalized()).normalized()
        if previous_u is None:
            axis = Vector((0, 0, 1)) if abs(tangent.z) < .9 else Vector((1, 0, 0))
            u = tangent.cross(axis).normalized()
        else:
            u = previous_u - tangent * previous_u.dot(tangent)
            u.normalize()
        v = tangent.cross(u).normalized()
        previous_u = u
        vertices.extend(tuple(center + radius * (u * cos(2 * pi * side / sides)
                                                + v * sin(2 * pi * side / sides)))
                        for side in range(sides))
    faces.append(tuple(offset + index for index in reversed(range(sides))))
    smooth.append(False)
    for ring in range(len(points) - 1):
        for side in range(sides):
            following = (side + 1) % sides
            faces.append((offset + ring * sides + side, offset + ring * sides + following,
                          offset + (ring + 1) * sides + following, offset + (ring + 1) * sides + side))
            smooth.append(True)
    faces.append(tuple(offset + (len(points) - 1) * sides + side for side in range(sides)))
    smooth.append(False)


def _append_sleeve(part, start, end, inner_radius, outer_radius, sides):
    vertices, faces, smooth = part
    direction = (end - start).normalized()
    axis = Vector((0, 0, 1)) if abs(direction.z) < .9 else Vector((1, 0, 0))
    u = direction.cross(axis).normalized()
    v = direction.cross(u).normalized()
    offset = len(vertices)
    for radius in (outer_radius, inner_radius):
        for center in (start, end):
            vertices.extend(tuple(center + radius * (u * cos(2 * pi * side / sides)
                                                     + v * sin(2 * pi * side / sides)))
                            for side in range(sides))
    for side in range(sides):
        following = (side + 1) % sides
        for ring1, ring2, is_smooth in ((0, 1, True), (3, 2, True), (2, 0, False), (1, 3, False)):
            faces.append((offset + ring1 * sides + side, offset + ring1 * sides + following,
                          offset + ring2 * sides + following, offset + ring2 * sides + side))
            smooth.append(is_smooth)


def _append_post(part, center, profile, sides):
    """One closed stepped post: flange, shaft, collar and optional integral stem.

    Adjacent radius changes share rings and annular quads. Only the two ends
    are capped; no cylinder or hidden shaft cap passes through the collar.
    """
    vertices, faces, smooth = part
    offset = len(vertices)
    for height, radius in profile:
        vertices.extend((center.x + radius * cos(2 * pi * side / sides),
                         center.y + radius * sin(2 * pi * side / sides), height)
                        for side in range(sides))
    faces.append(tuple(offset + side for side in reversed(range(sides))))
    smooth.append(False)
    for ring, ((height, _), (next_height, _)) in enumerate(zip(profile, profile[1:])):
        for side in range(sides):
            following = (side + 1) % sides
            faces.append((offset + ring * sides + side, offset + ring * sides + following,
                          offset + (ring + 1) * sides + following, offset + (ring + 1) * sides + side))
            smooth.append(abs(next_height - height) > EPSILON)
    faces.append(tuple(offset + (len(profile) - 1) * sides + side for side in range(sides)))
    smooth.append(False)


def _closest_on_path(point, path):
    best, distance = None, float('inf')
    for start, end in zip(path, path[1:]):
        delta = end - start
        factor = max(0.0, min(1.0, (point - start).dot(delta) / delta.length_squared))
        candidate = start + factor * delta
        candidate_distance = (point - candidate).length_squared
        if candidate_distance < distance:
            best, distance = candidate, candidate_distance
    return best


def _make_mesh(name, part):
    vertices, faces, smooth = part
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        mesh.from_pydata(vertices, [], faces)
        for face, use_smooth in zip(mesh.polygons, smooth):
            face.use_smooth = use_smooth
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        for edge in bm.edges:
            edge.smooth = all(face.smooth for face in edge.link_faces)
        bm.to_mesh(mesh)
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    finally:
        bm.free()
    mesh.update()
    return mesh


def build_railing_meshes(
    stairs, rail_type='TYPE_1', rail_left=True, rail_right=True, rail_height=1.05,
    rail_inset=.08, rail_radius=.025, rail_bend_radius=.09, rail_bend_segments=6,
    rail_segments=16, rail_lower_count=4, rail_lower_radius=.008, rail_lower_clearance=.12,
    rail_post_spacing=.9, rail_post_radius=.018, rail_connector_radius=.008,
    rail_connector_length=.07, rail_coupling_length=.045, rail_coupling_thickness=.006,
    rail_lower_segments=8, rail_post_segments=16, rail_post_match_handrail=True,
    rail_connector_segments=8, rail_connector_match_post=False,
    rail_connector_mode='SEPARATE', rail_outer_enabled=True,
):
    if rail_type != 'TYPE_1':
        raise ValueError('Choose railing Type 1')
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
