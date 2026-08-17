import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator
from bpy_extras.object_utils import AddObjectHelper, object_data_add


EPSILON = 0.000001


def _coord_key(coord):
    return tuple(round(value, 6) for value in coord)


def _add_vertex(coord, vertices, vertex_lookup):
    key = _coord_key(coord)
    index = vertex_lookup.get(key)
    if index is None:
        index = len(vertices)
        vertices.append(coord)
        vertex_lookup[key] = index
    return index


def _add_face(indices, faces, face_lookup):
    cleaned = []
    for index in indices:
        if not cleaned or cleaned[-1] != index:
            cleaned.append(index)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    if len(cleaned) < 3 or len(set(cleaned)) != len(cleaned):
        return
    key = tuple(sorted(cleaned))
    if key not in face_lookup:
        face_lookup.add(key)
        faces.append(cleaned)


def _regular_step_profile(step_index, tread, riser, use_lower_slab, lower_slab_z_offset):
    y_front = -step_index * tread
    y_back = -(step_index + 1) * tread
    z_base = step_index * riser
    z_top = (step_index + 1) * riser
    z_under_front = z_base - riser
    points = {
        "A": (y_front, z_under_front), "B": (y_front, z_base),
        "C": (y_front, z_top), "D": (y_back, z_top), "E": (y_back, z_base),
    }
    cap_faces = [("A", "B", "E"), ("B", "C", "D", "E")]
    outer_edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
    if use_lower_slab and lower_slab_z_offset > EPSILON:
        points["F"] = (y_front, z_under_front - lower_slab_z_offset)
        points["G"] = (y_back, z_base - lower_slab_z_offset)
        cap_faces.insert(0, ("F", "A", "E", "G"))
        outer_edges.extend((("E", "G"), ("G", "F"), ("F", "A")))
        bottom_edge = ("G", "F")
    else:
        outer_edges.append(("E", "A"))
        bottom_edge = ("E", "A")
    return {"points": points, "cap_faces": tuple(cap_faces), "outer_edges": tuple(outer_edges), "bottom_edge": bottom_edge}


def _start_cut_profile(tread, riser, use_lower_slab, lower_slab_z_offset, cut_width, cut_type):
    cut_width = min(max(cut_width, 0.0), tread)
    y_cut, y_back = -cut_width, -tread
    z_under = -riser
    z_under_cut = z_under + riser * (cut_width / tread)
    if cut_width >= tread - EPSILON:
        return {"points": {"B0": (0.0, 0.0), "C0": (0.0, riser), "D": (y_back, riser), "E": (y_back, 0.0)}, "cap_faces": (("B0", "C0", "D", "E"),), "outer_edges": (("B0", "C0"), ("C0", "D"), ("D", "E"), ("E", "B0")), "bottom_edge": None}
    points = {"B0": (0.0, 0.0), "C0": (0.0, riser), "B1": (y_cut, 0.0), "C1": (y_cut, riser), "A1": (y_cut, z_under_cut), "D": (y_back, riser), "E": (y_back, 0.0)}
    if cut_type == "CORNER":
        cap_faces = [("B0", "C0", "B1"), ("C0", "D", "E", "B1")]
        outer_edges = [("B0", "C0"), ("C0", "D"), ("D", "E")]
    else:
        cap_faces = [("B0", "C0", "C1", "B1"), ("B1", "C1", "D", "E")]
        outer_edges = [("B0", "C0"), ("C0", "C1"), ("C1", "D"), ("D", "E")]
    cap_faces.append(("A1", "B1", "E"))
    if use_lower_slab and lower_slab_z_offset > EPSILON:
        points["F1"] = (y_cut, z_under_cut - lower_slab_z_offset)
        points["G"] = (y_back, -lower_slab_z_offset)
        cap_faces.append(("F1", "A1", "E", "G"))
        outer_edges.extend((("E", "G"), ("G", "F1"), ("F1", "A1"), ("A1", "B1"), ("B1", "B0")))
        bottom_edge = ("G", "F1")
    else:
        outer_edges.extend((("E", "A1"), ("A1", "B1"), ("B1", "B0")))
        bottom_edge = ("E", "A1")
    return {"points": points, "cap_faces": tuple(cap_faces), "outer_edges": tuple(outer_edges), "bottom_edge": bottom_edge}


def _step_profile(step_index, tread, riser, use_lower_slab, lower_slab_z_offset, start_cut_type, start_cut_width, start_cut_edge_flow):
    if step_index == 0 and start_cut_type == "BOX" and start_cut_width > EPSILON:
        return _start_cut_profile(tread, riser, use_lower_slab, lower_slab_z_offset, start_cut_width, start_cut_edge_flow)
    return _regular_step_profile(step_index, tread, riser, use_lower_slab, lower_slab_z_offset)


