import textwrap

import bpy

from ..BlenderUtils.dropdown import dropdown
from ..services.stairs import find_stairs


class MODULAR_ASSETS_PT_stairs(bpy.types.Panel):
    bl_label = 'Stairs Configurator'
    bl_idname = 'MODULAR_ASSETS_PT_stairs'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Modular'
    bl_order = -10

    def draw(self, context):
        layout = self.layout
        create = layout.row()
        create.enabled = context.mode == 'OBJECT'
        create.operator('mesh.modular_assets_add_stairs', text='New Stairs', icon='ADD')
        root = find_stairs(context.object)
        if root is None:
            layout.label(text='Create or select parametric stairs.', icon='INFO')
            return
        settings = root.modular_stairs
        layout.prop(root, 'name', text='Object')
        row = layout.row(align=True)
        row.prop(settings, 'auto_update', toggle=True)
        row.operator('modular_assets.update_stairs', text='Update', icon='FILE_REFRESH')
        if settings.last_error:
            box = layout.box()
            for line in textwrap.wrap(settings.last_error, width=42):
                box.label(text=line, icon='ERROR' if line == textwrap.wrap(settings.last_error, 42)[0] else 'NONE')
        body = layout.column()
        body.enabled = context.mode == 'OBJECT'
        box = body.box()
        if dropdown(box, settings, 'show_shape', text='Steps & Slab'):
            for name in ('step_count', 'width', 'riser', 'tread', 'riser_offset', 'slab_height'):
                box.prop(settings, name)
        box = body.box()
        if dropdown(box, settings, 'show_landings', text='Flights & Landings'):
            box.prop(settings, 'flight_count')
            controls = box.column()
            controls.enabled = settings.flight_count > 1
            for name in ('turn_angle', 'turn_direction', 'landing_depth', 'flight_gap',
                         'landing_side_overhang', 'landing_end_overhang'):
                controls.prop(settings, name)
            if settings.flight_count > 1 and settings.turn_angle == '90' and settings.landing_depth < settings.width + settings.flight_gap:
                controls.label(text='90° depth ≥ Width + Flight Gap')
        box = body.box()
        if dropdown(box, settings, 'show_reinforcement', text='Reinforcement'):
            box.prop(settings, 'use_side_ribs')
            controls = box.column()
            controls.enabled = settings.use_side_ribs
            for name in ('rib_width', 'rib_z_offset', 'cut_top'):
                controls.prop(settings, name)
        box = body.box()
        if dropdown(box, settings, 'show_bevels', text='Tread Finish & Bevels'):
            box.prop(settings, 'tread_finish')
            if settings.tread_finish == 'PLATES':
                box.prop(settings, 'plate_thickness')
                box.template_ID(settings, 'plate_material', new='material.new')
                box.label(text='Included in the existing stair height')
                for name in ('plate_bevel_front', 'plate_bevel_sides', 'plate_bevel_corners'):
                    box.prop(settings, name)
                controls = box.column()
                controls.enabled = settings.plate_bevel_front or settings.plate_bevel_sides or settings.plate_bevel_corners
                for name in ('plate_bevel_width', 'plate_bevel_segments', 'plate_bevel_profile'):
                    controls.prop(settings, name)
            else:
                for prefix in ('top', 'bottom'):
                    box.prop(settings, f'use_{prefix}_bevel')
                    controls = box.column()
                    controls.enabled = getattr(settings, f'use_{prefix}_bevel')
                    for suffix in ('width', 'segments', 'profile'):
                        controls.prop(settings, f'{prefix}_bevel_{suffix}')
        box = body.box()
        if dropdown(box, settings, 'show_shading', text='Shading'):
            box.prop(settings, 'use_smooth_shading')
            controls = box.column()
            controls.enabled = settings.use_smooth_shading
            controls.label(text='Mark Sharp:')
            for name in ('sharp_side', 'sharp_reinforcement', 'sharp_top_end', 'sharp_start',
                         'sharp_unbeveled', 'sharp_landings'):
                controls.prop(settings, name)
        box = body.box()
        if dropdown(box, settings, 'show_cut', text='Start Cut'):
            box.prop(settings, 'start_cut_type')
            controls = box.column()
            controls.enabled = settings.start_cut_type == 'BOX'
            for name in ('start_cut_width', 'start_cut_edge_flow'):
                controls.prop(settings, name)
        box = body.box()
        if dropdown(box, settings, 'show_railings', text='Railing System'):
            box.prop(settings, 'rail_enabled')
            controls = box.column()
            controls.enabled = settings.rail_enabled
            controls.prop(settings, 'rail_type')
            rectangular = settings.rail_type == 'TYPE_2'
            timber = settings.rail_type == 'TYPE_3'
            metal = settings.rail_type == 'TYPE_4'
            balusters = timber or metal
            if balusters:
                materials = controls.box()
                materials.label(text='Materials · 2 Slots' if timber else 'Metal Material')
                fields = (('rail_metal_material', 'Metal'), ('rail_handrail_material', 'Handrail')) if timber else (('rail_metal_material', 'Metal'),)
                for field, label in fields:
                    row = materials.row()
                    row.label(text=label)
                    row.template_ID(settings, field, new='material.new')
            has_flight = 'FLIGHT' in (settings.rail_inner_mount, settings.rail_outer_mount)
            has_wall = 'WALL' in (settings.rail_inner_mount, settings.rail_outer_mount)
            inner_side = 'Right' if settings.turn_direction == 'RIGHT' else 'Left'
            outer_side = 'Left' if inner_side == 'Right' else 'Right'
            for prefix, label, side in (('inner', 'Inner', inner_side), ('outer', 'Outer', outer_side)):
                section = controls.box()
                section.prop(settings, f'rail_{prefix}_mount', text=f'{label} ({side})')
                extent = section.row()
                extent.enabled = settings.flight_count > 1 and getattr(settings, f'rail_{prefix}_mount') != 'NONE'
                extent.prop(settings, f'rail_{prefix}_include_landings')
            common_names = ['rail_height']
            if has_flight:
                common_names.append('rail_inset')
                if not balusters:
                    common_names.append('rail_lower_count')
                common_names.append('rail_post_spacing')
            for name in common_names:
                controls.prop(settings, name)
            if has_wall:
                sub = controls.box()
                if dropdown(sub, settings, 'show_wall_mounts', text='Wall Mounts'):
                    for name in ('rail_wall_clearance', 'rail_wall_bracket_spacing', 'rail_wall_plate_radius'):
                        sub.prop(settings, name)
                    sub.prop(settings, 'rail_connector_radius', text='Bracket Stem Radius')
                    sub.prop(settings, 'rail_connector_segments', text='Bracket Stem Sides')
                    sub.operator('modular_assets.preview_walls',
                                 text='Hide Wall Preview' if settings.rail_preview_walls else 'Preview Wall',
                                 icon='MESH_CUBE', depress=settings.rail_preview_walls)
                    if settings.rail_preview_walls:
                        sub.prop(settings, 'rail_preview_wall_thickness')
                        sub.prop(settings, 'rail_preview_wall_extra_height')
                        sub.label(text='Wireframe preview · viewport only')
            sub = controls.box()
            title = 'Handrail & Vertical Balusters' if balusters else ('Handrail, Infill & Corner Fittings' if rectangular else 'Handrail, Infill & Sleeves')
            if dropdown(sub, settings, 'show_rail_tubes', text=title):
                if metal:
                    names = ('rail_type4_handrail_width', 'rail_type4_handrail_thickness')
                elif timber:
                    names = ('rail_type3_handrail_width', 'rail_type3_handrail_thickness', 'rail_top_rail_height')
                    if not has_flight:
                        names += ('rail_base_rail_width', 'rail_base_rail_height')
                elif rectangular:
                    names = ('rail_handrail_width', 'rail_handrail_thickness', 'rail_corner_length', 'rail_corner_allowance')
                else:
                    names = ('rail_radius', 'rail_bend_radius', 'rail_bend_segments', 'rail_segments',
                             'rail_coupling_length', 'rail_coupling_thickness')
                if has_flight:
                    names += (('rail_baluster_spacing', 'rail_baluster_width', 'rail_baluster_depth',
                               'rail_base_rail_width', 'rail_base_rail_height', 'rail_base_clearance') if balusters else
                              ('rail_lower_radius', 'rail_lower_segments', 'rail_lower_clearance'))
                for name in names:
                    sub.prop(settings, name)
            sub = controls.box()
            if dropdown(sub, settings, 'show_rail_ends', text='Ends & Extensions'):
                if not metal:
                    sub.prop(settings, 'rail_start_extension')
                    sub.prop(settings, 'rail_end_extension')
                if metal:
                    sub.prop(settings, 'rail_type4_return_radius')
                    sub.prop(settings, 'rail_type4_return_segments')
                if (has_flight and not metal) or timber:
                    sub.prop(settings, 'rail_infill_start_setback', text='Metal Start Setback' if balusters else 'Infill Start Setback')
                    sub.prop(settings, 'rail_infill_end_setback', text='Metal End Setback' if balusters else 'Infill End Setback')
            if timber:
                sub = controls.box()
                if dropdown(sub, settings, 'show_timber_details', text='Handrail Boards & Bevels'):
                    sub.prop(settings, 'rail_cap_split')
                    boards = sub.column()
                    boards.enabled = settings.rail_cap_split
                    boards.prop(settings, 'rail_cap_max_length')
                    boards.prop(settings, 'rail_cap_joint_gap')
                    sub.separator()
                    for group in ('top', 'bottom', 'ends'):
                        row = sub.row(align=True)
                        row.prop(settings, f'rail_cap_bevel_{group}')
                        amount = row.row()
                        amount.enabled = getattr(settings, f'rail_cap_bevel_{group}')
                        amount.prop(settings, f'rail_cap_{group}_bevel_width')
                    bevel = sub.column()
                    bevel.enabled = any(getattr(settings, f'rail_cap_bevel_{group}') for group in ('top', 'bottom', 'ends'))
                    bevel.prop(settings, 'rail_cap_bevel_segments')
                    bevel.prop(settings, 'rail_cap_bevel_profile')
            sub = controls.box() if has_flight else None
            if has_flight and dropdown(sub, settings, 'show_rail_posts', text='Posts' if balusters else 'Posts & Handrail Supports'):
                if balusters:
                    sub.prop(settings, 'rail_post_size')
                    sub.label(text='Square posts with integral base plates')
                    return
                if rectangular:
                    sub.prop(settings, 'rail_post_size')
                    sub.label(text='Square post section: 4 sides')
                else:
                    sub.prop(settings, 'rail_post_radius')
                    sub.prop(settings, 'rail_post_match_handrail')
                    post_sides = sub.row()
                    post_sides.enabled = not settings.rail_post_match_handrail
                    post_sides.prop(settings, 'rail_segments' if settings.rail_post_match_handrail else 'rail_post_segments', text='Post Sides')
                sub.separator()
                sub.prop(settings, 'rail_connector_mode')
                sub.prop(settings, 'rail_connector_radius', text='Stem Half-Width' if rectangular and settings.rail_connector_mode == 'INTEGRATED' else 'Support Stem Radius')
                sub.prop(settings, 'rail_connector_length')
                if settings.rail_connector_mode == 'INTEGRATED':
                    effective = 4 if rectangular else (settings.rail_segments if settings.rail_post_match_handrail else settings.rail_post_segments)
                    sub.label(text=f'Integral stem: {effective} sides (same as post)')
                else:
                    sub.prop(settings, 'rail_connector_match_post')
                    support_sides = sub.row()
                    support_sides.enabled = not settings.rail_connector_match_post
                    if rectangular and settings.rail_connector_match_post:
                        support_sides.label(text='Support Sides: 4 (same as post)')
                    else:
                        inherited = 'rail_segments' if settings.rail_post_match_handrail else 'rail_post_segments'
                        support_sides.prop(settings, inherited if settings.rail_connector_match_post else 'rail_connector_segments', text='Support Sides')


classes = (MODULAR_ASSETS_PT_stairs,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
