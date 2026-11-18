"""Type 2 square-post/rectangular-handrail and fixed-connector integration tests."""
import itertools
import os
from pathlib import Path
import sys
import tempfile
import unittest

import bmesh
import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import EasyGridAligner
from EasyGridAligner.services.stairs import INPUT_FIELDS


def components(mesh):
    adjacency = [set() for _ in mesh.vertices]
    for edge in mesh.edges:
        first, second = edge.vertices
        adjacency[first].add(second)
        adjacency[second].add(first)
    remaining, result = set(range(len(mesh.vertices))), []
    while remaining:
        pending, visited = {remaining.pop()}, set()
        while pending:
            index = pending.pop()
            visited.add(index)
            pending.update(adjacency[index] - visited)
        remaining.difference_update(visited)
        result.append(sorted(visited))
    return result


def center(mesh, indices):
    return sum((mesh.vertices[index].co for index in indices), Vector()) / len(indices)


class Type2Test(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def create(self, **parameters):
        self.assertEqual(bpy.ops.mesh.modular_assets_add_stairs(), {'FINISHED'})
        root = bpy.context.object
        self.configure(root, rail_enabled=True, rail_type='TYPE_2', **parameters)
        return root

    def configure(self, root, **parameters):
        settings = root.modular_stairs
        settings.auto_update = False
        for name, value in parameters.items():
            setattr(settings, name, value)
        settings.auto_update = True
        self.assertFalse(settings.last_error, settings.last_error)

    def parts(self, root):
        return {child['modular_stair_part']: child for child in root.children}

    def assert_closed(self, mesh):
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            self.assertTrue(all(len(edge.link_faces) == 2 for edge in bm.edges))
            self.assertTrue(all(edge.is_contiguous for edge in bm.edges))
            self.assertTrue(all(face.calc_area() > 0 for face in bm.faces))
            self.assertGreater(bm.calc_volume(signed=True), 0)
        finally:
            bm.free()

    def test_square_posts_and_rectangular_straight_sections(self):
        root = self.create()
        parts = self.parts(root)
        self.assertEqual(set(parts), {'handrail', 'lower_rails', 'posts', 'connectors'})
        post_mesh = parts['posts'].data
        for group in components(post_mesh):
            self.assertEqual(len(group), 24)
            ring = [post_mesh.vertices[index].co for index in group[:4]]
            self.assertEqual(len({round(point.x, 5) for point in ring}), 2)
            self.assertEqual(len({round(point.y, 5) for point in ring}), 2)
        handrail = parts['handrail'].data
        groups = components(handrail)
        self.assertEqual(len(groups), 2)
        for group in groups:
            self.assertEqual(len(group), 8)
            ring = [handrail.vertices[index].co for index in group[:4]]
            lengths = sorted((ring[(index + 1) % 4] - ring[index]).length for index in range(4))
            for actual, expected in zip(lengths, (.025, .025, .05, .05)):
                self.assertAlmostEqual(actual, expected, places=5)
        self.assertTrue(all(len(face.vertices) == 4 and not face.use_smooth for face in handrail.polygons))
        self.assertEqual(len(components(parts['lower_rails'].data)), 8)
        self.assertTrue(all(len(group) == 16 for group in components(parts['lower_rails'].data)))
        for obj in [root, *parts.values()]:
            self.assert_closed(obj.data)

    def test_one_fixed_fitting_per_corner_and_trimmed_straights(self):
        root = self.create(flight_count=2, turn_angle='180')
        parts = self.parts(root)
        self.assertNotIn('couplings', parts)
        handrail = parts['handrail'].data
        fittings = parts['handrail_corners'].data
        bars, elbows = components(handrail), components(fittings)
        self.assertEqual(len(elbows), 8)
        self.assertEqual(len(bars), 10)
        self.assertTrue(all(len(group) == 12 for group in elbows), 'A corner must be one three-ring fitting, without a hinge')
        self.assertTrue(all(len(group) == 8 for group in bars))
        infill_elbows = components(parts['infill_corners'].data)
        self.assertEqual(len(infill_elbows), len(elbows) * 4)
        self.assertTrue(all(len(group) == 24 for group in infill_elbows))
        bar_ends = [center(handrail, ring) for group in bars for ring in (group[:4], group[-4:])]
        fitting_ends = [center(fittings, ring) for group in elbows for ring in (group[:4], group[-4:])]
        self.assertTrue(all(any((end - candidate).length < 1e-5 for candidate in bar_ends) for end in fitting_ends))
        self.assertEqual(sum(not any((end - candidate).length < 1e-5 for candidate in fitting_ends)
                             for end in bar_ends), 4)
        for obj in parts.values():
            self.assert_closed(obj.data)

    def test_turns_gaps_and_support_modes(self):
        root = self.create()
        for angle, direction, gap, mode in itertools.product(
            ('90', '180'), ('LEFT', 'RIGHT'), (.001, .2, 1.5), ('SEPARATE', 'INTEGRATED'),
        ):
            with self.subTest(angle=angle, direction=direction, gap=gap, mode=mode):
                self.configure(root, flight_count=3, turn_angle=angle, turn_direction=direction,
                               flight_gap=gap, landing_side_overhang=.1, landing_end_overhang=.2,
                               rail_connector_mode=mode, use_top_bevel=True, use_bottom_bevel=True)
                parts = self.parts(root)
                self.assertEqual('connectors' in parts, mode == 'SEPARATE')
                self.assertIn('handrail_corners', parts)
                self.assertIn('infill_corners', parts)
                self.assertTrue(all(len(group) == (24 if mode == 'SEPARATE' else 32)
                                    for group in components(parts['posts'].data)))
                for obj in [root, *parts.values()]:
                    self.assert_closed(obj.data)

    def test_type_switch_preserves_settings_transform_and_material(self):
        root = self.create(flight_count=2, rail_handrail_width=.054, rail_handrail_thickness=.022,
                           rail_post_size=.045)
        root.location = (3, 4, 5)
        root.rotation_euler = (.1, .2, .3)
        transform = root.matrix_basis.copy()
        material = bpy.data.materials.new('Rectangular Handrail Material')
        handrail = self.parts(root)['handrail']
        handrail.data.materials.clear()
        handrail.data.materials.append(material)
        bpy.context.view_layer.objects.active = self.parts(root)['handrail_corners']
        self.configure(root, rail_type='TYPE_1')
        self.assertEqual(bpy.context.view_layer.objects.active, root)
        self.assertIn('couplings', self.parts(root))
        self.assertNotIn('handrail_corners', self.parts(root))
        self.configure(root, rail_type='TYPE_2')
        self.assertIn('handrail_corners', self.parts(root))
        self.assertNotIn('couplings', self.parts(root))
        self.assertEqual(root.matrix_basis, transform)
        self.assertEqual(self.parts(root)['handrail'].data.materials[0], material)
        self.assertAlmostEqual(root.modular_stairs.rail_handrail_width, .054)
        self.assertAlmostEqual(root.modular_stairs.rail_post_size, .045)

    def test_outer_switch_infill_count_and_invalid_size(self):
        root = self.create(flight_count=2, turn_angle='90', flight_gap=1.5, rail_outer_enabled=False)
        parts = self.parts(root)
        original = len(components(parts['infill_corners'].data))
        self.configure(root, rail_lower_count=2)
        self.assertEqual(len(components(self.parts(root)['infill_corners'].data)) * 2, original)
        self.configure(root, rail_lower_count=0)
        self.assertNotIn('lower_rails', self.parts(root))
        self.assertNotIn('infill_corners', self.parts(root))
        before = root.data
        child_data = {child: child.data for child in root.children}
        root.modular_stairs.rail_handrail_width = .25
        self.assertTrue(root.modular_stairs.last_error)
        self.assertEqual(root.data, before)
        self.assertEqual({child: child.data for child in root.children}, child_data)
        root.modular_stairs.rail_handrail_width = .05
        self.assertFalse(root.modular_stairs.last_error)

    def test_type2_persistence(self):
        root = self.create(flight_count=2, turn_angle='90', rail_handrail_width=.054,
                           rail_handrail_thickness=.022, rail_post_size=.045,
                           rail_corner_length=.055, rail_corner_allowance=.0015,
                           rail_connector_mode='INTEGRATED', rail_lower_count=3)
        root.name = 'Type 2 Saved Stairs'
        output = Path(os.environ.get('STAIRS_TEST_OUTPUT') or tempfile.mkdtemp(prefix='stairs_type2_'))
        path = output / 'stairs_type2_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        loaded = bpy.data.objects['Type 2 Saved Stairs']
        self.assertEqual(loaded.modular_stairs.rail_type, 'TYPE_2')
        self.assertEqual(loaded.modular_stairs.schema_version, 8)
        self.assertTrue(all(loaded.modular_stairs.is_property_set(name) for name in INPUT_FIELDS))
        self.assertAlmostEqual(loaded.modular_stairs.rail_handrail_width, .054)
        self.assertAlmostEqual(loaded.modular_stairs.rail_handrail_thickness, .022)
        self.assertAlmostEqual(loaded.modular_stairs.rail_post_size, .045)
        self.assertAlmostEqual(loaded.modular_stairs.rail_corner_length, .055)
        self.assertAlmostEqual(loaded.modular_stairs.rail_corner_allowance, .0015)
        loaded.modular_stairs.rail_lower_count = 4
        self.assertFalse(loaded.modular_stairs.last_error)

    def test_schema2_migration_initializes_type2_dimensions(self):
        root = self.create(flight_count=2)
        settings = root.modular_stairs
        settings.auto_update = False
        settings.rail_type = 'TYPE_1'
        settings.rail_segments = 24
        settings.schema_version = 2
        fields = ('rail_handrail_width', 'rail_handrail_thickness', 'rail_post_size',
                  'rail_corner_length', 'rail_corner_allowance')
        for name in fields:
            settings.property_unset(name)
        settings.auto_update = True
        self.assertFalse(settings.last_error, settings.last_error)
        self.assertEqual(settings.schema_version, 8)
        self.assertEqual(settings.rail_segments, 24)
        self.assertEqual(settings.rail_type, 'TYPE_1')
        self.assertTrue(all(settings.is_property_set(name) for name in fields))
        settings.rail_type = 'TYPE_2'
        self.assertFalse(settings.last_error, settings.last_error)
        self.assertAlmostEqual(settings.rail_handrail_width, .05)
        self.assertAlmostEqual(settings.rail_handrail_thickness, .025)
        self.assertAlmostEqual(settings.rail_post_size, .04)


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Type2Test))
        if not result.wasSuccessful():
            raise RuntimeError('Type 2 railing tests failed')
    finally:
        EasyGridAligner.unregister()
