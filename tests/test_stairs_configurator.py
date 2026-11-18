"""Blender integration tests for object settings, live updates and Type 1 rails."""
import itertools
import os
from pathlib import Path
import sys
import tempfile
import unittest

import bmesh
import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import EasyGridAligner
from EasyGridAligner.services.stairs import INPUT_FIELDS, find_stairs, rebuild_stairs


class ConfiguratorTest(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.scene.cursor.location = (0, 0, 0)

    def create(self):
        self.assertEqual(bpy.ops.mesh.modular_assets_add_stairs(), {'FINISHED'})
        return bpy.context.object

    def configure(self, root, **parameters):
        settings = root.modular_stairs
        settings.auto_update = False
        for name, value in parameters.items():
            setattr(settings, name, value)
        settings.auto_update = True
        self.assertFalse(settings.last_error, settings.last_error)

    def assert_closed(self, obj):
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            self.assertTrue(all(len(edge.link_faces) == 2 for edge in bm.edges), obj.name)
            self.assertTrue(all(edge.is_contiguous for edge in bm.edges), obj.name)
            self.assertTrue(all(face.calc_area() > 0 for face in bm.faces), obj.name)
            self.assertGreater(bm.calc_volume(signed=True), 0)
        finally:
            bm.free()

    def test_live_update_instances_and_materials(self):
        first = self.create()
        first.location = (3, 4, 5)
        first.rotation_euler = (.1, .2, .3)
        first.scale = (1.2, .9, 1.1)
        matrix = first.matrix_basis.copy()
        material = bpy.data.materials.new('Custom Concrete')
        first.data.materials.clear()
        first.data.materials.append(material)
        previous = first.data.as_pointer()
        first.modular_stairs.step_count = 5
        self.assertNotEqual(first.data.as_pointer(), previous)
        self.assertEqual(first.matrix_basis, matrix)
        self.assertEqual(first.data.materials[0], material)
        second = self.create()
        self.assertEqual(second.modular_stairs.step_count, 5)
        first_data = first.data
        second.modular_stairs.width = 1.5
        self.assertEqual(first.data, first_data)
        self.assertEqual(first.modular_stairs.width, 2.0)
        self.assertEqual(second.modular_stairs.width, 1.5)
        self.assertIsNot(first.data, second.data)

    def test_rails_turns_sides_and_topology(self):
        root = self.create()
        for angle, direction, ribs in itertools.product(('90', '180'), ('LEFT', 'RIGHT'), (False, True)):
            with self.subTest(angle=angle, direction=direction, ribs=ribs):
                self.configure(root, flight_count=3, step_count=5, width=1.5,
                               turn_angle=angle, turn_direction=direction, use_side_ribs=ribs,
                               landing_side_overhang=.1, landing_end_overhang=.2,
                               rail_enabled=True, use_top_bevel=True, use_bottom_bevel=True)
                self.assertEqual({child['modular_stair_part'] for child in root.children},
                                 {'handrail', 'lower_rails', 'posts', 'connectors', 'couplings'})
                for obj in [root, *root.children]:
                    self.assert_closed(obj)
                    if obj != root:
                        self.assertEqual(find_stairs(obj), root)
                        self.assertEqual(obj.matrix_basis, Matrix.Identity(4))

    def test_tube_count_and_post_frequency(self):
        root = self.create()
        self.configure(root, rail_enabled=True, rail_lower_count=4)
        parts = {child['modular_stair_part']: child for child in root.children}
        lower_faces = len(parts['lower_rails'].data.polygons)
        post_faces = len(parts['posts'].data.polygons)
        root.modular_stairs.rail_lower_count = 2
        self.assertEqual(len(parts['lower_rails'].data.polygons) * 2, lower_faces)
        root.modular_stairs.rail_post_spacing = .4
        self.assertGreater(len(parts['posts'].data.polygons), post_faces)
        root.modular_stairs.rail_lower_count = 0
        self.assertNotIn('lower_rails', {child['modular_stair_part'] for child in root.children})
        root.modular_stairs.rail_right = False
        self.assertFalse(root.modular_stairs.last_error)
        self.assertEqual(len(parts['handrail'].data.polygons), 18)

    def test_invalid_settings_keep_previous_geometry(self):
        root = self.create()
        self.configure(root, flight_count=2, rail_enabled=True)
        data = root.data
        children = {child: child.data for child in root.children}
        mesh_count = len(bpy.data.meshes)
        root.modular_stairs.rail_bend_radius = .01
        self.assertTrue(root.modular_stairs.last_error)
        self.assertEqual(root.data, data)
        self.assertEqual({child: child.data for child in root.children}, children)
        self.assertEqual(len(bpy.data.meshes), mesh_count)
        root.modular_stairs.rail_bend_radius = .09
        self.assertFalse(root.modular_stairs.last_error)
        root.modular_stairs.auto_update = False
        data = root.data
        root.modular_stairs.step_count = 12
        self.assertEqual(root.data, data)
        rebuild_stairs(root)
        self.assertNotEqual(root.data, data)

    def test_child_selection_materials_and_user_children(self):
        root = self.create()
        self.configure(root, flight_count=2, rail_enabled=True)
        handrail = next(child for child in root.children if child['modular_stair_part'] == 'handrail')
        material = bpy.data.materials.new('Custom Steel')
        handrail.data.materials.clear()
        handrail.data.materials.append(material)
        extra = bpy.data.objects.new('User Detail', None)
        bpy.context.collection.objects.link(extra)
        extra.parent = root
        bpy.context.view_layer.objects.active = handrail
        self.assertEqual(bpy.ops.modular_assets.update_stairs(), {'FINISHED'})
        self.assertEqual(handrail.data.materials[0], material)
        root.modular_stairs.rail_enabled = False
        self.assertEqual(list(root.children), [extra])
        root.modular_stairs.rail_enabled = True
        self.assertFalse(root.modular_stairs.last_error)
        self.assertIn(extra, list(root.children))

    def test_save_reopen_and_registration_lifecycle(self):
        handlers = {name: len(getattr(bpy.app.handlers, name)) for name in ('load_post', 'depsgraph_update_post', 'undo_post')}
        root = self.create()
        self.configure(root, flight_count=2, rail_enabled=True, rail_lower_count=3, rail_post_spacing=.75,
                       use_top_bevel=True, top_bevel_segments=5, rail_connector_mode='INTEGRATED',
                       rail_segments=18, rail_lower_segments=10, rail_post_segments=12,
                       rail_post_match_handrail=False, rail_connector_segments=6,
                       rail_connector_match_post=True, rail_outer_enabled=False)
        self.assertTrue(all(root.modular_stairs.is_property_set(name) for name in INPUT_FIELDS))
        root.name = 'Persistent Stairs'
        root.location = (2, 3, 4)
        path = Path(os.environ.get('STAIRS_TEST_OUTPUT') or tempfile.mkdtemp(prefix='modular_stairs_test_')) / 'stairs_configurator_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        loaded = bpy.data.objects['Persistent Stairs']
        self.assertTrue(all(loaded.modular_stairs.is_property_set(name) for name in INPUT_FIELDS))
        self.assertEqual(loaded.modular_stairs.flight_count, 2)
        self.assertEqual(loaded.modular_stairs.rail_lower_count, 3)
        self.assertAlmostEqual(loaded.modular_stairs.rail_post_spacing, .75)
        self.assertEqual(tuple(loaded.location), (2, 3, 4))
        self.assertEqual(len(loaded.children), 4)
        self.assertEqual(loaded.modular_stairs.rail_connector_mode, 'INTEGRATED')
        self.assertEqual(loaded.modular_stairs.rail_segments, 18)
        self.assertEqual(loaded.modular_stairs.rail_lower_segments, 10)
        self.assertEqual(loaded.modular_stairs.rail_post_segments, 12)
        self.assertFalse(loaded.modular_stairs.rail_post_match_handrail)
        self.assertEqual(loaded.modular_stairs.rail_connector_segments, 6)
        self.assertTrue(loaded.modular_stairs.rail_connector_match_post)
        self.assertFalse(loaded.modular_stairs.rail_outer_enabled)
        loaded.modular_stairs.rail_lower_count = 4
        self.assertFalse(loaded.modular_stairs.last_error)
        EasyGridAligner.unregister()
        EasyGridAligner.register()
        self.assertEqual(loaded.modular_stairs.rail_lower_count, 4)
        self.assertTrue(loaded.modular_stairs.is_stairs)
        self.assertEqual(handlers, {name: len(getattr(bpy.app.handlers, name)) for name in handlers})

    def test_shared_mesh_duplicate_becomes_independent(self):
        root = self.create()
        self.configure(root, rail_enabled=True)
        duplicate = root.copy()
        duplicate.data = root.data
        bpy.context.collection.objects.link(duplicate)
        original_data = root.data
        duplicate.modular_stairs.width = 1.6
        self.assertEqual(root.data, original_data)
        self.assertNotEqual(duplicate.data, original_data)
        self.assertEqual(root.modular_stairs.width, 2.0)
        self.assertEqual(len(root.children), 4)
        self.assertEqual(len(duplicate.children), 4)

    def test_undo_restores_settings_and_mesh(self):
        root = self.create()
        root.name = 'Undo Stairs'
        bpy.context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message='Configured stairs')
        original_faces = len(root.data.polygons)
        root.modular_stairs.step_count = 12
        self.assertNotEqual(len(root.data.polygons), original_faces)
        bpy.ops.ed.undo_push(message='More steps')
        self.assertEqual(bpy.ops.ed.undo(), {'FINISHED'})
        restored = bpy.data.objects['Undo Stairs']
        self.assertEqual(restored.modular_stairs.step_count, 8)
        self.assertEqual(len(restored.data.polygons), original_faces)


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ConfiguratorTest))
        if not result.wasSuccessful():
            raise RuntimeError('Configurator integration tests failed')
    finally:
        EasyGridAligner.unregister()
