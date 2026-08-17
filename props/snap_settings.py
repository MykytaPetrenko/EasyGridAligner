import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import PropertyGroup


AXIS_ITEMS = (
    ("X", "X", "Use X coordinate"),
    ("Y", "Y", "Use Y coordinate"),
    ("Z", "Z", "Use Z coordinate"),
    ("-X", "-X", "Use negative X coordinate"),
    ("-Y", "-Y", "Use negative Y coordinate"),
    ("-Z", "-Z", "Use negative Z coordinate"),
)

UV_AXIS_MODE_ITEMS = (
    ("AUTO", "Auto (From View)", "Use the global axes closest to the current view's horizontal and vertical directions"),
    ("CUSTOM", "Custom", "Choose U and V axes manually"),
)

UV_OFFSET_MODE_ITEMS = (
    ("AUTO", "Auto", "Offset to the configured step grid"),
    ("CUSTOM", "Custom", "Set source-coordinate offsets manually"),
)

SNAP_COORDINATE_SPACE_ITEMS = (
    ("GLOBAL", "Global", "Snap to the global world grid"),
    ("LOCAL", "Local", "Snap to the object's local grid"),
)


class MODULAR_ASSETS_PG_snap_settings(PropertyGroup):
    show_uv_generator: BoolProperty(name="Show UV Generator", default=True)
    vertex_grid_size: FloatProperty(
        name="Vertex Grid Size", default=0.1, min=0.000001, precision=6,
    )
    uv_grid_size: FloatProperty(
        name="UV Grid Size", default=0.1, min=0.000001, precision=6,
    )
    snap_coordinate_space: EnumProperty(
        name="Coordinate Space", items=SNAP_COORDINATE_SPACE_ITEMS, default="LOCAL",
    )
    snap_x: BoolProperty(name="X", description="Snap the X coordinate", default=True)
    snap_y: BoolProperty(name="Y", description="Snap the Y coordinate", default=True)
    snap_z: BoolProperty(name="Z", description="Snap the Z coordinate", default=True)
    snap_u: BoolProperty(name="U", description="Snap the U coordinate", default=True)
    snap_v: BoolProperty(name="V", description="Snap the V coordinate", default=True)
    u_axis: EnumProperty(
        name="U Axis", items=AXIS_ITEMS, default="X",
        description="3D axis mapped onto the U coordinate",
    )
    v_axis: EnumProperty(
        name="V Axis", items=AXIS_ITEMS, default="Y",
        description="3D axis mapped onto the V coordinate",
    )
    uv_axis_mode: EnumProperty(name="Axis Mode", items=UV_AXIS_MODE_ITEMS, default="AUTO")
    uv_offset_mode: EnumProperty(name="Offset Mode", items=UV_OFFSET_MODE_ITEMS, default="AUTO")
    coordinate_scale: FloatProperty(
        name="Scale",
        description="Applied to both UV channels after their source-coordinate offsets",
        default=1.0,
        min=0.000001,
    )
    horizontal_offset: FloatProperty(
        name="Horizontal Axis Offset",
        description="Offset added in the mapped horizontal 3D-axis direction before scale",
        default=0.0,
        unit="LENGTH",
    )
    vertical_offset: FloatProperty(
        name="Vertical Axis Offset",
        description="Offset added in the mapped vertical 3D-axis direction before scale",
        default=0.0,
        unit="LENGTH",
    )
    projection_offset_step: FloatProperty(
        name="Offset Step",
        description="3D-coordinate interval used to automatically offset each mapped axis before scale",
        default=1.0,
        min=0.000001,
        unit="LENGTH",
    )
    use_world_coords: BoolProperty(
        name="Use World Coordinates",
        description="Use world-space coordinates instead of local object coordinates",
        default=False,
    )
    target_uv_name: StringProperty(
        name="UV Map", description="UV map to write to; created when missing", default="UVMap",
    )


classes = (MODULAR_ASSETS_PG_snap_settings,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.modular_assets_snap_settings = bpy.props.PointerProperty(
        type=MODULAR_ASSETS_PG_snap_settings
    )


def unregister():
    del bpy.types.Scene.modular_assets_snap_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
