import bpy
import bmesh

from ..BlenderUtils.keep_state import EditorState


EPSILON = 0.000001


def _snap_value(value, grid_size):
    return round(value / grid_size) * grid_size


def _values_different(first, second):
    return abs(first - second) > EPSILON


def _snap_coordinate(coordinate, grid_size, axes):
    snapped = coordinate.copy()
    for index, should_snap in enumerate(axes):
        if should_snap:
            snapped[index] = _snap_value(coordinate[index], grid_size)
    return snapped


def _vertex_axes(settings):
    return settings.snap_x, settings.snap_y, settings.snap_z


def _uv_axes(settings):
    return settings.snap_u, settings.snap_v


def _snap_vertex_coordinate(obj, local_coordinate, grid_size, axes, coordinate_space):
    if coordinate_space == "GLOBAL":
        world_coordinate = obj.matrix_world @ local_coordinate
        snapped_world_coordinate = _snap_coordinate(world_coordinate, grid_size, axes)
        return obj.matrix_world.inverted_safe() @ snapped_world_coordinate
    return _snap_coordinate(local_coordinate, grid_size, axes)


def _uv_loop_is_selected(loop, face, uv_data, use_uv_select_sync):
    """Read UV selection using Blender 5's API, then older Blender fallbacks."""
    if hasattr(loop, "uv_select_vert"):
        return (
            loop.uv_select_vert
            or getattr(loop, "uv_select_edge", False)
            or getattr(face, "uv_select", False)
        )
    return getattr(uv_data, "select", False) or (
        use_uv_select_sync and loop.vert.select
    )


def _snap_uv_loops(obj, grid_size, axes, selected_only, use_uv_select_sync):
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.verify()
    fixed_count = 0
    for face in bm.faces:
        for loop in face.loops:
            uv_data = loop[uv_layer]
            if selected_only and not _uv_loop_is_selected(
                loop, face, uv_data, use_uv_select_sync
            ):
                continue
            snapped = _snap_coordinate(uv_data.uv, grid_size, axes)
            if any(_values_different(current, new) for current, new in zip(uv_data.uv, snapped)):
                uv_data.uv = snapped
                fixed_count += 1
    bmesh.update_edit_mesh(obj.data)
    return fixed_count


class MODULAR_ASSETS_OT_snap_vertices(bpy.types.Operator):
    bl_idname = "modular_assets.snap_vertices"
    bl_label = "Snap All Vertices to Grid"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def execute(self, context):
        obj = context.object
        settings = context.scene.modular_assets_snap_settings
        axes = _vertex_axes(settings)
        if not any(axes):
            self.report({"WARNING"}, "Enable at least one vertex axis")
            return {"CANCELLED"}
        grid_size = settings.vertex_grid_size
        state = EditorState.capture_current_state(
            restore_visibility=False, restore_active_vertex_group=False
        )
        try:
            if obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            fixed_count = 0
            for vertex in obj.data.vertices:
                snapped = _snap_vertex_coordinate(
                    obj, vertex.co, grid_size, axes, settings.snap_coordinate_space
                )
                if any(_values_different(current, new) for current, new in zip(vertex.co, snapped)):
                    vertex.co = snapped
                    fixed_count += 1
            obj.data.update()
        finally:
            state.try_restore()
        self.report({"INFO"}, f"Vertices snapped: {fixed_count}")
        return {"FINISHED"}


class MODULAR_ASSETS_OT_snap_selected_vertices(bpy.types.Operator):
    bl_idname = "modular_assets.snap_selected_vertices"
    bl_label = "Snap Selected Vertices to Grid"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH" and context.object.mode == "EDIT"

    def execute(self, context):
        obj = context.object
        settings = context.scene.modular_assets_snap_settings
        axes = _vertex_axes(settings)
        if not any(axes):
            self.report({"WARNING"}, "Enable at least one vertex axis")
            return {"CANCELLED"}
        grid_size = settings.vertex_grid_size
        bm = bmesh.from_edit_mesh(obj.data)
        fixed_count = 0
        for vertex in bm.verts:
            if not vertex.select:
                continue
            snapped = _snap_vertex_coordinate(
                obj, vertex.co, grid_size, axes, settings.snap_coordinate_space
            )
            if any(_values_different(current, new) for current, new in zip(vertex.co, snapped)):
                vertex.co = snapped
                fixed_count += 1
        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, f"Selected vertices snapped: {fixed_count}")
        return {"FINISHED"}


class MODULAR_ASSETS_OT_snap_uvs(bpy.types.Operator):
    bl_idname = "modular_assets.snap_uvs"
    bl_label = "Snap UVs to Grid"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def execute(self, context):
        obj = context.object
        if not obj.data.uv_layers.active:
            self.report({"ERROR"}, "The mesh has no active UV map")
            return {"CANCELLED"}
        settings = context.scene.modular_assets_snap_settings
        axes = _uv_axes(settings)
        if not any(axes):
            self.report({"WARNING"}, "Enable U and/or V")
            return {"CANCELLED"}
        grid_size = settings.uv_grid_size
        state = EditorState.capture_current_state(
            restore_visibility=False, restore_active_vertex_group=False
        )
        try:
            if obj.mode != "EDIT":
                bpy.ops.object.mode_set(mode="EDIT")
            fixed_count = _snap_uv_loops(
                obj, grid_size, axes, selected_only=False, use_uv_select_sync=False
            )
        finally:
            state.try_restore()
        self.report({"INFO"}, f"UV loops snapped: {fixed_count}")
        return {"FINISHED"}


class MODULAR_ASSETS_OT_snap_selected_uvs(bpy.types.Operator):
    bl_idname = "modular_assets.snap_selected_uvs"
    bl_label = "Snap Selected UVs to Grid"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (
            context.object is not None
            and context.object.type == "MESH"
            and context.object.mode == "EDIT"
            and context.object.data.uv_layers.active is not None
        )

    def execute(self, context):
        settings = context.scene.modular_assets_snap_settings
        axes = _uv_axes(settings)
        if not any(axes):
            self.report({"WARNING"}, "Enable U and/or V")
            return {"CANCELLED"}
        fixed_count = _snap_uv_loops(
            context.object,
            settings.uv_grid_size,
            axes,
            selected_only=True,
            use_uv_select_sync=context.tool_settings.use_uv_select_sync,
        )
        self.report({"INFO"}, f"Selected UV loops snapped: {fixed_count}")
        return {"FINISHED"}


classes = (
    MODULAR_ASSETS_OT_snap_vertices,
    MODULAR_ASSETS_OT_snap_selected_vertices,
    MODULAR_ASSETS_OT_snap_uvs,
    MODULAR_ASSETS_OT_snap_selected_uvs,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
