"""Shared stair-railing paths and geometry primitives."""
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
            points.extend(((x, y - near_depth), (outer_x, y - near_depth), (outer_x, bridge_y),
                           (next_outer_x, bridge_y), (next_outer_x, y - near_depth),
                           (next_x, y - near_depth)))
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
            points.extend(((x, y - near_depth), (outer_x, y - near_depth), (outer_x, bridge_y)))
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


def _closest_on_path(point, path, with_segment=False):
    best, best_segment, distance = None, None, float('inf')
    for start, end in zip(path, path[1:]):
        delta = end - start
        factor = max(0.0, min(1.0, (point - start).dot(delta) / delta.length_squared))
        candidate = start + factor * delta
        candidate_distance = (point - candidate).length_squared
        if candidate_distance < distance:
            best, distance = candidate, candidate_distance
            best_segment = (start, end)
    return (best, best_segment) if with_segment else best


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


