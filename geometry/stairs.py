import bmesh
import bpy
from mathutils import Matrix


EPSILON = 0.000001


def _add_vertex(coord, vertices, lookup):
    key = tuple(round(value, 6) for value in coord)
    if key not in lookup:
        lookup[key] = len(vertices)
        vertices.append(coord)
    return lookup[key]


def _add_face(indices, faces, lookup):
    cleaned = []
    for index in indices:
        if not cleaned or cleaned[-1] != index:
            cleaned.append(index)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    if len(cleaned) < 3 or len(set(cleaned)) != len(cleaned):
        return
    key = tuple(sorted(cleaned))
    if key not in lookup:
        lookup.add(key)
        faces.append(cleaned)


def _stair_shell(step_count, width, riser, tread, slab_height, use_side_ribs,
                 rib_width, rib_z_offset, cut_top, riser_offset,
                 open_start=False, open_end=False, plate_thickness=0.0):
    """Triangular steps on one continuous slab, with no internal interfaces."""
    half_width = width / 2
    ribs = use_side_ribs and rib_width > EPSILON and rib_z_offset > EPSILON
    rib_x = (-half_width, -half_width + rib_width, half_width - rib_width, half_width)
    vertices, faces, lookup, face_lookup = [], [], {}, set()

    def vertex(point, x):
        return _add_vertex((x, *point), vertices, lookup)

    for index in range(step_count):
        front, back = -index * tread, -(index + 1) * tread
        base, top = index * riser, (index + 1) * riser
        points = {
            'A': (front, base - slab_height),
            'B': (front, base - plate_thickness if index > 0 or open_start else base),
            'G': (front, base),
            'C': (front + riser_offset * (1 - plate_thickness / riser), top - plate_thickness),
            'D': (back, top - plate_thickness),
            'E': (back, top - slab_height),
        }
        caps = ((('B', 'G', 'D'), ('G', 'C', 'D'), ('A', 'B', 'D', 'E'))
                if plate_thickness > EPSILON else (('B', 'C', 'D'), ('A', 'B', 'D', 'E')))
        for cap in caps:
            _add_face([vertex(points[name], -half_width) for name in cap], faces, face_lookup)
            _add_face([vertex(points[name], half_width) for name in reversed(cap)], faces, face_lookup)

        def surface_vertex(name, x):
            connection = ((open_start and index == 0 and name == 'B')
                          or (open_end and index == step_count - 1 and name == 'D'))
            if ribs and not cut_top and name not in ('A', 'E') and not connection:
                if abs(x - rib_x[1]) <= EPSILON:
                    x = -half_width
                elif abs(x - rib_x[2]) <= EPSILON:
                    x = half_width
            return vertex(points[name], x)

        edges = ([('B', 'G'), ('G', 'C'), ('C', 'D'), ('E', 'A')]
                 if plate_thickness > EPSILON else [('B', 'C'), ('C', 'D'), ('E', 'A')])
        if index == 0 and not open_start:
            edges.append(('A', 'B'))
        if index == step_count - 1 and not open_end:
            edges.append(('D', 'E'))
        for first, second in edges:
            x_values = rib_x if ribs else (-half_width, half_width)
            if ribs and (first, second) == ('E', 'A'):
                x_values = rib_x[1:3]
            for x1, x2 in zip(x_values, x_values[1:]):
                _add_face([surface_vertex(first, x1), surface_vertex(second, x1),
                           surface_vertex(second, x2), surface_vertex(first, x2)], faces, face_lookup)
        if ribs:
            start, end = points['E'], points['A']
            for outer, inner in ((rib_x[0], rib_x[1]), (rib_x[3], rib_x[2])):
                top_ring = [vertex(start, outer), vertex(start, inner), vertex(end, inner), vertex(end, outer)]
                bottom_ring = [vertex((start[0], start[1] - rib_z_offset), outer),
                               vertex((start[0], start[1] - rib_z_offset), inner),
                               vertex((end[0], end[1] - rib_z_offset), inner),
                               vertex((end[0], end[1] - rib_z_offset), outer)]
                _add_face(list(reversed(bottom_ring)), faces, face_lookup)
                for edge_index in range(4):
                    if edge_index == 0 and index < step_count - 1:
                        continue
                    if edge_index == 2 and index > 0:
                        continue
                    next_index = (edge_index + 1) % 4
                    _add_face([top_ring[edge_index], top_ring[next_index],
                               bottom_ring[next_index], bottom_ring[edge_index]], faces, face_lookup)
    return vertices, faces


