import bpy

from ..BlenderUtils.dropdown import dropdown


class MODULAR_ASSETS_PT_tools(bpy.types.Panel):
    bl_label = "Modular Asset Tools"
    bl_idname = "MODULAR_ASSETS_PT_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Modular"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.modular_assets_snap_settings
        layout.label(text="Vertex Snapping")
        layout.prop(settings, "vertex_grid_size")
        row = layout.row(align=True)
        row.prop(settings, "snap_x", toggle=True)
        row.prop(settings, "snap_y", toggle=True)
        row.prop(settings, "snap_z", toggle=True)
        layout.prop(settings, "snap_coordinate_space", expand=True)
        layout.operator("modular_assets.snap_vertices", icon="SNAP_GRID")
        if context.object and context.object.type == "MESH" and context.object.mode == "EDIT":
            layout.operator("modular_assets.snap_selected_vertices", icon="VERTEXSEL")

        layout.separator()
        layout.label(text="UV Snapping")
        layout.prop(settings, "uv_grid_size")
        row = layout.row(align=True)
        row.prop(settings, "snap_u", toggle=True)
        row.prop(settings, "snap_v", toggle=True)
        layout.operator("modular_assets.snap_uvs", icon="UV")
        if context.object and context.object.type == "MESH" and context.object.mode == "EDIT":
            layout.operator("modular_assets.snap_selected_uvs", icon="UV_VERTEXSEL")

        if context.mode == "EDIT_MESH":
            layout.separator()
            if dropdown(layout, settings, "show_uv_generator", "UV from Coordinates", icon="UV"):
                layout.label(text="Axes")
                layout.prop(settings, "uv_axis_mode", expand=True)
                if settings.uv_axis_mode == "CUSTOM":
                    row = layout.row(align=True)
                    row.prop(settings, "u_axis", text="U")
                    row.prop(settings, "v_axis", text="V")
                    layout.prop(settings, "use_world_coords", text="Use Global Coordinates")
                else:
                    layout.label(text="Global axes are detected from the current view.", icon="VIEW_CAMERA")

                layout.separator()
                layout.label(text="Offset")
                layout.prop(settings, "uv_offset_mode", expand=True)
                if settings.uv_offset_mode == "AUTO":
                    layout.prop(settings, "projection_offset_step")
                else:
                    if settings.uv_axis_mode == "CUSTOM":
                        horizontal_label = f"{settings.u_axis} Axis Offset"
                        vertical_label = f"{settings.v_axis} Axis Offset"
                    else:
                        horizontal_label = "Horizontal Axis Offset"
                        vertical_label = "Vertical Axis Offset"
                    layout.prop(settings, "horizontal_offset", text=horizontal_label)
                    layout.prop(settings, "vertical_offset", text=vertical_label)

                layout.separator()
                layout.prop(settings, "coordinate_scale")
                layout.prop(settings, "target_uv_name")
                if settings.uv_axis_mode == "AUTO":
                    layout.operator("modular_assets.generate_uvs_from_view", icon="VIEW_CAMERA")
                else:
                    layout.operator("modular_assets.generate_uvs_from_coordinates", icon="UV")


classes = (MODULAR_ASSETS_PT_tools,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