def _clip_mesh_at_floor(vertices, faces, floor_z=0.0):
    output_vertices, output_faces, lookup, face_lookup = [], [], {}, set()
    floor_edges = {}
    def add(coord):
        x, y, z = coord
        return _add_vertex((x, y, floor_z if abs(z - floor_z) <= EPSILON else z), output_vertices, lookup)
    def intersect(start, end):
        factor = (floor_z - start[2]) / (end[2] - start[2])
        return tuple(start[index] + (end[index] - start[index]) * factor for index in range(2)) + (floor_z,)
    for face in faces:
        coordinates = []
        for position, end_index in enumerate(face):
            start = vertices[face[position - 1]]
            end = vertices[end_index]
            start_inside, end_inside = start[2] >= floor_z - EPSILON, end[2] >= floor_z - EPSILON
            if start_inside and not end_inside:
                coordinates.append(intersect(start, end))
            elif not start_inside and end_inside:
                coordinates.extend((intersect(start, end), end))
            elif end_inside:
                coordinates.append(end)
        indices = [add(coordinate) for coordinate in coordinates]
        _add_face(indices, output_faces, face_lookup)
        for first, second in zip(indices, indices[1:] + indices[:1]):
            if first != second and output_vertices[first][2] == floor_z and output_vertices[second][2] == floor_z:
                key = tuple(sorted((first, second)))
                floor_edges[key] = floor_edges.get(key, 0) + 1
    boundary = [edge for edge, count in floor_edges.items() if count == 1]
    adjacency = {}
    for first, second in boundary:
        adjacency.setdefault(first, []).append(second)
        adjacency.setdefault(second, []).append(first)
    unused = set(boundary)
    while unused:
        first, second = unused.pop()
        loop, previous, current = [first, second], first, second
        while current != first:
            next_vertex = next((candidate for candidate in adjacency[current] if candidate != previous and tuple(sorted((current, candidate))) in unused), None)
            if next_vertex is None:
                break
            unused.remove(tuple(sorted((current, next_vertex))))
            previous, current = current, next_vertex
            if current != first:
                loop.append(current)
        if current == first:
            _add_face(list(reversed(loop)), output_faces, face_lookup)
    return output_vertices, output_faces


def build_stair_mesh(name, step_count, width, riser, tread, use_lower_slab, lower_slab_z_offset, use_side_ribs, rib_width, rib_z_offset, cut_top, start_cut_type, start_cut_width, start_cut_edge_flow):
    half_width = width * 0.5
    rib_width = min(max(rib_width, 0.0), max(0.0, half_width - EPSILON))
    can_build_ribs = use_side_ribs and rib_width > EPSILON and rib_z_offset > EPSILON
    vertices, faces, lookup, face_lookup = [], [], {}, set()
    def vertex(point, x):
        return _add_vertex((x, point[0], point[1]), vertices, lookup)
    for step_index in range(step_count):
        profile = _step_profile(step_index, tread, riser, use_lower_slab, lower_slab_z_offset, start_cut_type, start_cut_width, start_cut_edge_flow)
        points = profile["points"]
        for cap in profile["cap_faces"]:
            _add_face([vertex(points[name], -half_width) for name in cap], faces, face_lookup)
            _add_face([vertex(points[name], half_width) for name in reversed(cap)], faces, face_lookup)
        step_has_ribs = can_build_ribs and profile["bottom_edge"] is not None
        rib_x_values = (-half_width, -half_width + rib_width, half_width - rib_width, half_width)

        def surface_vertex(point_name, x_value):
            bottom_edge = profile["bottom_edge"]
            if not step_has_ribs or cut_top or point_name in bottom_edge:
                return vertex(points[point_name], x_value)
            if abs(x_value - (-half_width + rib_width)) <= EPSILON:
                return vertex(points[point_name], -half_width)
            if abs(x_value - (half_width - rib_width)) <= EPSILON:
                return vertex(points[point_name], half_width)
            return vertex(points[point_name], x_value)

        for first, second in profile["outer_edges"]:
            x_values = (
                rib_x_values[1:3]
                if step_has_ribs and profile["bottom_edge"] == (first, second)
                else rib_x_values if step_has_ribs else (-half_width, half_width)
            )
            for x1, x2 in zip(x_values, x_values[1:]):
                _add_face([surface_vertex(first, x1), surface_vertex(second, x1), surface_vertex(second, x2), surface_vertex(first, x2)], faces, face_lookup)
        if step_has_ribs:
            start_name, end_name = profile["bottom_edge"]
            for outer, inner in ((-half_width, -half_width + rib_width), (half_width, half_width - rib_width)):
                start, end = points[start_name], points[end_name]
                top = [vertex(start, outer), vertex(start, inner), vertex(end, inner), vertex(end, outer)]
                bottom = [_add_vertex((outer, start[0], start[1] - rib_z_offset), vertices, lookup), _add_vertex((inner, start[0], start[1] - rib_z_offset), vertices, lookup), _add_vertex((inner, end[0], end[1] - rib_z_offset), vertices, lookup), _add_vertex((outer, end[0], end[1] - rib_z_offset), vertices, lookup)]
                _add_face(list(reversed(bottom)), faces, face_lookup)
                for index in range(4):
                    next_index = (index + 1) % 4
                    _add_face([top[index], top[next_index], bottom[next_index], bottom[index]], faces, face_lookup)
    if start_cut_type == "FLOOR":
        vertices, faces = _clip_mesh_at_floor(vertices, faces)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(verbose=False)
    mesh.update()
    return mesh


