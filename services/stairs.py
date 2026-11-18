"""Object-owned stair configuration with synchronous, transactional rebuilds."""
from inspect import signature

import bpy
from mathutils import Matrix

from ..geometry.railings import build_railing_meshes
from ..geometry.railing_system import build_railing_system_meshes
from ..geometry.stairs import build_stair_mesh
from ..geometry.tread_plates import build_tread_plate_mesh


STAIR_FIELDS = tuple(name for name in signature(build_stair_mesh).parameters if name != 'name')
RAIL_FIELDS = tuple(name for name in signature(build_railing_meshes).parameters if name not in ('stairs', 'handrail_only'))
SYSTEM_FIELDS = tuple(name for name in signature(build_railing_system_meshes).parameters if name not in ('stairs', 'rail_parameters'))
PLATE_FIELDS = tuple(name for name in signature(build_tread_plate_mesh).parameters if name not in ('name', 'stairs'))
INPUT_FIELDS = STAIR_FIELDS + RAIL_FIELDS + SYSTEM_FIELDS + PLATE_FIELDS + ('rail_enabled',)
_REBUILDING = set()
SCHEMA_VERSION = 8
PART_NAMES = {'handrail': 'Handrail', 'lower_rails': 'Infill Rails', 'posts': 'Posts',
              'connectors': 'Handrail Supports', 'couplings': 'Coupling Sleeves',
              'handrail_corners': 'Handrail Corner Connectors', 'infill_corners': 'Infill Corner Connectors',
              'tread_plates': 'Tread Plates', 'wall_handrail': 'Wall Handrail',
              'wall_couplings': 'Wall Handrail Coupling Sleeves',
              'wall_handrail_corners': 'Wall Handrail Corner Connectors',
              'wall_brackets': 'Wall Brackets', 'wall_mount_plates': 'Wall Mounting Plates',
              'preview_walls': 'Preview Walls', 'balustrade': 'Vertical Baluster Railing',
              'wall_balustrade': 'Wall Handrail'}
LEGACY_PART_NAMES = {'lower_rails': 'Lower Rails', 'connectors': 'Connectors', 'couplings': 'Couplings'}


def find_stairs(obj):
    while obj is not None:
        if obj.type == 'MESH' and obj.modular_stairs.is_stairs:
            return obj
        obj = obj.parent
    return None


def _discard_mesh(mesh):
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _steel_material():
    material = bpy.data.materials.get('Stairs Stainless Steel')
    if material is None:
        material = bpy.data.materials.new('Stairs Stainless Steel')
        material.diffuse_color = (.48, .53, .58, 1)
        material.use_nodes = True
        shader = material.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = (.48, .53, .58, 1)
        shader.inputs['Metallic'].default_value = .95
        shader.inputs['Roughness'].default_value = .23
    return material


def _copy_materials(mesh, previous, fallback):
    materials = list(previous.materials) if previous is not None else []
    for material in materials or [fallback]:
        mesh.materials.append(material)


def _plate_material():
    material = bpy.data.materials.get('Stair Tread Finish')
    if material is None:
        material = bpy.data.materials.new('Stair Tread Finish')
        material.diffuse_color = (.22, .12, .055, 1)
        material.use_nodes = True
        shader = material.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = material.diffuse_color
        shader.inputs['Roughness'].default_value = .45
    return material


def sync_legacy_railing(settings, side, enabled, context):
    """Keep scripted legacy switches usable; new UI uses mounting enums."""
    root = settings.id_data
    key = root.as_pointer()
    if key in _REBUILDING:
        return
    if side == 'OUTER':
        field = 'rail_outer_mount'
    else:
        inner = 'RIGHT' if settings.turn_direction == 'RIGHT' else 'LEFT'
        field = 'rail_inner_mount' if side == inner else 'rail_outer_mount'
    _REBUILDING.add(key)
    try:
        setattr(settings, field, 'FLIGHT' if enabled else 'NONE')
    finally:
        _REBUILDING.discard(key)
    request_rebuild(settings, context)


def _preview_material():
    material = bpy.data.materials.get('Stairs Wall Preview')
    if material is None:
        material = bpy.data.materials.new('Stairs Wall Preview')
        material.diffuse_color = (.18, .45, .65, 1)
    return material


