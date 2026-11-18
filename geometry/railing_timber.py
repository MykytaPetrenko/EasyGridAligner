"""Timber cap boards, mitered expansion joints and independently beveled edge groups."""
from math import ceil

import bmesh

from .railings_rectangular import _append_loft, _rect_offsets
from .finish_shading import FinishShading


EPSILON = 1e-6
SIDE, TOP, BOTTOM, START, END = 1, 2, 3, 4, 5


def _board_rings(points, rings, width, thickness, maximum_length, gap):
    """One board per straight run, subdividing long runs and insetting each joint plane."""
    if maximum_length <= EPSILON or gap < 0:
        raise ValueError('Board Length must be positive and Joint Gap cannot be negative')
    boards = []
    for run, (start, end) in enumerate(zip(points, points[1:])):
        delta = end - start
        direction, length = delta.normalized(), delta.length
        count = max(1, ceil(length / maximum_length))
        offsets = _rect_offsets(direction, width, thickness)
        for index in range(count):
            first = ([point.copy() for point in rings[run]] if index == 0 else
                     [start + delta * (index / count) + offset for offset in offsets])
            last = ([point.copy() for point in rings[run + 1]] if index == count - 1 else
                    [start + delta * ((index + 1) / count) + offset for offset in offsets])
            for ring, sign, is_joint in ((first, 1, run > 0 or index > 0),
                                          (last, -1, run < len(points) - 2 or index < count - 1)):
                if is_joint and gap > 0:
                    normal = (ring[1] - ring[0]).cross(ring[3] - ring[0]).normalized()
                    projection = abs(normal.dot(direction))
                    if projection <= EPSILON:
                        raise ValueError('Invalid timber joint plane')
                    shift = direction * (sign * gap / (2 * projection))
                    for point in ring:
                        point += shift
            remaining = sum((b - a).dot(direction) for a, b in zip(first, last)) / 4
            if remaining <= EPSILON:
                raise ValueError('Joint Gap leaves no board length; reduce the gap or increase Board Length')
            boards.append([first, last])
    return boards


def _append_beveled_board(part, rings, bevels, segments, profile, smooth, sharp_edges):
    source = ([], [], [])
    _append_loft(source, rings)
    bm = bmesh.new()
    try:
        vertices = [bm.verts.new(point) for point in source[0]]
        layer = bm.faces.layers.int.new('cap_surface')
        last_face = len(source[1]) - 1
        for index, indices in enumerate(source[1]):
            face = bm.faces.new([vertices[i] for i in indices])
            face[layer] = (START if index == 0 else END if index == last_face else
                           (BOTTOM, SIDE, TOP, SIDE)[(index - 1) % 4])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        shading = FinishShading(bm, smooth)
        active_surfaces = {surface for surface, enabled, width in bevels if enabled}
        excluded = ({BOTTOM} if TOP in active_surfaces and BOTTOM not in active_surfaces else
                    {TOP} if BOTTOM in active_surfaces and TOP not in active_surfaces else set())
        for surface, enabled, width in bevels:
            if not enabled or width <= EPSILON:
                continue
            bm.normal_update()
            selected = []
            for edge in bm.edges:
                if len(edge.link_faces) != 2 or edge.calc_face_angle(0.0) < .0001:
                    continue
                tags = {face[layer] for face in edge.link_faces}
                if ((surface in (TOP, BOTTOM) and surface in tags and SIDE in tags)
                        or (surface in (START, END) and surface in tags and not tags & excluded)):
                    selected.append(edge)
            if selected:
                result = shading.bevel(
                    selected, offset=width, segments=segments, profile=profile,
                    clamp_overlap=True, loop_slide=True)
                for face in result['faces']:
                    face[layer] = 0
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        shading.apply()
        bm.verts.index_update()
        offset = len(part[0])
        part[0].extend(tuple(vertex.co) for vertex in bm.verts)
        for face in bm.faces:
            part[1].append(tuple(offset + vertex.index for vertex in face.verts))
            part[2].append(face.smooth)
        sharp_edges.extend(tuple(sorted(offset + vertex.index for vertex in edge.verts))
                           for edge in bm.edges if not edge.smooth)
    finally:
        bm.free()


def append_timber_cap(part, points, rings, width, thickness,
                       split=False, maximum_length=2.0, gap=.003,
                       bevel_top=False, bevel_bottom=False, bevel_ends=False,
                       top_width=.002, bottom_width=.002, ends_width=.002,
                       bevel_segments=3, bevel_profile=.5, smooth=True, sharp_edges=None):
    pieces = _board_rings(points, rings, width, thickness, maximum_length, gap) if split else [rings]
    bevels = [(surface, enabled, min(amount, min(width, thickness) * .49)) for surface, enabled, amount in (
        (TOP, bevel_top, top_width), (BOTTOM, bevel_bottom, bottom_width),
        (START, bevel_ends, ends_width), (END, bevel_ends, ends_width))]
    sharp_edges = sharp_edges if sharp_edges is not None else []
    for piece in pieces:
        _append_beveled_board(part, piece, bevels, bevel_segments, bevel_profile, smooth, sharp_edges)