class MODULAR_ASSETS_OT_add_stairs(Operator, AddObjectHelper):
    bl_idname = "mesh.modular_assets_add_stairs"
    bl_label = "Modular Stairs"
    bl_options = {"REGISTER", "UNDO"}
    step_count: IntProperty(name="Steps", default=8, min=1, soft_max=64)
    width: FloatProperty(name="Width", default=2.0, min=0.001, unit="LENGTH")
    riser: FloatProperty(name="Riser", default=0.2, min=0.001, unit="LENGTH")
    tread: FloatProperty(name="Tread", default=0.3, min=0.001, unit="LENGTH")
    use_lower_slab: BoolProperty(name="Lower Slab", default=False)
    lower_slab_z_offset: FloatProperty(name="Slab Z Offset", default=0.08, min=0.0, unit="LENGTH")
    use_side_ribs: BoolProperty(name="Side Ribs", default=False)
    rib_width: FloatProperty(name="Rib Width", default=0.15, min=0.001, unit="LENGTH")
    rib_z_offset: FloatProperty(name="Rib Z Offset", default=0.08, min=0.0, unit="LENGTH")
    cut_top: BoolProperty(name="Cut Top", default=False)
    start_cut_type: EnumProperty(name="Cut Type", items=(("NONE", "None", "Do not cut"), ("FLOOR", "Floor Cut", "Clip at Z=0"), ("BOX", "Box Cut", "Cut into the first module")), default="NONE")
    start_cut_width: FloatProperty(name="Cut Width", default=0.1, min=0.0, unit="LENGTH")
    start_cut_edge_flow: EnumProperty(name="Cut Edge Flow", items=(("CORNER", "Corner", "Merge to corner"), ("THROUGH", "Through", "Continue through module")), default="THROUGH")

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def draw(self, context):
        layout = self.layout
        for attribute in ("step_count", "width", "riser", "tread", "use_lower_slab"):
            layout.prop(self, attribute)
        slab = layout.column(); slab.enabled = self.use_lower_slab; slab.prop(self, "lower_slab_z_offset")
        layout.prop(self, "use_side_ribs")
        ribs = layout.column(); ribs.enabled = self.use_side_ribs
        for attribute in ("rib_width", "rib_z_offset", "cut_top"): ribs.prop(self, attribute)
        layout.prop(self, "start_cut_type")
        cut = layout.column(); cut.enabled = self.start_cut_type == "BOX"
        cut.prop(self, "start_cut_width"); cut.prop(self, "start_cut_edge_flow")

    def execute(self, context):
        mesh = build_stair_mesh("Modular_Stairs_Mesh", self.step_count, self.width, self.riser, self.tread, self.use_lower_slab, self.lower_slab_z_offset, self.use_side_ribs, self.rib_width, self.rib_z_offset, self.cut_top, self.start_cut_type, self.start_cut_width, self.start_cut_edge_flow)
        obj = object_data_add(context, mesh, operator=self)
        obj.name = "Modular Stairs"
        material = bpy.data.materials.new("Stair Concrete")
        material.diffuse_color = (0.55, 0.55, 0.52, 1.0)
        obj.data.materials.append(material)
        return {"FINISHED"}


def add_stairs_menu(self, context):
    if context.mode == "OBJECT":
        self.layout.operator(MODULAR_ASSETS_OT_add_stairs.bl_idname, text="Modular Stairs", icon="MESH_CUBE")


def register():
    bpy.utils.register_class(MODULAR_ASSETS_OT_add_stairs)
    bpy.types.VIEW3D_MT_mesh_add.append(add_stairs_menu)


def unregister():
    bpy.types.VIEW3D_MT_mesh_add.remove(add_stairs_menu)
    bpy.utils.unregister_class(MODULAR_ASSETS_OT_add_stairs)
