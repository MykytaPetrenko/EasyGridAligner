import bpy
import bmesh
from math import floor
from mathutils import Vector


AXIS_MAP = {
    "X": (0, 1.0), "Y": (1, 1.0), "Z": (2, 1.0),
    "-X": (0, -1.0), "-Y": (1, -1.0), "-Z": (2, -1.0),
}


def _axis_value(coordinate, axis):
    index, sign = AXIS_MAP[axis]
    return coordinate[index] * sign


def _view_projection_axes(context):
    """Return the signed world axes most closely aligned to screen U and V."""
    view_rotation = context.region_data.view_matrix.to_3x3()
    projected_axes = [view_rotation @ Vector(axis) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    horizontal_index = max(range(3), key=lambda index: abs(projected_axes[index].x))
    vertical_index = max(
        (index for index in range(3) if index != horizontal_index),
        key=lambda index: abs(projected_axes[index].y),
    )
    horizontal_sign = 1.0 if projected_axes[horizontal_index].x >= 0.0 else -1.0
    vertical_sign = 1.0 if projected_axes[vertical_index].y >= 0.0 else -1.0
    return (horizontal_index, horizontal_sign), (vertical_index, vertical_sign)


def _step_offset(minimum, step):
    """Move the smallest value into the [0, step) band without changing scale."""
    return -floor(minimum / step) * step


def _axis_label(axis):
    names = ("X", "Y", "Z")
    index, sign = axis
    return names[index] if sign > 0 else f"-{names[index]}"


class MODULAR_ASSETS_OT_generate_uvs_from_coordinates(bpy.types.Operator):
    bl_idname = "modular_assets.generate_uvs_from_coordinates"
    bl_label = "Generate UVs from Coordinates"
    bl_description = "Generate UV coordinates for selected polygons from their 3D coordinates"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and bool(context.objects_in_mode)

    def execute(self, context):
        settings = context.scene.modular_assets_snap_settings
        uv_name = settings.target_uv_name.strip() or "UVMap"
        selected_faces = []
        u_minimum = float("inf")
        v_minimum = float("inf")
        for obj in context.objects_in_mode:
            if obj.type != "MESH":
                continue
            transform = obj.matrix_world if settings.use_world_coords else None
            bm = bmesh.from_edit_mesh(obj.data)
            for face in bm.faces:
                if not face.select:
                    continue
                selected_faces.append((obj, face))
                for loop in face.loops:
                    coordinate = transform @ loop.vert.co if transform else loop.vert.co
                    u_minimum = min(u_minimum, _axis_value(coordinate, settings.u_axis))
                    v_minimum = min(v_minimum, _axis_value(coordinate, settings.v_axis))

        if not selected_faces:
            self.report({"WARNING"}, "No polygons selected")
            return {"CANCELLED"}

        if settings.uv_offset_mode == "AUTO":
            u_offset = _step_offset(u_minimum, settings.projection_offset_step)
            v_offset = _step_offset(v_minimum, settings.projection_offset_step)
        else:
            u_offset = settings.horizontal_offset
            v_offset = settings.vertical_offset

        faces_by_object = {}
        for obj, face in selected_faces:
            faces_by_object.setdefault(obj, []).append(face)
        for obj, faces in faces_by_object.items():
            mesh = obj.data
            transform = obj.matrix_world if settings.use_world_coords else None
            bm = bmesh.from_edit_mesh(mesh)
            uv_layer = bm.loops.layers.uv.get(uv_name) or bm.loops.layers.uv.new(uv_name)
            for face in faces:
                for loop in face.loops:
                    coordinate = transform @ loop.vert.co if transform else loop.vert.co
                    loop[uv_layer].uv = (
                        (_axis_value(coordinate, settings.u_axis) + u_offset)
                        * settings.coordinate_scale,
                        (_axis_value(coordinate, settings.v_axis) + v_offset)
                        * settings.coordinate_scale,
                    )
            bmesh.update_edit_mesh(mesh)
            mesh.uv_layers.active = mesh.uv_layers[uv_name]

        self.report({"INFO"}, f"Generated UVs for {len(selected_faces)} polygon(s)")
        return {"FINISHED"}


class MODULAR_ASSETS_OT_generate_uvs_from_view(bpy.types.Operator):
    bl_idname = "modular_assets.generate_uvs_from_view"
    bl_label = "Generate UVs from View"
    bl_description = "Map selected polygons from the world axes closest to the current view's horizontal and vertical directions"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "EDIT_MESH"
            and bool(context.objects_in_mode)
            and context.region_data is not None
        )

    def execute(self, context):
        settings = context.scene.modular_assets_snap_settings
        u_axis, v_axis = _view_projection_axes(context)
        uv_name = settings.target_uv_name.strip() or "UVMap"
        selected_faces = []
        u_minimum = float("inf")
        v_minimum = float("inf")

        for obj in context.objects_in_mode:
            if obj.type != "MESH":
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            for face in bm.faces:
                if not face.select:
                    continue
                selected_faces.append((obj, face))
                for loop in face.loops:
                    world_coordinate = obj.matrix_world @ loop.vert.co
                    u_minimum = min(u_minimum, world_coordinate[u_axis[0]] * u_axis[1])
                    v_minimum = min(v_minimum, world_coordinate[v_axis[0]] * v_axis[1])

        if not selected_faces:
            self.report({"WARNING"}, "No polygons selected")
            return {"CANCELLED"}

        if settings.uv_offset_mode == "AUTO":
            u_offset = _step_offset(u_minimum, settings.projection_offset_step)
            v_offset = _step_offset(v_minimum, settings.projection_offset_step)
        else:
            u_offset = settings.horizontal_offset
            v_offset = settings.vertical_offset
        faces_by_object = {}
        for obj, face in selected_faces:
            faces_by_object.setdefault(obj, []).append(face)

        for obj, faces in faces_by_object.items():
            mesh = obj.data
            bm = bmesh.from_edit_mesh(mesh)
            uv_layer = bm.loops.layers.uv.get(uv_name) or bm.loops.layers.uv.new(uv_name)
            for face in faces:
                for loop in face.loops:
                    world_coordinate = obj.matrix_world @ loop.vert.co
                    loop[uv_layer].uv = (
                        (world_coordinate[u_axis[0]] * u_axis[1] + u_offset)
                        * settings.coordinate_scale,
                        (world_coordinate[v_axis[0]] * v_axis[1] + v_offset)
                        * settings.coordinate_scale,
                    )
            bmesh.update_edit_mesh(mesh)
            mesh.uv_layers.active = mesh.uv_layers[uv_name]

        self.report(
            {"INFO"},
            f"Generated view UVs ({_axis_label(u_axis)} → U, {_axis_label(v_axis)} → V)",
        )
        return {"FINISHED"}


classes = (
    MODULAR_ASSETS_OT_generate_uvs_from_coordinates,
    MODULAR_ASSETS_OT_generate_uvs_from_view,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