def _fill_cut_plane(bm, axis, value, below_floor=False):
    edges = [edge for edge in bm.edges if edge.is_boundary
             and all(abs(vertex.co[axis] - value) <= EPSILON for vertex in edge.verts)
             and (not below_floor or all(vertex.co.z <= EPSILON for vertex in edge.verts))]
    if below_floor:
        # The vertical box-cut boundary ends at Z=0. Close each open section
        # there before filling it, including separate reinforcement sections.
        degrees = {}
        for edge in edges:
            for vertex in edge.verts:
                degrees[vertex] = degrees.get(vertex, 0) + 1
        endpoints = sorted((vertex for vertex, degree in degrees.items() if degree == 1),
                           key=lambda vertex: vertex.co.x)
        for first, second in zip(endpoints[::2], endpoints[1::2]):
            edge = bm.edges.get((first, second))
            if edge is None:
                edges.append(bm.edges.new((first, second)))
            elif edge not in edges:
                edges.append(edge)
    if edges:
        bmesh.ops.holes_fill(bm, edges=edges, sides=0)


def _cut_start(bm, cut_type, cut_width, tread, edge_flow):
    if cut_type == 'NONE' or (cut_type == 'BOX' and cut_width <= EPSILON):
        return
    if cut_type == 'FLOOR':
        bmesh.ops.bisect_plane(
            bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), dist=EPSILON,
            plane_co=(0, 0, 0), plane_no=(0, 0, 1), clear_inner=True,
        )
        _fill_cut_plane(bm, 2, 0)
        return
    cut_y = -min(cut_width, tread)
    for position, normal in (((0, cut_y, 0), (0, 1, 0)), ((0, 0, 0), (0, 0, 1))):
        bmesh.ops.bisect_plane(
            bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), dist=EPSILON,
            plane_co=position, plane_no=normal,
        )
    removed = [face for face in bm.faces
               if face.calc_center_median().y >= cut_y - EPSILON
               and face.calc_center_median().z < -EPSILON]
    bmesh.ops.delete(bm, geom=removed, context='FACES')
    _fill_cut_plane(bm, 1, cut_y, below_floor=True)
    _fill_cut_plane(bm, 2, 0)
    if edge_flow == 'CORNER':
        bm.normal_update()
        top_cuts = [edge for edge in bm.edges if len(edge.link_faces) == 2
                    and all(abs(vertex.co.y - cut_y) <= EPSILON for vertex in edge.verts)
                    and all(abs(face.normal.z) > 1 - EPSILON for face in edge.link_faces)]
        if top_cuts:
            bmesh.ops.dissolve_edges(bm, edges=top_cuts, use_verts=False, use_face_split=False)


