import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup

from ..services.stairs import request_rebuild


def on_stairs_changed(self, context):
    request_rebuild(self, context)


class MODULAR_ASSETS_PG_stairs(PropertyGroup):
    is_stairs: BoolProperty(default=False)
    schema_version: IntProperty(default=1)
    auto_update: BoolProperty(name='Auto Update', default=True, update=on_stairs_changed,
                              description='Rebuild when a parameter changes; disable while adjusting many settings')
    last_error: StringProperty(name='Last Error', options={'SKIP_SAVE'})
    show_shape: BoolProperty(default=True)
    show_landings: BoolProperty(default=False)
    show_reinforcement: BoolProperty(default=False)
    show_bevels: BoolProperty(default=False)
    show_shading: BoolProperty(default=False)
    show_cut: BoolProperty(default=False)
    show_railings: BoolProperty(default=True)
    show_rail_tubes: BoolProperty(default=False)
    show_rail_posts: BoolProperty(default=False)
    step_count: IntProperty(name='Steps per Flight', default=8, min=1, soft_max=64, update=on_stairs_changed)
    flight_count: IntProperty(name='Flights', default=1, min=1, soft_max=8, max=64, description='Number of stair flights; Steps applies to every flight', update=on_stairs_changed)
    turn_angle: EnumProperty(name='Turn Angle', items=(('180', '180°', 'Parallel return flights'), ('90', '90°', 'Quarter-turn flights')), default='180', update=on_stairs_changed)
    turn_direction: EnumProperty(name='Turn Direction', items=(('RIGHT', 'Right', 'Turn right while ascending'), ('LEFT', 'Left', 'Turn left while ascending')), default='RIGHT', update=on_stairs_changed)
    landing_depth: FloatProperty(name='Landing Depth', default=1.2, min=0.001, unit='LENGTH', description='Landing depth; 90° landings use at least Width + Flight Gap', update=on_stairs_changed)
    flight_gap: FloatProperty(name='Flight Gap', default=0.2, min=0.001, unit='LENGTH', description='Clear space between adjacent flights; 90° turns keep this gap in both directions', update=on_stairs_changed)
    landing_side_overhang: FloatProperty(name='Side Overhang', default=0.0, min=0.0, unit='LENGTH', description='Extend the exposed lateral edges of each landing', update=on_stairs_changed)
    landing_end_overhang: FloatProperty(name='End Overhang', default=0.0, min=0.0, unit='LENGTH', description='Extend the far edge of each landing beyond Landing Depth', update=on_stairs_changed)
    width: FloatProperty(name='Width', default=2.0, min=0.001, unit='LENGTH', update=on_stairs_changed)
    riser: FloatProperty(name='Riser', default=0.2, min=0.001, unit='LENGTH', update=on_stairs_changed)
    tread: FloatProperty(name='Tread', default=0.3, min=0.001, unit='LENGTH', update=on_stairs_changed)
    riser_offset: FloatProperty(name='Riser Offset', default=0.0, soft_min=-0.1, soft_max=0.1, unit='LENGTH', description='Positive projects the tread nose forward; negative recesses it', update=on_stairs_changed)
    slab_height: FloatProperty(name='Slab Height', default=0.2, min=0.001, unit='LENGTH', description='Vertical thickness of the required continuous slab beneath the triangular steps', update=on_stairs_changed)
    use_side_ribs: BoolProperty(name='Side Ribs', default=False, update=on_stairs_changed)
    rib_width: FloatProperty(name='Rib Width', default=0.15, min=0.001, unit='LENGTH', update=on_stairs_changed)
    rib_z_offset: FloatProperty(name='Rib Z Offset', default=0.08, min=0.0, unit='LENGTH', update=on_stairs_changed)
    cut_top: BoolProperty(name='Cut Top', default=False, update=on_stairs_changed)
    use_top_bevel: BoolProperty(name='Upper Bevel', default=False, description='Round the convex tread noses', update=on_stairs_changed)
    top_bevel_width: FloatProperty(name='Width', default=0.01, min=0.0, soft_max=0.1, unit='LENGTH', update=on_stairs_changed)
    top_bevel_segments: IntProperty(name='Segments', default=3, min=1, soft_max=12, max=64, update=on_stairs_changed)
    top_bevel_profile: FloatProperty(name='Profile', default=0.5, min=0.01, max=0.99, update=on_stairs_changed)
    use_bottom_bevel: BoolProperty(name='Lower Bevel', default=False, description='Round the concave tread/riser junctions, except the first step of each flight', update=on_stairs_changed)
    bottom_bevel_width: FloatProperty(name='Width', default=0.01, min=0.0, soft_max=0.1, unit='LENGTH', update=on_stairs_changed)
    bottom_bevel_segments: IntProperty(name='Segments', default=3, min=1, soft_max=12, max=64, update=on_stairs_changed)
    bottom_bevel_profile: FloatProperty(name='Profile', default=0.5, min=0.01, max=0.99, update=on_stairs_changed)
    use_smooth_shading: BoolProperty(name='Smooth Shading', default=True, update=on_stairs_changed)
    sharp_side: BoolProperty(name='Sides', default=True, description='Sharp outer side contours, including bevel ends', update=on_stairs_changed)
    sharp_reinforcement: BoolProperty(name='Underside / Reinforcement', default=True, description='Sharp longitudinal slab and reinforcement corners', update=on_stairs_changed)
    sharp_top_end: BoolProperty(name='Upper End', default=True, description='Sharp perimeter of the upper end face', update=on_stairs_changed)
    sharp_start: BoolProperty(name='Front / Cut Faces', default=True, description='Sharp exposed front and cut contours; includes the riser/slab join when the riser is offset', update=on_stairs_changed)
    sharp_unbeveled: BoolProperty(name='Unbeveled Corners', default=True, description='Keep tread/riser corners sharp when their bevel is disabled', update=on_stairs_changed)
    sharp_landings: BoolProperty(name='Landing Borders', default=True, description='Sharp outer borders of the landing slabs', update=on_stairs_changed)
    start_cut_type: EnumProperty(name='Cut Type', items=(('NONE', 'None', 'Do not cut'), ('FLOOR', 'Floor Cut', 'Clip at Z=0'), ('BOX', 'Box Cut', 'Cut the start below Z=0')), default='NONE', update=on_stairs_changed)
    start_cut_width: FloatProperty(name='Cut Width', default=0.1, min=0.0, unit='LENGTH', update=on_stairs_changed)
    start_cut_edge_flow: EnumProperty(name='Cut Edge Flow', items=(('CORNER', 'Corner', 'Keep the top surface continuous'), ('THROUGH', 'Through', 'Continue cut edges through the top')), default='THROUGH', update=on_stairs_changed)

    rail_enabled: BoolProperty(name='Enable Railing', default=False, update=on_stairs_changed)
    rail_type: EnumProperty(name='Type', items=(('TYPE_1', 'Type 1 · Tubular', 'Tubular handrail with elbows and couplings'),), default='TYPE_1', update=on_stairs_changed)
    rail_left: BoolProperty(name='Left Side', default=True, update=on_stairs_changed)
    rail_right: BoolProperty(name='Right Side', default=True, update=on_stairs_changed)
    rail_outer_enabled: BoolProperty(name='Outer Railing', default=True, description='Include the outer railing around turning flights and landings; the inner railing remains controlled by the side switches', update=on_stairs_changed)
    rail_height: FloatProperty(name='Railing Height', default=1.05, min=.25, soft_max=1.5, unit='LENGTH', description='Height above the landing and sloping stair reference line', update=on_stairs_changed)
    rail_inset: FloatProperty(name='Edge Inset', default=.08, min=.01, soft_max=.3, unit='LENGTH', update=on_stairs_changed)
    rail_radius: FloatProperty(name='Handrail Radius', default=.025, min=.005, soft_max=.06, unit='LENGTH', update=on_stairs_changed)
    rail_bend_radius: FloatProperty(name='Elbow Radius', default=.09, min=.01, soft_max=.3, unit='LENGTH', update=on_stairs_changed)
    rail_bend_segments: IntProperty(name='Elbow Segments', default=6, min=2, soft_max=12, max=32, update=on_stairs_changed)
    rail_segments: IntProperty(name='Handrail Sides', default=16, min=3, soft_max=32, max=64, update=on_stairs_changed)
    rail_lower_count: IntProperty(name='Infill Rail Count', default=4, min=0, soft_max=8, max=32, update=on_stairs_changed)
    rail_lower_radius: FloatProperty(name='Infill Rail Radius', default=.008, min=.002, soft_max=.02, unit='LENGTH', update=on_stairs_changed)
    rail_lower_clearance: FloatProperty(name='Infill Clearance', default=.12, min=.03, soft_max=.4, unit='LENGTH', update=on_stairs_changed)
    rail_lower_segments: IntProperty(name='Infill Rail Sides', default=8, min=3, soft_max=24, max=64, update=on_stairs_changed)
    rail_post_spacing: FloatProperty(name='Post Spacing', default=.9, min=.15, soft_max=2.0, unit='LENGTH', description='Target post spacing; flight posts snap to tread centers. Also controls landing posts', update=on_stairs_changed)
    rail_post_radius: FloatProperty(name='Post Radius', default=.018, min=.006, soft_max=.04, unit='LENGTH', update=on_stairs_changed)
    rail_post_segments: IntProperty(name='Post Sides', default=16, min=3, soft_max=32, max=64, update=on_stairs_changed)
    rail_post_match_handrail: BoolProperty(name='Same as Handrail', default=True, description='Use the handrail cross-section side count for posts and their integral stems', update=on_stairs_changed)
    rail_connector_mode: EnumProperty(name='Support Construction', items=(('SEPARATE', 'Separate Support', 'A separate handrail support stem above the post collar'), ('INTEGRATED', 'Integral Stem', 'The support stem shares the post mesh through a flat annular shoulder')), default='SEPARATE', update=on_stairs_changed)
    rail_connector_radius: FloatProperty(name='Support Stem Radius', default=.008, min=.002, soft_max=.02, unit='LENGTH', update=on_stairs_changed)
    rail_connector_length: FloatProperty(name='Support Stem Length', default=.07, min=.015, soft_max=.15, unit='LENGTH', update=on_stairs_changed)
    rail_connector_segments: IntProperty(name='Support Sides', default=8, min=3, soft_max=24, max=64, update=on_stairs_changed)
    rail_connector_match_post: BoolProperty(name='Same as Post', default=False, description='Use the effective post side count for separate handrail supports', update=on_stairs_changed)
    rail_coupling_length: FloatProperty(name='Coupling Length', default=.045, min=.01, soft_max=.1, unit='LENGTH', update=on_stairs_changed)
    rail_coupling_thickness: FloatProperty(name='Coupling Thickness', default=.006, min=.001, soft_max=.015, unit='LENGTH', update=on_stairs_changed)


classes = (MODULAR_ASSETS_PG_stairs,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.modular_stairs = PointerProperty(type=MODULAR_ASSETS_PG_stairs)


def unregister():
    del bpy.types.Object.modular_stairs
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
