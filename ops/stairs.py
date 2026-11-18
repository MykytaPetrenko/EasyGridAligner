import bpy
from bpy.types import Operator

from ..services.stairs import create_stairs, find_stairs, rebuild_stairs


class MODULAR_ASSETS_OT_add_stairs(Operator):
    bl_idname = 'mesh.modular_assets_add_stairs'
    bl_label = 'New Stairs'
    bl_description = 'Create stairs; edit their saved settings in Sidebar > Modular > Stairs'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        try:
            create_stairs(context, source=find_stairs(context.object))
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        if context.area is not None and context.area.type == 'VIEW_3D':
            context.space_data.show_region_ui = True
        return {'FINISHED'}


class MODULAR_ASSETS_OT_update_stairs(Operator):
    bl_idname = 'modular_assets.update_stairs'
    bl_label = 'Update Stairs'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and find_stairs(context.object) is not None

    def execute(self, context):
        try:
            rebuild_stairs(find_stairs(context.object))
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


def add_stairs_menu(self, context):
    if context.mode == 'OBJECT':
        self.layout.operator(MODULAR_ASSETS_OT_add_stairs.bl_idname, text='Modular Stairs', icon='MESH_CUBE')


classes = (MODULAR_ASSETS_OT_add_stairs, MODULAR_ASSETS_OT_update_stairs)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_mesh_add.append(add_stairs_menu)


def unregister():
    bpy.types.VIEW3D_MT_mesh_add.remove(add_stairs_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