def _bevel_step_corners(bm, upper, width, segments, profile, flight_layer=None, flight_id=None):
    if width <= EPSILON:
        return
    bm.normal_update()
    edges = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2 or edge.is_convex != upper:
            continue
        if flight_layer is not None and not any(face[flight_layer] == flight_id for face in edge.link_faces):
            continue
        # Each flight is processed in its own local frame. Its first riser
        # meets the floor/landing at Y=0, Z=0 and must keep that original edge.
        if not upper and all(abs(vertex.co.y) <= EPSILON and abs(vertex.co.z) <= EPSILON
                             for vertex in edge.verts):
            continue
        direction = edge.verts[1].co - edge.verts[0].co
        normals = [face.normal for face in edge.link_faces]
        if (abs(direction.y) <= EPSILON and abs(direction.z) <= EPSILON
                and any(normal.z > 1 - EPSILON for normal in normals)
                and any(normal.y > EPSILON and abs(normal.x) < EPSILON for normal in normals)):
            edges.append(edge)
    if edges:
        result = bmesh.ops.bevel(bm, geom=edges, offset=width, segments=segments, profile=profile,
                                 affect='EDGES', clamp_overlap=True, loop_slide=True)
        if flight_layer is not None:
            for face in result['faces']:
                face[flight_layer] = flight_id
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=EPSILON)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=EPSILON)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def _shade_stairs(bm, width, riser, tread, step_count, cut_type, cut_width,
                  smooth, sharp_side, sharp_reinforcement, sharp_top_end, sharp_start,
                  sharp_unbeveled, top_rounded, bottom_rounded,
                  flight_layer=None, flight_id=None):
    bm.normal_update()
    half_width = width / 2
    front_planes = (0.0, -min(cut_width, tread)) if cut_type == 'BOX' else (0.0,)
    for face in bm.faces:
        if flight_layer is None:
            face.smooth = smooth
    for edge in bm.edges:
        if flight_layer is None:
            edge.smooth = True
        elif not any(face[flight_layer] == flight_id for face in edge.link_faces):
            continue
        if len(edge.link_faces) != 2 or edge.calc_face_angle(0.0) <= 0.0001:
            continue
        vertices = edge.verts
        direction = vertices[1].co - vertices[0].co
        side = any(all(abs(vertex.co.x - sign * half_width) <= EPSILON for vertex in vertices)
                   for sign in (-1, 1))
        longitudinal = (abs(direction.x) <= EPSILON
                        and abs(direction.z + direction.y * riser / tread) <= EPSILON
                        and abs(direction.y) > EPSILON)
        top_end = all(abs(vertex.co.y + step_count * tread) <= EPSILON for vertex in vertices)
        start = (all(vertex.co.z <= EPSILON for vertex in vertices)
                 and any(all(abs(vertex.co.y - plane) <= EPSILON for vertex in vertices)
                         for plane in front_planes))
        if cut_type != 'NONE':
            start = start or any(
                face.normal.z < -1 + EPSILON
                and all(abs(vertex.co.z) <= EPSILON for vertex in face.verts)
                for face in edge.link_faces)
        normals = [face.normal for face in edge.link_faces]
        step_corner = (abs(direction.y) <= EPSILON and abs(direction.z) <= EPSILON
                       and any(normal.z > 1 - EPSILON for normal in normals)
                       and any(normal.y > EPSILON and abs(normal.x) < EPSILON for normal in normals))
        first_step_base = all(abs(vertex.co.y) <= EPSILON and abs(vertex.co.z) <= EPSILON
                              for vertex in vertices)
        unrounded = step_corner and (first_step_base or not (top_rounded if edge.is_convex else bottom_rounded))
        if ((sharp_side and side) or (sharp_reinforcement and longitudinal)
                or (sharp_top_end and top_end) or (sharp_start and start)
                or (sharp_unbeveled and unrounded)):
            edge.smooth = False


def _flight_layout(flight_count, step_count, width, riser, tread, turn_angle,
                    turn_direction, landing_depth, flight_gap, side_overhang, end_overhang):
    """Exact orthogonal flight frames and landing bounds in the incoming frame."""
    frames, landings = [], []
    origin, x_axis, y_axis = (0.0, 0.0, 0.0), (1, 0), (0, 1)
    sign = 1 if turn_direction == 'RIGHT' else -1
    length, height = step_count * tread, step_count * riser
    for index in range(flight_count):
        frame = Matrix(((x_axis[0], y_axis[0], 0, origin[0]),
                        (x_axis[1], y_axis[1], 0, origin[1]),
                        (0, 0, 1, origin[2]), (0, 0, 0, 1)))
        frames.append(frame)
        if index == flight_count - 1:
            break
        if turn_angle == '180':
            next_x, next_y = sign * (width + flight_gap), -length
            x0 = min(-width / 2, next_x - width / 2) - side_overhang
            x1 = max(width / 2, next_x + width / 2) + side_overhang
            depth = landing_depth
            openings = [('NEAR', -width / 2, width / 2),
                        ('NEAR', next_x - width / 2, next_x + width / 2)]
            next_x_axis = tuple(-value for value in x_axis)
            next_y_axis = tuple(-value for value in y_axis)
        else:
            next_x = sign * (width / 2 + flight_gap)
            next_y = -length - width / 2 - flight_gap
            depth = max(landing_depth, width + flight_gap)
            x0 = -width / 2 - side_overhang if sign > 0 else next_x
            x1 = next_x if sign > 0 else width / 2 + side_overhang
            openings = [('NEAR', -width / 2, width / 2),
                        ('RIGHT' if sign > 0 else 'LEFT', next_y - width / 2, next_y + width / 2)]
            next_x_axis = tuple(sign * value for value in y_axis)
            next_y_axis = tuple(-sign * value for value in x_axis)
        landings.append(dict(frame=frame, bounds=(x0, x1, -length - depth - end_overhang, -length),
                             height=height, openings=openings))
        origin = (origin[0] + x_axis[0] * next_x + y_axis[0] * next_y,
                  origin[1] + x_axis[1] * next_x + y_axis[1] * next_y,
                  origin[2] + height)
        x_axis, y_axis = next_x_axis, next_y_axis
    return frames, landings


