"""Regression checks for connected posts and per-component railing resolution."""
import itertools
from pathlib import Path
import sys
import unittest

import bmesh
import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import EasyGridAligner
from EasyGridAligner.services.stairs import INPUT_FIELDS, rebuild_stairs


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
        result.append(visited)
    return result


class RailingDetailTest(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def create(self, **parameters):
        self.assertEqual(bpy.ops.mesh.modular_assets_add_stairs(), {'FINISHED'})
        root = bpy.context.object
        self.configure(root, rail_enabled=True, **parameters)
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

    def assert_post_topology(self, mesh, sides, integrated):
        groups = components(mesh)
        self.assertTrue(groups)
        # Six rings cover flange, shaft and collar. An integral stem adds two.
        self.assertTrue(all(len(group) == sides * (8 if integrated else 6) for group in groups))
        caps = [face for face in mesh.polygons if len(face.vertices) > 4]
        self.assertEqual(len(caps), len(groups) * 2)
        self.assertTrue(all(len(face.vertices) == sides for face in caps))
        # All shoulders are flat annuli, including the integral stem transition.
        # A cone/frustum would introduce faces with an intermediate Z normal.
        self.assertTrue(all(abs(face.normal.z) < 1e-5 or abs(face.normal.z) > 1 - 1e-5
                            for face in mesh.polygons))
        for group in groups:
            low = min(mesh.vertices[index].co.z for index in group)
            high = max(mesh.vertices[index].co.z for index in group)
            # No duplicate shaft ring or cap exists at the top of the collar.
            self.assertEqual(sum(abs(mesh.vertices[index].co.z - high) < 1e-6 for index in group), sides)
            self.assertEqual(sum(abs(mesh.vertices[index].co.z - low) < 1e-6 for index in group), sides)
            levels = {round(mesh.vertices[index].co.z, 5) for index in group}
            self.assertEqual(len(levels), 5 if integrated else 4)
        self.assert_closed(mesh)
        return len(groups)

    def test_defaults_and_continuous_post_collar(self):
        root = self.create()
        settings = root.modular_stairs
        self.assertEqual(settings.rail_segments, 16)
        self.assertEqual(settings.rail_lower_segments, 8)
        self.assertEqual(settings.rail_post_segments, 16)
        self.assertTrue(settings.rail_post_match_handrail)
        self.assertEqual(settings.rail_connector_segments, 8)
        self.assertFalse(settings.rail_connector_match_post)
        self.assertEqual(settings.rail_connector_mode, 'SEPARATE')
        parts = self.parts(root)
        post_count = self.assert_post_topology(parts['posts'].data, 16, False)
        self.assertEqual(len(components(parts['connectors'].data)), post_count)
        self.assertEqual({len(face.vertices) for face in parts['connectors'].data.polygons if len(face.vertices) > 4}, {8})
        self.assertEqual({len(face.vertices) for face in parts['handrail'].data.polygons if len(face.vertices) > 4}, {16})
        self.assertEqual({len(face.vertices) for face in parts['lower_rails'].data.polygons if len(face.vertices) > 4}, {8})

    def test_resolution_inheritance_and_integrated_stem(self):
        root = self.create(rail_segments=24)
        self.assert_post_topology(self.parts(root)['posts'].data, 24, False)
        self.configure(root, rail_post_match_handrail=False, rail_post_segments=12, rail_connector_match_post=True)
        parts = self.parts(root)
        self.assert_post_topology(parts['posts'].data, 12, False)
        self.assertEqual({len(face.vertices) for face in parts['connectors'].data.polygons if len(face.vertices) > 4}, {12})
        bpy.context.view_layer.objects.active = parts['connectors']
        self.configure(root, rail_connector_mode='INTEGRATED', rail_connector_match_post=False, rail_connector_segments=8)
        self.assertEqual(bpy.context.view_layer.objects.active, root)
        parts = self.parts(root)
        self.assertNotIn('connectors', parts)
        self.assert_post_topology(parts['posts'].data, 12, True)
        root.modular_stairs.rail_segments = 32
        self.assert_post_topology(self.parts(root)['posts'].data, 12, True)
        root.modular_stairs.rail_post_match_handrail = True
        self.assert_post_topology(self.parts(root)['posts'].data, 32, True)
        root.modular_stairs.rail_connector_mode = 'SEPARATE'
        self.assertIn('connectors', self.parts(root))
        self.assert_post_topology(self.parts(root)['posts'].data, 32, False)

    def test_outer_switch_tracks_turn_direction(self):
        for angle, direction in itertools.product(('90', '180'), ('LEFT', 'RIGHT')):
            with self.subTest(angle=angle, direction=direction):
                root = self.create(flight_count=3, turn_angle=angle, turn_direction=direction,
                                   rail_outer_enabled=False)
                parts = self.parts(root)
                self.assertEqual(len(components(parts['handrail'].data)), 1)
                self.assertEqual(len(components(parts['lower_rails'].data)), 4)
                expected = sorted(tuple(round(value, 5) for value in vertex.co) for vertex in parts['handrail'].data.vertices)
                self.configure(root, rail_outer_enabled=True, rail_left=direction == 'LEFT', rail_right=direction == 'RIGHT')
                actual = sorted(tuple(round(value, 5) for value in vertex.co) for vertex in self.parts(root)['handrail'].data.vertices)
                self.assertEqual(actual, expected)
                self.configure(root, rail_left=True, rail_right=True)
                self.assertEqual(len(components(self.parts(root)['handrail'].data)), 2)

    def test_both_support_modes_on_landings(self):
        for angle, mode, match in itertools.product(('90', '180'), ('SEPARATE', 'INTEGRATED'), (False, True)):
            with self.subTest(angle=angle, mode=mode, match=match):
                root = self.create(flight_count=3, turn_angle=angle, turn_direction='LEFT',
                                   landing_side_overhang=.1, landing_end_overhang=.2,
                                   rail_connector_mode=mode, rail_post_match_handrail=match,
                                   rail_post_segments=12, rail_connector_segments=8)
                for part in self.parts(root).values():
                    self.assert_closed(part.data)
                self.assert_post_topology(self.parts(root)['posts'].data, 16 if match else 12, mode == 'INTEGRATED')

    def test_saved_schema_migration_keeps_old_handrail_setting(self):
        root = self.create()
        settings = root.modular_stairs
        settings.auto_update = False
        settings.rail_segments = 20
        settings.schema_version = 1
        for name in ('rail_lower_segments', 'rail_post_segments', 'rail_post_match_handrail',
                     'rail_connector_segments', 'rail_connector_match_post', 'rail_connector_mode', 'rail_outer_enabled'):
            settings.property_unset(name)
        rebuild_stairs(root)
        self.assertEqual(settings.schema_version, 2)
        self.assertEqual(settings.rail_segments, 20)
        self.assertEqual(settings.rail_lower_segments, 8)
        self.assertFalse(settings.rail_connector_match_post)
        self.assertTrue(all(settings.is_property_set(name) for name in INPUT_FIELDS))
        self.assert_post_topology(self.parts(root)['posts'].data, 20, False)


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(RailingDetailTest))
        if not result.wasSuccessful():
            raise RuntimeError('Railing detail regression tests failed')
    finally:
        EasyGridAligner.unregister()