def _type3_materials(settings):
    for field, name, color, metallic, roughness in (
        ('rail_metal_material', 'Stairs Powder Coated Metal', (.025, .03, .035, 1), .65, .32),
        ('rail_handrail_material', 'Stairs Timber Handrail', (.4, .19, .055, 1), 0.0, .35),
    ):
        if getattr(settings, field) is None:
            material = bpy.data.materials.get(name)
            if material is None:
                material = bpy.data.materials.new(name)
                material.diffuse_color = color
                material.use_nodes = True
                shader = material.node_tree.nodes.get('Principled BSDF')
                shader.inputs['Base Color'].default_value = color
                shader.inputs['Metallic'].default_value = metallic
                shader.inputs['Roughness'].default_value = roughness
            setattr(settings, field, material)
    return settings.rail_metal_material, settings.rail_handrail_material


def _sync_type3_materials(settings, children):
    """Retain edits made in Blender's material slots as well as the configurator."""
    if settings.rail_materials_dirty:
        return
    previous = next((child for role, child in children.items()
                     if role in ('balustrade', 'wall_balustrade') and len(child.data.materials) == 2), None)
    if previous is None:
        return
    active = bpy.context.object
    if active in children.values() and len(active.data.materials) == 2:
        previous = active
    for field, material in zip(('rail_metal_material', 'rail_handrail_material'), previous.data.materials):
        if material is not None:
            setattr(settings, field, material)


def request_railing_material_rebuild(settings, context):
    if not settings.is_stairs or settings.id_data.as_pointer() in _REBUILDING:
        return
    settings.rail_materials_dirty = True
    request_rebuild(settings, context)


def rebuild_stairs(root):
    if root.type != 'MESH' or not root.modular_stairs.is_stairs:
        raise ValueError('Select a configured stairs object')
    if root.library is not None:
        raise ValueError('Linked stairs must be made local before editing')
    if root.mode != 'OBJECT' or any(child.mode != 'OBJECT' for child in root.children
                                  if child.get('modular_stair_part') in PART_NAMES):
        raise ValueError('Switch the stairs to Object Mode, then press Update')
    key = root.as_pointer()
    if key in _REBUILDING:
        return
    _REBUILDING.add(key)
    settings = root.modular_stairs
    prepared = {}
    try:
        if settings.schema_version < SCHEMA_VERSION:
            if not settings.is_property_set('rail_top_rail_height'):
                settings.rail_top_rail_height = min(.015, settings.rail_base_rail_height * .5)
            inner_enabled = settings.rail_right if settings.turn_direction == 'RIGHT' else settings.rail_left
            outer_enabled = settings.rail_left if settings.turn_direction == 'RIGHT' else settings.rail_right
            if not settings.is_property_set('rail_inner_mount'):
                settings.rail_inner_mount = 'FLIGHT' if inner_enabled else 'NONE'
            if not settings.is_property_set('rail_outer_mount'):
                enabled = outer_enabled and (settings.rail_outer_enabled or settings.flight_count == 1)
                settings.rail_outer_mount = 'FLIGHT' if enabled else 'NONE'
            for name in INPUT_FIELDS:
                if not settings.is_property_set(name):
                    setattr(settings, name, getattr(settings, name))
            settings.schema_version = SCHEMA_VERSION
        parameters = {name: getattr(settings, name) for name in STAIR_FIELDS}
        prepared['stairs'] = build_stair_mesh(f'{root.name} Mesh', **parameters)
        if settings.tread_finish == 'PLATES':
            prepared['tread_plates'] = build_tread_plate_mesh(
                f'{root.name} Tread Plates', parameters,
                **{name: getattr(settings, name) for name in PLATE_FIELDS})
        if settings.rail_enabled:
            prepared.update(build_railing_system_meshes(
                parameters, **{name: getattr(settings, name) for name in RAIL_FIELDS + SYSTEM_FIELDS}))
        children = {child.get('modular_stair_part'): child for child in root.children
                    if child.get('modular_stair_part') in PART_NAMES}
        _sync_type3_materials(settings, children)
        concrete = bpy.data.materials.get('Stair Concrete')
        if concrete is None:
            concrete = bpy.data.materials.new('Stair Concrete')
            concrete.diffuse_color = (.55, .55, .52, 1)
        _copy_materials(prepared['stairs'], root.data, concrete)
        for name, mesh in prepared.items():
            if name != 'stairs':
                previous = children.get(name)
                if name == 'tread_plates':
                    if settings.plate_material is None:
                        settings.plate_material = (previous.data.materials[0] if previous is not None
                                                   and previous.data.materials else _plate_material())
                    mesh.materials.append(settings.plate_material)
                elif name == 'preview_walls':
                    _copy_materials(mesh, previous.data if previous is not None else None, _preview_material())
                elif settings.rail_type == 'TYPE_3':
                    for material in _type3_materials(settings):
                        mesh.materials.append(material)
                else:
                    _copy_materials(mesh, previous.data if previous is not None else None, _steel_material())
        previous = root.data
        root.data = prepared.pop('stairs')
        _discard_mesh(previous)
        for name, mesh in list(prepared.items()):
            child = children.pop(name, None)
            if child is None:
                child = bpy.data.objects.new(f'{root.name} · {PART_NAMES[name]}', mesh)
                (root.users_collection[0] if root.users_collection else bpy.context.scene.collection).objects.link(child)
                child.parent = root
                child.matrix_parent_inverse = Matrix.Identity(4)
                child['modular_stair_part'] = name
            else:
                previous = child.data
                child.data = mesh
                _discard_mesh(previous)
                if name in LEGACY_PART_NAMES and child.name == f'{root.name} · {LEGACY_PART_NAMES[name]}':
                    child.name = f'{root.name} · {PART_NAMES[name]}'
            prepared.pop(name)
            if name == 'preview_walls':
                child.display_type = 'WIRE'
                child.hide_render = True
                child.color = (.18, .45, .65, 1)
        for child in children.values():
            previous = child.data
            if bpy.context.view_layer.objects.active == child and root.name in bpy.context.view_layer.objects:
                root.select_set(True)
                bpy.context.view_layer.objects.active = root
            # Preserve user additions parented to a generated part.
            for extra in list(child.children):
                world = extra.matrix_world.copy()
                extra.parent = root
                extra.matrix_world = world
            bpy.data.objects.remove(child, do_unlink=True)
            _discard_mesh(previous)
        settings.last_error = ''
        settings.rail_materials_dirty = False
    except Exception as error:
        settings.last_error = str(error)
        for mesh in prepared.values():
            _discard_mesh(mesh)
        raise
    finally:
        _REBUILDING.discard(key)