def _landing_shell(bounds, height, slab_height, openings, rib_width, plate_thickness=0.0):
    """Grid a flat slab with precisely matching flight apertures in its sides."""
    x0, x1, y0, y1 = bounds
    xs, ys = {x0, x1}, {y0, y1}
    for side, start, end in openings:
        cuts = (start, start + rib_width, end - rib_width, end) if rib_width > EPSILON else (start, end)
        (xs if side == 'NEAR' else ys).update(cuts)
    xs, ys = sorted(xs), sorted(ys)
    vertices, faces, lookup, face_lookup = [], [], {}, set()

    def vertex(x, y, z):
        return _add_vertex((x, y, z), vertices, lookup)

    def open_interval(side, start, end):
        return any(candidate == side and start >= low - EPSILON and end <= high + EPSILON
                   for candidate, low, high in openings)

    low = height - slab_height
    for left, right in zip(xs, xs[1:]):
        for near, far in zip(ys, ys[1:]):
            for z in (low, height - plate_thickness):
                _add_face([vertex(left, near, z), vertex(right, near, z),
                           vertex(right, far, z), vertex(left, far, z)], faces, face_lookup)
        for y, side in ((y0, 'FAR'), (y1, 'NEAR')):
            if not open_interval(side, left, right):
                _add_face([vertex(left, y, low), vertex(right, y, low),
                           vertex(right, y, height - plate_thickness), vertex(left, y, height - plate_thickness)], faces, face_lookup)
    for near, far in zip(ys, ys[1:]):
        for x, side in ((x0, 'LEFT'), (x1, 'RIGHT')):
            if not open_interval(side, near, far):
                _add_face([vertex(x, near, low), vertex(x, far, low),
                           vertex(x, far, height - plate_thickness), vertex(x, near, height - plate_thickness)], faces, face_lookup)
    return vertices, faces


def _multi_flight_shell(frames, landings, step_count, width, riser, tread, slab_height,
                        use_side_ribs, rib_width, rib_z_offset, cut_top, riser_offset, plate_thickness=0.0):
    vertices, faces, lookup, face_lookup, owners = [], [], {}, set(), []

    def append(part_vertices, part_faces, frame, owner):
        remap = []
        for x, y, z in part_vertices:
            world = (frame[0][0] * x + frame[0][1] * y + frame[0][3],
                     frame[1][0] * x + frame[1][1] * y + frame[1][3], z + frame[2][3])
            remap.append(_add_vertex(world, vertices, lookup))
        for face in part_faces:
            before = len(faces)
            _add_face([remap[index] for index in face], faces, face_lookup)
            if len(faces) != before:
                owners.append(owner)

    for index, frame in enumerate(frames):
        part = _stair_shell(step_count, width, riser, tread, slab_height, use_side_ribs,
                            rib_width, rib_z_offset, cut_top, riser_offset,
                            open_start=index > 0, open_end=index < len(frames) - 1,
                            plate_thickness=plate_thickness)
        append(*part, frame, index)
    connection_rib = rib_width if use_side_ribs and rib_z_offset > EPSILON else 0.0
    for landing in landings:
        part = _landing_shell(landing['bounds'], landing['height'], slab_height,
                               landing['openings'], connection_rib, plate_thickness)
        append(*part, landing['frame'], -1)
    return vertices, faces, owners


