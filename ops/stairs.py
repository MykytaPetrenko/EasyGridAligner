import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator
from bpy_extras.object_utils import AddObjectHelper, object_data_add


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
                 rib_width, rib_z_offset, cut_top, riser_offset):
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
            'A': (front, base - slab_height), 'B': (front, base),
            'C': (front + riser_offset, top), 'D': (back, top),
            'E': (back, top - slab_height),
        }
        for cap in (('B', 'C', 'D'), ('A', 'B', 'D', 'E')):
            _add_face([vertex(points[name], -half_width) for name in cap], faces, face_lookup)
            _add_face([vertex(points[name], half_width) for name in reversed(cap)], faces, face_lookup)

        def surface_vertex(name, x):
            if ribs and not cut_top and name not in ('A', 'E'):
                if abs(x - rib_x[1]) <= EPSILON:
                    x = -half_width
                elif abs(x - rib_x[2]) <= EPSILON:
                    x = half_width
            return vertex(points[name], x)

        edges = [('B', 'C'), ('C', 'D'), ('E', 'A')]
        if index == 0:
            edges.append(('A', 'B'))
        if index == step_count - 1:
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


def _bevel_step_corners(bm, upper, width, segments, profile):
    if width <= EPSILON:
        return
    bm.normal_update()
    edges = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2 or edge.is_convex != upper:
            continue
        direction = edge.verts[1].co - edge.verts[0].co
        normals = [face.normal for face in edge.link_faces]
        if (abs(direction.y) <= EPSILON and abs(direction.z) <= EPSILON
                and any(normal.z > 1 - EPSILON for normal in normals)
                and any(normal.y > EPSILON and abs(normal.x) < EPSILON for normal in normals)):
            edges.append(edge)
    if edges:
        bmesh.ops.bevel(bm, geom=edges, offset=width, segments=segments, profile=profile,
                        affect='EDGES', clamp_overlap=True, loop_slide=True)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=EPSILON)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=EPSILON)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def _shade_stairs(bm, width, riser, tread, step_count, cut_type, cut_width,
                  smooth, sharp_side, sharp_reinforcement, sharp_top_end, sharp_start,
                  sharp_unbeveled, top_rounded, bottom_rounded):
    bm.normal_update()
    half_width = width / 2
    front_planes = (0.0, -min(cut_width, tread)) if cut_type == 'BOX' else (0.0,)
    for face in bm.faces:
        face.smooth = smooth
    for edge in bm.edges:
        edge.smooth = True
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
        unrounded = step_corner and not (top_rounded if edge.is_convex else bottom_rounded)
        if ((sharp_side and side) or (sharp_reinforcement and longitudinal)
                or (sharp_top_end and top_end) or (sharp_start and start)
                or (sharp_unbeveled and unrounded)):
            edge.smooth = False


def build_stair_mesh(
    name, step_count, width, riser, tread, slab_height=0.2,
    use_side_ribs=False, rib_width=0.15, rib_z_offset=0.08, cut_top=False,
    start_cut_type='NONE', start_cut_width=0.1, start_cut_edge_flow='THROUGH',
    riser_offset=0.0, use_top_bevel=False, top_bevel_width=0.01,
    top_bevel_segments=3, top_bevel_profile=0.5, use_bottom_bevel=False,
    bottom_bevel_width=0.01, bottom_bevel_segments=3, bottom_bevel_profile=0.5,
    use_smooth_shading=True, sharp_side=True, sharp_reinforcement=True,
    sharp_top_end=True, sharp_start=True, sharp_unbeveled=True,
):
    if tread + riser_offset <= EPSILON:
        raise ValueError('Riser Offset must be greater than -Tread')
    if slab_height <= EPSILON:
        raise ValueError('Slab Height must be positive; the slab is a required component')
    rib_width = min(max(rib_width, 0.0), max(0.0, width / 2 - EPSILON))
    vertices, faces = _stair_shell(step_count, width, riser, tread, slab_height,
                                    use_side_ribs, rib_width, rib_z_offset, cut_top, riser_offset)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        mesh.from_pydata(vertices, [], faces)
        bm.from_mesh(mesh)
        _cut_start(bm, start_cut_type, start_cut_width, tread, start_cut_edge_flow)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if use_top_bevel:
            _bevel_step_corners(bm, True, top_bevel_width, top_bevel_segments, top_bevel_profile)
        if use_bottom_bevel:
            _bevel_step_corners(bm, False, bottom_bevel_width, bottom_bevel_segments, bottom_bevel_profile)
        _shade_stairs(bm, width, riser, tread, step_count, start_cut_type, start_cut_width,
                       use_smooth_shading, sharp_side, sharp_reinforcement, sharp_top_end, sharp_start,
                       sharp_unbeveled, use_top_bevel and top_bevel_width > EPSILON,
                       use_bottom_bevel and bottom_bevel_width > EPSILON)
        bm.to_mesh(mesh)
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    finally:
        bm.free()
    mesh.update()
    return mesh


