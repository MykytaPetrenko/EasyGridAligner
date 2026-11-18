"""Type 3 vertical balusters, inclined cuts and two persistent material slots."""
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
from EasyGridAligner.services.stairs import INPUT_FIELDS, find_stairs
from EasyGridAligner.tests.test_stairs_type2 import components


class Type3Test(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def create(self, **options):
        bpy.ops.mesh.modular_assets_add_stairs()
        root = bpy.context.object
        self.configure(root, rail_enabled=True, rail_type='TYPE_3', **options)
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
            self.assertGreater(bm.calc_volume(signed=True), 0)
        finally:
            bm.free()

    def vertical_groups(self, mesh, size):
        return [group for group in components(mesh) if len(group) == size
                and max(mesh.vertices[i].co.z for i in group) - min(mesh.vertices[i].co.z for i in group) > .5
                and len({(round(mesh.vertices[i].co.x, 5), round(mesh.vertices[i].co.y, 5))
                         for i in group}) == size // 2]

    def test_two_slots_and_vertical_baluster_sections(self):
        root = self.create()
        parts = self.parts(root)
        self.assertEqual(set(parts), {'balustrade'})
        obj = parts['balustrade']
        self.assertEqual(find_stairs(obj), root)
        self.assertEqual(list(obj.data.materials), [root.modular_stairs.rail_metal_material,
                                                  root.modular_stairs.rail_handrail_material])
        self.assertNotEqual(*obj.data.materials)
        self.assertEqual({face.material_index for face in obj.data.polygons}, {0, 1})
        groups = self.vertical_groups(obj.data, 8)
        self.assertGreater(len(groups), 20)
        scale = (1 + (.2 / .3) ** 2) ** .5
        base_offset = .2 + .05 + .035 / 2
        for group in groups:
            coords = [obj.data.vertices[index].co for index in group]
            self.assertAlmostEqual(max(p.x for p in coords) - min(p.x for p in coords), .016, places=5)
            self.assertAlmostEqual(max(p.y for p in coords) - min(p.y for p in coords), .025, places=5)
            self.assertEqual(len({(round(p.x, 5), round(p.y, 5)) for p in coords}), 4)
            for point in coords[:4]:
                self.assertAlmostEqual(point.z, -point.y * .2 / .3 + base_offset + .035 * scale / 2, places=5)
            for point in coords[4:]:
                self.assertAlmostEqual(point.z, -point.y * .2 / .3 + 1.05 - (.04 / 2 + .015) * scale, places=5)
        self.assert_closed(obj.data)

    def test_spacing_and_post_frequency(self):
        root = self.create()
        before = self.parts(root)['balustrade'].data
        count = len(self.vertical_groups(before, 8))
        posts = len(self.vertical_groups(before, 16))
        self.configure(root, rail_baluster_spacing=.07, rail_post_spacing=3)
        after = self.parts(root)['balustrade'].data
        self.assertGreater(len(self.vertical_groups(after, 8)), count)
        self.assertLess(len(self.vertical_groups(after, 16)), posts)
        self.assert_closed(after)

    def test_continuous_metal_top_rail_fits_flush_beneath_handrail(self):
        root = self.create()
        for width, thickness in ((.03, .015), (.045, .01)):
            self.configure(root, rail_base_rail_width=width, rail_top_rail_height=thickness)
            mesh = self.parts(root)['balustrade'].data
            scale = (1 + (.2 / .3) ** 2) ** .5
            top_rails = []
            for group in components(mesh):
                coords = [mesh.vertices[index].co for index in group]
                normal_depths = [(p.z + p.y * .2 / .3 - 1.05) / scale for p in coords]
                if len(group) == 8 and all(-.02 - thickness - 1e-5 <= depth <= -.02 + 1e-5 for depth in normal_depths):
                    top_rails.append(group)
                    self.assertAlmostEqual(max(p.x for p in coords) - min(p.x for p in coords), width, places=5)
                    self.assertAlmostEqual(max(normal_depths), -.02, places=5)
                    self.assertAlmostEqual(min(normal_depths), -.02 - thickness, places=5)
                    faces = [face for face in mesh.polygons if set(face.vertices).issubset(group)]
                    self.assertTrue(all(face.material_index == 0 for face in faces))
            self.assertEqual(len(top_rails), 2, 'One uninterrupted metal top rail per side')
            self.assertEqual(len(mesh.materials), 2)
            self.assert_closed(mesh)

    def test_top_rail_migration_and_copy_with_thin_existing_bottom_rail(self):
        root = self.create(rail_top_rail_height=.004, rail_base_rail_height=.01)
        settings = root.modular_stairs
        settings.auto_update = False
        settings.schema_version = 6
        settings.property_unset('rail_top_rail_height')
        bpy.ops.mesh.modular_assets_add_stairs()
        copied = bpy.context.object
        self.assertFalse(copied.modular_stairs.last_error)
        self.assertAlmostEqual(copied.modular_stairs.rail_top_rail_height, .005)
        bpy.context.view_layer.objects.active = root
        bpy.ops.modular_assets.update_stairs()
        self.assertFalse(settings.last_error)
        self.assertEqual(settings.schema_version, 10)
        self.assertAlmostEqual(settings.rail_top_rail_height, .005)

    def test_turns_gaps_and_flight_coverage(self):
        root = self.create(flight_count=3, landing_side_overhang=.25, landing_end_overhang=.3,
                           tread_finish='PLATES')
        for angle, direction, gap, include in itertools.product(
            ('90', '180'), ('LEFT', 'RIGHT'), (.001, .2, 1.5), (False, True),
        ):
            with self.subTest(angle=angle, direction=direction, gap=gap, include=include):
                self.configure(root, turn_angle=angle, turn_direction=direction, flight_gap=gap,
                               rail_inner_include_landings=include, rail_outer_include_landings=not include)
                obj = self.parts(root)['balustrade']
                self.assertEqual(len(obj.data.materials), 2)
                self.assertEqual({face.material_index for face in obj.data.polygons}, {0, 1})
                self.assert_closed(obj.data)

    def test_material_edits_from_panel_and_blender_slots(self):
        root = self.create()
        metal = bpy.data.materials.new('Custom Black Metal')
        handrail = bpy.data.materials.new('Custom Wood')
        self.configure(root, rail_metal_material=metal, rail_handrail_material=handrail)
        obj = self.parts(root)['balustrade']
        self.assertEqual(list(obj.data.materials), [metal, handrail])
        slot_material = bpy.data.materials.new('Edited In Material Properties')
        obj.data.materials[1] = slot_material
        bpy.context.view_layer.objects.active = obj
        self.configure(root, rail_baluster_spacing=.1)
        self.assertEqual(root.modular_stairs.rail_handrail_material, slot_material)
        self.assertEqual(self.parts(root)['balustrade'].data.materials[1], slot_material)
        for style in ('TYPE_1', 'TYPE_2', 'TYPE_3'):
            self.configure(root, rail_type=style)
        self.assertEqual(list(self.parts(root)['balustrade'].data.materials), [metal, slot_material])
        settings = root.modular_stairs
        settings.auto_update = False
        settings.rail_handrail_material = handrail
        self.assertTrue(settings.rail_materials_dirty)
        bpy.ops.modular_assets.update_stairs()
        self.assertEqual(self.parts(root)['balustrade'].data.materials[1], handrail)
        self.assertFalse(settings.rail_materials_dirty)

    def test_wall_mounts_two_slots_and_material_faces(self):
        root = self.create(flight_count=2, rail_outer_mount='WALL', rail_preview_walls=True)
        for include in (False, True):
            self.configure(root, rail_outer_include_landings=include)
            parts = self.parts(root)
            for role, obj in parts.items():
                if role == 'preview_walls':
                    continue
                self.assertEqual(len(obj.data.materials), 2)
                self.assert_closed(obj.data)
            self.assertEqual({f.material_index for f in parts['wall_balustrade'].data.polygons}, {0, 1})
            self.assertEqual({f.material_index for f in parts['wall_brackets'].data.polygons}, {0})
            self.assertEqual({f.material_index for f in parts['wall_mount_plates'].data.polygons}, {0})
            self.assertEqual({f.material_index for f in parts['balustrade'].data.polygons}, {0, 1})

    def test_save_reopen_and_copy_two_materials(self):
        root = self.create(flight_count=2, rail_baluster_spacing=.09, rail_baluster_width=.018,
                           rail_type3_handrail_width=.075, rail_base_clearance=.07, rail_top_rail_height=.012)
        metal = bpy.data.materials.new('Saved Metal')
        handrail = bpy.data.materials.new('Saved Handrail')
        self.configure(root, rail_metal_material=metal, rail_handrail_material=handrail)
        name = root.name
        path = Path(os.environ['STAIRS_TEST_OUTPUT']) / 'stairs_type3_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        root = bpy.data.objects[name]
        settings = root.modular_stairs
        self.assertEqual(settings.rail_type, 'TYPE_3')
        self.assertEqual(settings.rail_metal_material.name, 'Saved Metal')
        self.assertEqual(settings.rail_handrail_material.name, 'Saved Handrail')
        self.assertAlmostEqual(settings.rail_baluster_spacing, .09)
        self.assertAlmostEqual(settings.rail_type3_handrail_width, .075)
        self.assertAlmostEqual(settings.rail_top_rail_height, .012)
        self.assertTrue(all(settings.is_property_set(name) for name in INPUT_FIELDS))
        root.location = (3, 4, 5)
        transform = root.matrix_basis.copy()
        settings.step_count = 6
        self.assertFalse(settings.last_error)
        self.assertEqual(root.matrix_basis, transform)
        bpy.context.view_layer.objects.active = self.parts(root)['balustrade']
        bpy.ops.mesh.modular_assets_add_stairs()
        copied = bpy.context.object
        self.assertEqual(copied.modular_stairs.rail_type, 'TYPE_3')
        self.assertEqual(list(self.parts(copied)['balustrade'].data.materials),
                         list(self.parts(root)['balustrade'].data.materials))

    def test_invalid_settings_preserve_previous_meshes(self):
        root = self.create()
        original = root.data
        children = {child: child.data for child in root.children}
        count = len(bpy.data.meshes)
        root.modular_stairs.rail_baluster_spacing = .025
        self.assertTrue(root.modular_stairs.last_error)
        self.assertEqual(root.data, original)
        self.assertEqual({child: child.data for child in root.children}, children)
        self.assertEqual(len(bpy.data.meshes), count)
        root.modular_stairs.rail_baluster_spacing = .12
        self.assertFalse(root.modular_stairs.last_error)
        self.assertEqual(len(bpy.data.meshes), count)

    def test_schema5_migration_keeps_existing_style(self):
        root = self.create()
        settings = root.modular_stairs
        settings.auto_update = False
        settings.rail_type = 'TYPE_2'
        settings.rail_handrail_width = .054
        settings.schema_version = 5
        fields = ('rail_type3_handrail_width', 'rail_type3_handrail_thickness',
                  'rail_baluster_spacing', 'rail_baluster_width', 'rail_baluster_depth',
                  'rail_base_rail_width', 'rail_base_rail_height', 'rail_base_clearance')
        for name in fields:
            settings.property_unset(name)
        settings.auto_update = True
        self.assertFalse(settings.last_error)
        self.assertEqual(settings.schema_version, 10)
        self.assertEqual(settings.rail_type, 'TYPE_2')
        self.assertAlmostEqual(settings.rail_handrail_width, .054)
        self.assertTrue(all(settings.is_property_set(name) for name in fields))
        self.configure(root, rail_type='TYPE_3')
        self.assertAlmostEqual(settings.rail_baluster_spacing, .12)

    def test_pending_material_choice_survives_save_with_auto_update_off(self):
        root = self.create()
        settings = root.modular_stairs
        settings.auto_update = False
        material = bpy.data.materials.new('Pending Handrail Material')
        settings.rail_handrail_material = material
        name = root.name
        path = Path(os.environ['STAIRS_TEST_OUTPUT']) / 'stairs_type3_pending_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        loaded = bpy.data.objects[name]
        self.assertTrue(loaded.modular_stairs.rail_materials_dirty)
        bpy.context.view_layer.objects.active = loaded
        bpy.ops.modular_assets.update_stairs()
        self.assertEqual(self.parts(loaded)['balustrade'].data.materials[1].name, 'Pending Handrail Material')
        self.assertFalse(loaded.modular_stairs.rail_materials_dirty)


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Type3Test))
        if not result.wasSuccessful():
            raise RuntimeError('Type 3 baluster tests failed')
    finally:
        EasyGridAligner.unregister()