def build_stair_mesh(
    name, step_count, width, riser, tread, slab_height=0.2,
    use_side_ribs=False, rib_width=0.15, rib_z_offset=0.08, cut_top=False,
    start_cut_type='NONE', start_cut_width=0.1, start_cut_edge_flow='THROUGH',
    riser_offset=0.0, use_top_bevel=False, top_bevel_width=0.01,
    top_bevel_segments=3, top_bevel_profile=0.5, use_bottom_bevel=False,
    bottom_bevel_width=0.01, bottom_bevel_segments=3, bottom_bevel_profile=0.5,
    use_smooth_shading=True, sharp_side=True, sharp_reinforcement=True,
    sharp_top_end=True, sharp_start=True, sharp_unbeveled=True,
    flight_count=1, turn_angle='180', turn_direction='RIGHT', landing_depth=1.2,
    flight_gap=0.2, landing_side_overhang=0.0, landing_end_overhang=0.0,
    sharp_landings=True, tread_finish='ORIGINAL', plate_thickness=0.02,
):
    if tread + riser_offset <= EPSILON:
        raise ValueError('Riser Offset must be greater than -Tread')
    if slab_height <= EPSILON:
        raise ValueError('Slab Height must be positive; the slab is a required component')
    if flight_count < 1 or turn_angle not in ('90', '180') or turn_direction not in ('LEFT', 'RIGHT'):
        raise ValueError('Choose at least one flight, a 90/180 degree turn and Left or Right')
    if landing_depth <= EPSILON or landing_side_overhang < 0 or landing_end_overhang < 0:
        raise ValueError('Landing depth must be positive and overhangs cannot be negative')
    if flight_count > 1 and flight_gap < 0.001 - EPSILON:
        raise ValueError('Flight Gap must be at least 1 mm to keep adjacent flights separate')
    if tread_finish not in ('ORIGINAL', 'PLATES'):
        raise ValueError('Choose Original Bevel or Tread Plates')
    recess = plate_thickness if tread_finish == 'PLATES' else 0.0
    if tread_finish == 'PLATES':
        if recess <= EPSILON or recess >= min(riser, slab_height) - EPSILON:
            raise ValueError('Plate Thickness must be positive and smaller than Riser and Slab Height')
        # Tread junction bevels are replaced by the finish on the separate plates.
        use_top_bevel = use_bottom_bevel = False
    rib_width = min(max(rib_width, 0.0), max(0.0, width / 2 - EPSILON))
    frames, landings = _flight_layout(flight_count, step_count, width, riser, tread,
                                      turn_angle, turn_direction, landing_depth, flight_gap,
                                      landing_side_overhang, landing_end_overhang)
    if flight_count == 1:
        vertices, faces = _stair_shell(step_count, width, riser, tread, slab_height,
                                        use_side_ribs, rib_width, rib_z_offset, cut_top, riser_offset,
                                        plate_thickness=recess)
        owners = None
    else:
        vertices, faces, owners = _multi_flight_shell(
            frames, landings, step_count, width, riser, tread, slab_height,
            use_side_ribs, rib_width, rib_z_offset, cut_top, riser_offset, recess)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        mesh.from_pydata(vertices, [], faces)
        bm.from_mesh(mesh)
        flight_layer = None
        if owners is not None:
            flight_layer = bm.faces.layers.int.new('stair_flight')
            for face, owner in zip(bm.faces, owners):
                face[flight_layer] = owner
        _cut_start(bm, start_cut_type, start_cut_width, tread, start_cut_edge_flow)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        for index, frame in enumerate(frames):
            if flight_layer is not None:
                bmesh.ops.transform(bm, matrix=frame.inverted(), verts=list(bm.verts))
            if use_top_bevel:
                _bevel_step_corners(bm, True, top_bevel_width, top_bevel_segments, top_bevel_profile,
                                     flight_layer, index)
            if use_bottom_bevel:
                _bevel_step_corners(bm, False, bottom_bevel_width, bottom_bevel_segments, bottom_bevel_profile,
                                     flight_layer, index)
            if flight_layer is not None:
                bmesh.ops.transform(bm, matrix=frame, verts=list(bm.verts))
        if flight_layer is not None:
            for face in bm.faces:
                face.smooth = use_smooth_shading
            for edge in bm.edges:
                edge.smooth = not (sharp_landings and len(edge.link_faces) == 2
                                   and all(face[flight_layer] == -1 for face in edge.link_faces)
                                   and edge.calc_face_angle(0.0) > 0.0001)
        for index, frame in enumerate(frames):
            if flight_layer is not None:
                bmesh.ops.transform(bm, matrix=frame.inverted(), verts=list(bm.verts))
            _shade_stairs(bm, width, riser, tread, step_count,
                           start_cut_type if index == 0 else 'NONE', start_cut_width,
                           use_smooth_shading, sharp_side, sharp_reinforcement, sharp_top_end, sharp_start,
                           sharp_unbeveled, use_top_bevel and top_bevel_width > EPSILON,
                           use_bottom_bevel and bottom_bevel_width > EPSILON, flight_layer, index)
            if flight_layer is not None:
                bmesh.ops.transform(bm, matrix=frame, verts=list(bm.verts))
        bm.normal_update()
        bm.to_mesh(mesh)
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    finally:
        bm.free()
    mesh.update()
    return mesh