class MODULAR_ASSETS_OT_add_stairs(Operator, AddObjectHelper):
    bl_idname = 'mesh.modular_assets_add_stairs'
    bl_label = 'Modular Stairs'
    bl_options = {'REGISTER', 'UNDO'}

    step_count: IntProperty(name='Steps', default=8, min=1, soft_max=64)
    width: FloatProperty(name='Width', default=2.0, min=0.001, unit='LENGTH')
    riser: FloatProperty(name='Riser', default=0.2, min=0.001, unit='LENGTH')
    tread: FloatProperty(name='Tread', default=0.3, min=0.001, unit='LENGTH')
    riser_offset: FloatProperty(name='Riser Offset', default=0.0, soft_min=-0.1, soft_max=0.1,
                                unit='LENGTH', description='Positive projects the tread nose forward; negative recesses it')
    slab_height: FloatProperty(name='Slab Height', default=0.2, min=0.001, unit='LENGTH',
                               description='Vertical thickness of the required continuous slab beneath the triangular steps')
    use_side_ribs: BoolProperty(name='Side Ribs', default=False)
    rib_width: FloatProperty(name='Rib Width', default=0.15, min=0.001, unit='LENGTH')
    rib_z_offset: FloatProperty(name='Rib Z Offset', default=0.08, min=0.0, unit='LENGTH')
    cut_top: BoolProperty(name='Cut Top', default=False)
    use_top_bevel: BoolProperty(name='Upper Bevel', default=False, description='Round the convex tread noses')
    top_bevel_width: FloatProperty(name='Width', default=0.01, min=0.0, soft_max=0.1, unit='LENGTH')
    top_bevel_segments: IntProperty(name='Segments', default=3, min=1, soft_max=12, max=64)
    top_bevel_profile: FloatProperty(name='Profile', default=0.5, min=0.01, max=0.99)
    use_bottom_bevel: BoolProperty(name='Lower Bevel', default=False, description='Round the concave tread/riser junctions')
    bottom_bevel_width: FloatProperty(name='Width', default=0.01, min=0.0, soft_max=0.1, unit='LENGTH')
    bottom_bevel_segments: IntProperty(name='Segments', default=3, min=1, soft_max=12, max=64)
    bottom_bevel_profile: FloatProperty(name='Profile', default=0.5, min=0.01, max=0.99)
    use_smooth_shading: BoolProperty(name='Smooth Shading', default=True)
    sharp_side: BoolProperty(name='Sides', default=True, description='Sharp outer side contours, including bevel ends')
    sharp_reinforcement: BoolProperty(name='Underside / Reinforcement', default=True, description='Sharp longitudinal slab and reinforcement corners')
    sharp_top_end: BoolProperty(name='Upper End', default=True, description='Sharp perimeter of the upper end face')
    sharp_start: BoolProperty(name='Front / Cut Faces', default=True, description='Sharp exposed front and cut contours; includes the riser/slab join when the riser is offset')
    sharp_unbeveled: BoolProperty(name='Unbeveled Corners', default=True, description='Keep tread/riser corners sharp when their bevel is disabled')
    start_cut_type: EnumProperty(name='Cut Type', items=(('NONE', 'None', 'Do not cut'), ('FLOOR', 'Floor Cut', 'Clip at Z=0'), ('BOX', 'Box Cut', 'Cut the start below Z=0')), default='NONE')
    start_cut_width: FloatProperty(name='Cut Width', default=0.1, min=0.0, unit='LENGTH')
    start_cut_edge_flow: EnumProperty(name='Cut Edge Flow', items=(('CORNER', 'Corner', 'Keep the top surface continuous'), ('THROUGH', 'Through', 'Continue cut edges through the top')), default='THROUGH')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def draw(self, context):
        layout = self.layout
        for name in ('step_count', 'width', 'riser', 'tread', 'riser_offset', 'slab_height'):
            layout.prop(self, name)
        layout.prop(self, 'use_side_ribs')
        ribs = layout.column()
        ribs.enabled = self.use_side_ribs
        for name in ('rib_width', 'rib_z_offset', 'cut_top'):
            ribs.prop(self, name)
        layout.separator()
        for prefix in ('top', 'bottom'):
            layout.prop(self, f'use_{prefix}_bevel')
            bevel = layout.column()
            bevel.enabled = getattr(self, f'use_{prefix}_bevel')
            for suffix in ('width', 'segments', 'profile'):
                bevel.prop(self, f'{prefix}_bevel_{suffix}')
        layout.separator()
        layout.prop(self, 'use_smooth_shading')
        shading = layout.column()
        shading.enabled = self.use_smooth_shading
        shading.label(text='Mark Sharp:')
        for name in ('sharp_side', 'sharp_reinforcement', 'sharp_top_end', 'sharp_start', 'sharp_unbeveled'):
            shading.prop(self, name)
        layout.separator()
        layout.prop(self, 'start_cut_type')
        cut = layout.column()
        cut.enabled = self.start_cut_type == 'BOX'
        cut.prop(self, 'start_cut_width')
        cut.prop(self, 'start_cut_edge_flow')

    def execute(self, context):
        parameters = (
            'step_count', 'width', 'riser', 'tread', 'slab_height', 'use_side_ribs',
            'rib_width', 'rib_z_offset', 'cut_top', 'start_cut_type', 'start_cut_width',
            'start_cut_edge_flow', 'riser_offset', 'use_top_bevel', 'top_bevel_width',
            'top_bevel_segments', 'top_bevel_profile', 'use_bottom_bevel',
            'bottom_bevel_width', 'bottom_bevel_segments', 'bottom_bevel_profile',
            'use_smooth_shading', 'sharp_side', 'sharp_reinforcement', 'sharp_top_end', 'sharp_start', 'sharp_unbeveled',
        )
        try:
            mesh = build_stair_mesh('Modular_Stairs_Mesh', **{name: getattr(self, name) for name in parameters})
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        obj = object_data_add(context, mesh, operator=self)
        obj.name = 'Modular Stairs'
        material = bpy.data.materials.new('Stair Concrete')
        material.diffuse_color = (0.55, 0.55, 0.52, 1.0)
        obj.data.materials.append(material)
        return {'FINISHED'}


def add_stairs_menu(self, context):
    if context.mode == 'OBJECT':
        self.layout.operator(MODULAR_ASSETS_OT_add_stairs.bl_idname, text='Modular Stairs', icon='MESH_CUBE')


def register():
    bpy.utils.register_class(MODULAR_ASSETS_OT_add_stairs)
    bpy.types.VIEW3D_MT_mesh_add.append(add_stairs_menu)


def unregister():
    bpy.types.VIEW3D_MT_mesh_add.remove(add_stairs_menu)
    bpy.utils.unregister_class(MODULAR_ASSETS_OT_add_stairs)
