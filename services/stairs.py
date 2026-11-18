"""Object-owned stair configuration with synchronous, transactional rebuilds."""
from inspect import signature

import bpy
from mathutils import Matrix

from ..geometry.railings import build_railing_meshes
from ..geometry.stairs import build_stair_mesh


STAIR_FIELDS = tuple(name for name in signature(build_stair_mesh).parameters if name != 'name')
RAIL_FIELDS = tuple(name for name in signature(build_railing_meshes).parameters if name != 'stairs')
INPUT_FIELDS = STAIR_FIELDS + RAIL_FIELDS + ('rail_enabled',)
_REBUILDING = set()
SCHEMA_VERSION = 2
PART_NAMES = {'handrail': 'Handrail', 'lower_rails': 'Infill Rails', 'posts': 'Posts',
              'connectors': 'Handrail Supports', 'couplings': 'Coupling Sleeves'}
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
            for name in INPUT_FIELDS:
                if not settings.is_property_set(name):
                    setattr(settings, name, getattr(settings, name))
            settings.schema_version = SCHEMA_VERSION
        parameters = {name: getattr(settings, name) for name in STAIR_FIELDS}
        prepared['stairs'] = build_stair_mesh(f'{root.name} Mesh', **parameters)
        if settings.rail_enabled:
            prepared.update(build_railing_meshes(parameters, **{name: getattr(settings, name) for name in RAIL_FIELDS}))
        children = {child.get('modular_stair_part'): child for child in root.children
                    if child.get('modular_stair_part') in PART_NAMES}
        concrete = bpy.data.materials.get('Stair Concrete')
        if concrete is None:
            concrete = bpy.data.materials.new('Stair Concrete')
            concrete.diffuse_color = (.55, .55, .52, 1)
        _copy_materials(prepared['stairs'], root.data, concrete)
        for name, mesh in prepared.items():
            if name != 'stairs':
                previous = children.get(name)
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


def create_stairs(context, source=None):
    placeholder = bpy.data.meshes.new('Modular Stairs')
    root = bpy.data.objects.new('Modular Stairs', placeholder)
    context.collection.objects.link(root)
    root.location = context.scene.cursor.location
    settings = root.modular_stairs
    settings.auto_update = False
    source_settings = source.modular_stairs if source is not None else settings
    values = {name: getattr(source_settings, name) for name in INPUT_FIELDS}
    # Write defaults as well: future addon defaults must not change a saved asset.
    for name, value in values.items():
        setattr(settings, name, value)
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
