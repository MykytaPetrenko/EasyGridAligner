import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup

from ..services.stairs import request_rebuild, request_railing_material_rebuild, sync_legacy_railing


def on_stairs_changed(self, context):
    request_rebuild(self, context)


def on_railing_material_changed(self, context):
    request_railing_material_rebuild(self, context)


def on_legacy_left_changed(self, context):
    sync_legacy_railing(self, 'LEFT', self.rail_left, context)


def on_legacy_right_changed(self, context):
    sync_legacy_railing(self, 'RIGHT', self.rail_right, context)


def on_legacy_outer_changed(self, context):
    sync_legacy_railing(self, 'OUTER', self.rail_outer_enabled, context)


MOUNT_ITEMS = (('NONE', 'None', 'No railing on this side'),
               ('FLIGHT', 'Flight Mounted', 'Posts mounted to the stair treads and landings'),
               ('WALL', 'Wall Mounted', 'Handrail fixed to a wall with brackets, without posts or infill rails'))


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
    show_wall_mounts: BoolProperty(default=True)
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
    tread_finish: EnumProperty(name='Tread Finish', items=(('ORIGINAL', 'Original Bevel', 'Apply the original upper/lower bevels to the structural stair mesh'), ('PLATES', 'Additional Tiles / Plates', 'Separate tread and landing finish plates recessed into the existing stair height')), default='ORIGINAL', update=on_stairs_changed)
    plate_thickness: FloatProperty(name='Plate Thickness', default=.02, min=.001, soft_max=.06, unit='LENGTH', description='Recess the structure by this thickness; finished tread levels and the underside stay unchanged', update=on_stairs_changed)
    plate_material: PointerProperty(name='Plate Material', type=bpy.types.Material, description='Material for all tread and landing plates', update=on_stairs_changed)
    plate_bevel_front: BoolProperty(name='Front Edge Bevel', default=True, update=on_stairs_changed)
    plate_bevel_sides: BoolProperty(name='Side Edge Bevels', default=True, update=on_stairs_changed)
    plate_bevel_width: FloatProperty(name='Plate Bevel Width', default=.003, min=0.0, soft_max=.02, unit='LENGTH', description='Clamped below half the plate thickness', update=on_stairs_changed)
    plate_bevel_segments: IntProperty(name='Plate Bevel Segments', default=3, min=1, soft_max=12, max=64, update=on_stairs_changed)
    plate_bevel_profile: FloatProperty(name='Plate Bevel Profile', default=.5, min=.01, max=.99, update=on_stairs_changed)
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
    rail_type: EnumProperty(name='Type', items=(('TYPE_1', 'Type 1 · Tubular', 'Tubular handrail with elbows and couplings'), ('TYPE_2', 'Type 2 · Rectangular', 'Square posts, rectangular handrail and straight infill rails with fixed corner connectors'), ('TYPE_3', 'Type 3 · Vertical Balusters', 'Vertical metal balusters and bottom rail with a contrasting continuous handrail; two material slots')), default='TYPE_1', update=on_stairs_changed)
    rail_materials_dirty: BoolProperty(default=False)
    rail_metal_material: PointerProperty(name='Metal Material', type=bpy.types.Material, description='Slot 1: posts, balusters, bottom rail and wall brackets for Type 3', update=on_railing_material_changed)
    rail_handrail_material: PointerProperty(name='Handrail Material', type=bpy.types.Material, description='Slot 2: the upper handrail for Type 3', update=on_railing_material_changed)
    rail_type3_handrail_width: FloatProperty(name='Handrail Width', default=.065, min=.01, soft_max=.15, unit='LENGTH', update=on_stairs_changed)
    rail_type3_handrail_thickness: FloatProperty(name='Handrail Thickness', default=.04, min=.005, soft_max=.08, unit='LENGTH', update=on_stairs_changed)
    rail_baluster_spacing: FloatProperty(name='Baluster Spacing', default=.12, min=.025, soft_max=.3, unit='LENGTH', description='Target center-to-center spacing of the vertical infill bars', update=on_stairs_changed)
    rail_baluster_width: FloatProperty(name='Baluster Width', default=.016, min=.004, soft_max=.04, unit='LENGTH', description='Cross-section dimension across the railing', update=on_stairs_changed)
    rail_baluster_depth: FloatProperty(name='Baluster Depth', default=.025, min=.004, soft_max=.06, unit='LENGTH', description='Cross-section dimension along the railing', update=on_stairs_changed)
    rail_base_rail_width: FloatProperty(name='Bottom Rail Width', default=.03, min=.01, soft_max=.08, unit='LENGTH', update=on_stairs_changed)
    rail_base_rail_height: FloatProperty(name='Bottom Rail Thickness', default=.035, min=.01, soft_max=.08, unit='LENGTH', update=on_stairs_changed)
    rail_top_rail_height: FloatProperty(name='Top Rail Thickness', default=.015, min=.001, soft_max=.03, unit='LENGTH', description='Continuous metal rail beneath the handrail; shares Bottom Rail Width and must be thinner than Bottom Rail Thickness', update=on_stairs_changed)
    rail_base_clearance: FloatProperty(name='Bottom Clearance', default=.05, min=0.0, soft_max=.2, unit='LENGTH', description='Minimum clearance above the step noses; the bottom rail follows the stair slope', update=on_stairs_changed)
    rail_left: BoolProperty(name='Left Side', default=True, update=on_legacy_left_changed)
    rail_right: BoolProperty(name='Right Side', default=True, update=on_legacy_right_changed)
    rail_outer_enabled: BoolProperty(name='Outer Railing', default=True, update=on_legacy_outer_changed)
    rail_inner_mount: EnumProperty(name='Inner Railing', items=MOUNT_ITEMS, default='FLIGHT', update=on_stairs_changed)
    rail_outer_mount: EnumProperty(name='Outer Railing', items=MOUNT_ITEMS, default='FLIGHT', update=on_stairs_changed)
    rail_inner_include_landings: BoolProperty(name='Include Landings', default=True, description='Continue the inner railing over landings; disable for separate flight-only sections', update=on_stairs_changed)
    rail_outer_include_landings: BoolProperty(name='Include Landings', default=True, description='Continue the outer railing over landings; disable for separate flight-only sections', update=on_stairs_changed)
    rail_wall_clearance: FloatProperty(name='Wall Clearance', default=.05, min=.02, soft_max=.15, unit='LENGTH', description='Clear distance from the handrail surface to the wall face', update=on_stairs_changed)
    rail_wall_bracket_spacing: FloatProperty(name='Wall Bracket Spacing', default=.9, min=.2, soft_max=2, unit='LENGTH', update=on_stairs_changed)
    rail_wall_plate_radius: FloatProperty(name='Mounting Plate Radius', default=.035, min=.015, soft_max=.06, unit='LENGTH', update=on_stairs_changed)
    rail_preview_walls: BoolProperty(name='Preview Wall', default=False, description='Show wireframe guide walls for wall-mounted sides, in the viewport only', update=on_stairs_changed)
    rail_preview_wall_thickness: FloatProperty(name='Preview Wall Thickness', default=.15, min=.02, soft_max=.5, unit='LENGTH', update=on_stairs_changed)
    rail_preview_wall_extra_height: FloatProperty(name='Height Above Handrail', default=.25, min=0, soft_max=1, unit='LENGTH', update=on_stairs_changed)
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
    rail_handrail_width: FloatProperty(name='Handrail Width', default=.05, min=.01, soft_max=.12, unit='LENGTH', update=on_stairs_changed)
    rail_handrail_thickness: FloatProperty(name='Handrail Thickness', default=.025, min=.005, soft_max=.06, unit='LENGTH', update=on_stairs_changed)
    rail_post_size: FloatProperty(name='Square Post Width', default=.04, min=.015, soft_max=.08, unit='LENGTH', update=on_stairs_changed)
    rail_corner_length: FloatProperty(name='Corner Connector Length', default=.06, min=.01, soft_max=.15, unit='LENGTH', description='Target leg length of each fixed corner fitting; constrained by section size and available straight lengths', update=on_stairs_changed)
    rail_corner_allowance: FloatProperty(name='Connector Allowance', default=.002, min=0.0, soft_max=.008, unit='LENGTH', description='Extra material outside the handrail or infill rail cross-section at each fixed corner', update=on_stairs_changed)


classes = (MODULAR_ASSETS_PG_stairs,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.modular_stairs = PointerProperty(type=MODULAR_ASSETS_PG_stairs)


def unregister():
    del bpy.types.Object.modular_stairs
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
