"""Independent mounting, wall geometry, flight-only coverage and persistence."""
import itertools
import os
from pathlib import Path
import sys
import unittest

import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import EasyGridAligner
from EasyGridAligner.services.stairs import INPUT_FIELDS, SYSTEM_FIELDS, find_stairs
from EasyGridAligner.tests.test_stairs_type2 import components


class MountTest(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def create(self, **options):
        bpy.ops.mesh.modular_assets_add_stairs()
        root = bpy.context.object
        self.configure(root, rail_enabled=True, **options)
        return root

    def configure(self, root, **options):
        settings = root.modular_stairs
        settings.auto_update = False
        for name, value in options.items():
            setattr(settings, name, value)
        settings.auto_update = True
        self.assertFalse(settings.last_error, settings.last_error)

    def parts(self, root):
        return {child['modular_stair_part']: child for child in root.children}

    def assert_closed(self, mesh):
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            self.assertTrue(all(len(edge.link_faces) == 2 and edge.is_contiguous for edge in bm.edges), mesh.name)
            self.assertTrue(all(face.calc_area() > 1e-12 for face in bm.faces), mesh.name)
            self.assertGreater(bm.calc_volume(signed=True), 0, mesh.name)
        finally:
            bm.free()

    def test_modes_are_independent_on_both_turns(self):
        root = self.create(flight_count=3, landing_side_overhang=.25, landing_end_overhang=.3,
                           flight_gap=.4, rail_preview_walls=True)
        for style, angle, direction, inner, outer in itertools.product(
            ('TYPE_1', 'TYPE_2'), ('90', '180'), ('LEFT', 'RIGHT'),
            ('NONE', 'FLIGHT', 'WALL'), ('NONE', 'FLIGHT', 'WALL'),
        ):
            with self.subTest(style=style, angle=angle, direction=direction, inner=inner, outer=outer):
                self.configure(root, rail_type=style, turn_angle=angle, turn_direction=direction,
                               rail_inner_mount=inner, rail_outer_mount=outer)
                parts = self.parts(root)
                self.assertEqual('posts' in parts, 'FLIGHT' in (inner, outer))
                self.assertEqual('lower_rails' in parts, 'FLIGHT' in (inner, outer))
                self.assertEqual('wall_handrail' in parts, 'WALL' in (inner, outer))
                self.assertEqual('wall_brackets' in parts, 'WALL' in (inner, outer))
                self.assertEqual('preview_walls' in parts, 'WALL' in (inner, outer))
                self.assertNotIn('wall_posts', parts)
                self.assertNotIn('wall_lower_rails', parts)
                if inner == outer == 'NONE':
                    self.assertFalse(parts)
                for obj in parts.values():
                    self.assert_closed(obj.data)

    def test_flight_only_sections_and_independent_coverage(self):
        root = self.create(flight_count=3, rail_inner_mount='WALL', rail_outer_mount='FLIGHT')
        for style in ('TYPE_1', 'TYPE_2'):
            self.configure(root, rail_type=style, rail_inner_include_landings=False,
                           rail_outer_include_landings=True)
            parts = self.parts(root)
            self.assertEqual(len(components(parts['wall_handrail'].data)), 3)
            self.assertNotIn('wall_couplings', parts)
            self.assertNotIn('wall_handrail_corners', parts)
            if style == 'TYPE_1':
                self.assertEqual(len(components(parts['handrail'].data)), 1)
            self.configure(root, rail_inner_include_landings=True, rail_outer_include_landings=False)
            parts = self.parts(root)
            self.assertEqual(len(components(parts['handrail'].data)), 3)
            if style == 'TYPE_1':
                self.assertEqual(len(components(parts['wall_handrail'].data)), 1)
                self.assertIn('wall_couplings', parts)
            else:
                self.assertIn('wall_handrail_corners', parts)

    def test_wall_coverage_with_small_and_large_gaps(self):
        root = self.create(flight_count=3, rail_inner_mount='WALL', rail_outer_mount='WALL',
                           rail_preview_walls=True, landing_side_overhang=.25, landing_end_overhang=.3)
        for style, angle, direction, gap, include in itertools.product(
            ('TYPE_1', 'TYPE_2'), ('90', '180'), ('LEFT', 'RIGHT'), (.001, .2, 1.5), (False, True),
        ):
            with self.subTest(style=style, angle=angle, direction=direction, gap=gap, include=include):
                self.configure(root, rail_type=style, turn_angle=angle, turn_direction=direction,
                               flight_gap=gap, rail_inner_include_landings=include,
                               rail_outer_include_landings=not include)
                for child in root.children:
                    self.assert_closed(child.data)

    def test_wall_clearance_and_brackets_meet_preview(self):
        root = self.create(rail_inner_mount='WALL', rail_outer_mount='NONE', rail_preview_walls=True)
        for style in ('TYPE_1', 'TYPE_2'):
            self.configure(root, rail_type=style)
            parts = self.parts(root)
            handrail = parts['wall_handrail'].data
            plates = parts['wall_mount_plates'].data
            wall = parts['preview_walls']
            self.assertAlmostEqual(max(v.co.x for v in handrail.vertices), .95, places=5)
            self.assertAlmostEqual(max(v.co.x for v in plates.vertices), 1, places=5)
            self.assertAlmostEqual(min(v.co.x for v in wall.data.vertices), 1, places=5)
            self.assertAlmostEqual(max(v.co.x for v in wall.data.vertices), 1.15, places=5)
            self.assertEqual(wall.display_type, 'WIRE')
            self.assertTrue(wall.hide_render)
            self.assertEqual(find_stairs(wall), root)
            original = len(components(parts['wall_brackets'].data))
            self.configure(root, rail_wall_bracket_spacing=.4)
            self.assertGreater(len(components(self.parts(root)['wall_brackets'].data)), original)
            self.configure(root, rail_wall_bracket_spacing=.9)

    def test_short_flight_still_has_one_wall_bracket(self):
        root = self.create(step_count=1, tread=.1, riser=.1,
                           rail_inner_mount='WALL', rail_outer_mount='NONE',
                           rail_inner_include_landings=False)
        for style in ('TYPE_1', 'TYPE_2'):
            self.configure(root, rail_type=style)
            brackets = self.parts(root)['wall_brackets']
            self.assertEqual(len(components(brackets.data)), 1)
            self.assert_closed(brackets.data)

    def test_preview_toggle_selection_and_no_orphan_meshes(self):
        root = self.create(rail_inner_mount='WALL', rail_outer_mount='NONE', rail_preview_walls=True)
        preview = self.parts(root)['preview_walls']
        bpy.context.view_layer.objects.active = preview
        self.configure(root, rail_preview_walls=False)
        self.assertNotIn('preview_walls', self.parts(root))
        self.assertEqual(bpy.context.object, root)
        count = len(bpy.data.meshes)
        for index in range(5):
            self.configure(root, rail_wall_clearance=.06 if index % 2 else .05)
        self.assertEqual(len(bpy.data.meshes), count)
        before = root.data
        old_children = {child: child.data for child in root.children}
        root.modular_stairs.width = .1
        self.assertTrue(root.modular_stairs.last_error)
        self.assertEqual(root.data, before)
        self.assertEqual(old_children, {child: child.data for child in root.children})
        self.assertEqual(len(bpy.data.meshes), count)

    def test_schema4_migration_and_legacy_switches(self):
        root = self.create(flight_count=2)
        settings = root.modular_stairs
        settings.auto_update = False
        settings.rail_outer_enabled = False
        settings.schema_version = 4
        for name in SYSTEM_FIELDS:
            settings.property_unset(name)
        settings.auto_update = True
        self.assertFalse(settings.last_error)
        self.assertEqual(settings.schema_version, 11)
        self.assertEqual(settings.rail_outer_mount, 'NONE')
        self.assertEqual(settings.rail_inner_mount, 'FLIGHT')
        self.assertTrue(all(settings.is_property_set(name) for name in SYSTEM_FIELDS))
        settings.rail_inner_mount = 'WALL'
        settings.rail_outer_mount = 'FLIGHT'
        settings.rail_outer_enabled = False
        self.assertEqual(settings.rail_outer_mount, 'NONE')
        self.assertEqual(settings.rail_inner_mount, 'WALL')

    def test_preview_button_with_auto_update_disabled(self):
        root = self.create(rail_inner_mount='NONE', rail_outer_mount='WALL')
        root.modular_stairs.auto_update = False
        self.assertEqual(bpy.ops.modular_assets.preview_walls(), {'FINISHED'})
        self.assertFalse(root.modular_stairs.auto_update)
        self.assertTrue(root.modular_stairs.rail_preview_walls)
        bpy.context.view_layer.objects.active = self.parts(root)['preview_walls']
        self.assertEqual(bpy.ops.modular_assets.preview_walls(), {'FINISHED'})
        self.assertNotIn('preview_walls', self.parts(root))
        self.assertFalse(root.modular_stairs.rail_preview_walls)
        self.assertEqual(bpy.context.object, root)

    def test_save_reopen_materials_copy_and_update(self):
        root = self.create(flight_count=3, rail_type='TYPE_2', rail_inner_mount='FLIGHT',
                           rail_outer_mount='WALL', rail_outer_include_landings=False,
                           rail_wall_clearance=.065, rail_wall_bracket_spacing=.7, rail_preview_walls=True)
        material = bpy.data.materials.new('Custom Wall Handrail')
        wall_handrail = self.parts(root)['wall_handrail']
        wall_handrail.data.materials.clear()
        wall_handrail.data.materials.append(material)
        root.location = (3, 4, 5)
        root.rotation_euler = (.1, .2, .3)
        name = root.name
        path = Path(os.environ['STAIRS_TEST_OUTPUT']) / 'stairs_mounts_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        loaded = bpy.data.objects[name]
        settings = loaded.modular_stairs
        self.assertEqual(settings.rail_outer_mount, 'WALL')
        self.assertEqual(settings.rail_inner_mount, 'FLIGHT')
        self.assertFalse(settings.rail_outer_include_landings)
        self.assertAlmostEqual(settings.rail_wall_clearance, .065)
        self.assertTrue(all(settings.is_property_set(name) for name in INPUT_FIELDS))
        transform = loaded.matrix_basis.copy()
        settings.step_count = 6
        self.assertFalse(settings.last_error)
        self.assertEqual(loaded.matrix_basis, transform)
        self.assertEqual(self.parts(loaded)['wall_handrail'].data.materials[0].name, 'Custom Wall Handrail')
        bpy.context.view_layer.objects.active = self.parts(loaded)['wall_brackets']
        bpy.ops.mesh.modular_assets_add_stairs()
        copied = bpy.context.object.modular_stairs
        self.assertEqual(copied.rail_outer_mount, 'WALL')
        self.assertFalse(copied.rail_outer_include_landings)
        self.assertAlmostEqual(copied.rail_wall_clearance, .065)


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(MountTest))
        if not result.wasSuccessful():
            raise RuntimeError('Stair mounting tests failed')
    finally:
        EasyGridAligner.unregister()