def request_rebuild(settings, context):
    root = settings.id_data
    if not settings.is_stairs or not settings.auto_update or root.as_pointer() in _REBUILDING:
        return
    try:
        rebuild_stairs(root)
    except Exception as error:
        settings.last_error = str(error)


def toggle_wall_preview(root):
    settings = root.modular_stairs
    previous = settings.rail_preview_walls
    key = root.as_pointer()
    _REBUILDING.add(key)
    try:
        settings.rail_preview_walls = not previous
    finally:
        _REBUILDING.discard(key)
    try:
        rebuild_stairs(root)
    except Exception:
        _REBUILDING.add(key)
        try:
            settings.rail_preview_walls = previous
        finally:
            _REBUILDING.discard(key)
        raise


def create_stairs(context, source=None):
    placeholder = bpy.data.meshes.new('Modular Stairs')
    root = bpy.data.objects.new('Modular Stairs', placeholder)
    context.collection.objects.link(root)
    root.location = context.scene.cursor.location
    settings = root.modular_stairs
    settings.auto_update = False
    source_settings = source.modular_stairs if source is not None else settings
    values = {name: getattr(source_settings, name) for name in INPUT_FIELDS}
    if not source_settings.is_property_set('rail_top_rail_height'):
        values['rail_top_rail_height'] = min(.015, source_settings.rail_base_rail_height * .5)
    # Write defaults as well: future addon defaults must not change a saved asset.
    for name, value in values.items():
        setattr(settings, name, value)
    settings.plate_material = source_settings.plate_material
    settings.rail_metal_material = source_settings.rail_metal_material
    settings.rail_handrail_material = source_settings.rail_handrail_material
    settings.schema_version = SCHEMA_VERSION
    settings.is_stairs = True
    try:
        rebuild_stairs(root)
    except Exception:
        previous = root.data
        for child in list(root.children):
            child_mesh = child.data
            bpy.data.objects.remove(child, do_unlink=True)
            _discard_mesh(child_mesh)
        bpy.data.objects.remove(root, do_unlink=True)
        _discard_mesh(previous)
        raise
    _REBUILDING.add(root.as_pointer())
    try:
        settings.auto_update = True
    finally:
        _REBUILDING.discard(root.as_pointer())
    for obj in context.selected_objects:
        obj.select_set(False)
    root.select_set(True)
    context.view_layer.objects.active = root
    return root
