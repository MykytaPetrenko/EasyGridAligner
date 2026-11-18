"""Replace the upper slice of each tread/landing with a separate finish mesh."""
import bmesh
import bpy

from .stairs import EPSILON, _flight_layout


def _append_plate(bm, frame, x0, x1, back, front, lower_front, height, thickness,
                  bevel_front, bevel_sides, bevel_width, bevel_segments, bevel_profile,
                  smooth, excluded_sides=()):
    low = height - thickness
    coords = ((x0, lower_front, low), (x1, lower_front, low),
              (x1, back, low), (x0, back, low),
              (x0, front, height), (x1, front, height),
              (x1, back, height), (x0, back, height))
    vertices = [bm.verts.new(point) for point in coords]
    faces = [bm.faces.new([vertices[index] for index in indices]) for indices in
             ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))]
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    bevel_edges = []
    if bevel_width > EPSILON:
        for first, second, side, enabled in (
            (4, 5, 'NEAR', bevel_front), (5, 6, 'RIGHT', bevel_sides),
            (7, 4, 'LEFT', bevel_sides), (6, 7, 'FAR', bevel_sides),
        ):
            if enabled and side not in excluded_sides:
                bevel_edges.append(bm.edges.get((vertices[first], vertices[second])))
        if bevel_edges:
            # Never round below the underside of the finish or change its level.
            result = bmesh.ops.bevel(
                bm, geom=bevel_edges, offset=min(bevel_width, thickness * .49),
                segments=bevel_segments, profile=bevel_profile,
                affect='EDGES', clamp_overlap=True, loop_slide=True)
            for face in result['faces']:
                face.smooth = smooth
    # This bmesh contains only this plate, so transformation includes bevel vertices.
    bmesh.ops.transform(bm, matrix=frame, verts=list(bm.verts))
    bm.normal_update()
    for edge in bm.edges:
        edge.smooth = all(face.smooth for face in edge.link_faces)


def build_tread_plate_mesh(name, stairs, plate_bevel_front=True, plate_bevel_sides=True,
                           plate_bevel_width=.003, plate_bevel_segments=3, plate_bevel_profile=.5):
    """All plates share one child object/material; each is a closed solid."""
    thickness = stairs['plate_thickness']
    frames, landings = _flight_layout(
        stairs['flight_count'], stairs['step_count'], stairs['width'], stairs['riser'], stairs['tread'],
        stairs['turn_angle'], stairs['turn_direction'], stairs['landing_depth'], stairs['flight_gap'],
        stairs['landing_side_overhang'], stairs['landing_end_overhang'])
    mesh = bpy.data.meshes.new(name)
    combined = bmesh.new()
    piece = bmesh.new()
    try:
        specs = []
        for frame in frames:
            for step in range(stairs['step_count']):
                front = -step * stairs['tread']
                specs.append((frame, -stairs['width'] / 2, stairs['width'] / 2,
                              -(step + 1) * stairs['tread'], front + stairs['riser_offset'],
                              front + stairs['riser_offset'] * (1 - thickness / stairs['riser']),
                              (step + 1) * stairs['riser'], ('FAR',)))
        for landing in landings:
            x0, x1, back, front = landing['bounds']
            # Keep flight interfaces square; bevel exposed landing edges only.
            excluded = tuple({opening[0] for opening in landing['openings']})
            specs.append((landing['frame'], x0, x1, back, front, front, landing['height'], excluded))
        for frame, x0, x1, back, front, lower_front, height, excluded in specs:
            piece.clear()
            _append_plate(piece, frame, x0, x1, back, front, lower_front, height, thickness,
                          plate_bevel_front, plate_bevel_sides, plate_bevel_width,
                          plate_bevel_segments, plate_bevel_profile, stairs['use_smooth_shading'], excluded)
            piece.to_mesh(mesh)
            combined.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(combined, faces=combined.faces)
        combined.to_mesh(mesh)
        mesh.update()
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    finally:
        piece.free()
        combined.free()
