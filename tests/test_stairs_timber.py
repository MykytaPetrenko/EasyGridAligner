"""Timber board joints, independent bevels and consistent end offsets across rail styles."""
import itertools
import os
from pathlib import Path
import sys
import unittest

import bmesh
import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import EasyGridAligner
from EasyGridAligner.geometry.railing_timber import _board_rings
from EasyGridAligner.geometry.railings_balusters import _mitered_bar_rings
from EasyGridAligner.services.stairs import INPUT_FIELDS
from EasyGridAligner.tests.test_stairs_type2 import components


class TimberTest(unittest.TestCase):
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

    def wood_groups(self, mesh):
        wood = {i for face in mesh.polygons if face.material_index == 1 for i in face.vertices}
        return [group for group in components(mesh) if set(group).issubset(wood)]

    def test_four_bevel_groups_independently_and_together(self):
        root = self.create(rail_cap_max_length=.9)
        counts = {}
        for split, mask in itertools.product((False, True), itertools.product((False, True), repeat=4)):
            with self.subTest(split=split, mask=mask):
                self.configure(root, rail_cap_split=split,
                    **{f'rail_cap_bevel_{name}': enabled for name, enabled in zip(('top', 'bottom', 'start', 'end'), mask)},
                    rail_cap_top_bevel_width=.003, rail_cap_bottom_bevel_width=.001,
                    rail_cap_start_bevel_width=.004, rail_cap_end_bevel_width=.002)
                mesh = self.parts(root)['balustrade'].data
                self.assert_closed(mesh)
                counts[split, mask] = sum(face.material_index == 1 for face in mesh.polygons)
                self.assertEqual(len(mesh.materials), 2)
                self.assertEqual(len(self.wood_groups(mesh)), 8 if split else 2)
                self.assertEqual(any(face.use_smooth for face in mesh.polygons if face.material_index == 1), any(mask))
        for split in (False, True):
            for mask in itertools.product((False, True), repeat=4):
                if any(mask):
                    self.assertGreater(counts[split, mask], counts[split, (False,) * 4])

    def test_split_board_lengths_and_actual_joint_gaps(self):
        root = self.create(rail_cap_split=True, rail_cap_max_length=.9, rail_cap_joint_gap=.004)
        direction = Vector((0, -.3, .2)).normalized()
        mesh = self.parts(root)['balustrade'].data
        groups = self.wood_groups(mesh)
        self.assertEqual(len(groups), 8)
        for side in (-1, 1):
            spans = sorted((min(mesh.vertices[i].co.dot(direction) for i in group),
                            max(mesh.vertices[i].co.dot(direction) for i in group)) for group in groups
                           if mesh.vertices[group[0]].co.x * side > 0)
            self.assertTrue(all(high - low <= .9 + 1e-5 for low, high in spans))
            for previous, following in zip(spans, spans[1:]):
                self.assertAlmostEqual(following[0] - previous[1], .004, places=5)
        self.configure(root, rail_cap_joint_gap=0)
        self.assertEqual(len(self.wood_groups(self.parts(root)['balustrade'].data)), 8)

    def test_miter_joint_gap_is_measured_normal_to_cut(self):
        points = [Vector(point) for point in ((0, 0, 0), (0, -1, .5), (0, -2, .5), (1, -2, .5))]
        rings = _mitered_bar_rings(points, .065, .04)
        boards = _board_rings(points, rings, .065, .04, 10, .006)
        self.assertEqual(len(boards), 3)
        for first, second in zip(boards, boards[1:]):
            end, start = first[-1], second[0]
            normal = (end[1] - end[0]).cross(end[3] - end[0]).normalized()
            first_plane = sum(point.dot(normal) for point in end) / 4
            second_plane = sum(point.dot(normal) for point in start) / 4
            self.assertAlmostEqual(abs(second_plane - first_plane), .006, places=5)
            self.assertTrue(all(abs(point.dot(normal) - first_plane) < 1e-5 for point in end))
            self.assertTrue(all(abs(point.dot(normal) - second_plane) < 1e-5 for point in start))

    def test_asymmetric_extensions_and_setbacks_for_all_styles(self):
        root = self.create(rail_start_extension=.11, rail_end_extension=.17,
                           rail_infill_start_setback=.07, rail_infill_end_setback=.13)
        direction = Vector((0, -.3, .2)).normalized()
        length = Vector((0, -2.4, 1.6)).length
        for style in ('TYPE_1', 'TYPE_2', 'TYPE_3'):
            self.configure(root, rail_type=style)
            parts = self.parts(root)
            mesh = parts['balustrade' if style == 'TYPE_3' else 'handrail'].data
            indices = ({i for f in mesh.polygons if f.material_index == 1 for i in f.vertices}
                       if style == 'TYPE_3' else range(len(mesh.vertices)))
            stations = [(mesh.vertices[i].co - Vector((0, 0, 1.05))).dot(direction) for i in indices]
            self.assertAlmostEqual(min(stations), -.11, places=5)
            self.assertAlmostEqual(max(stations), length + .17, places=5)
            if style == 'TYPE_3':
                scale = (1 + (.2 / .3) ** 2) ** .5
                found = 0
                for group in components(mesh):
                    coords = [mesh.vertices[i].co for i in group]
                    depths = [(p.z + p.y * .2 / .3 - 1.05) / scale for p in coords]
                    if len(group) == 8 and all(-.035 - 1e-5 <= depth <= -.02 + 1e-5 for depth in depths):
                        spans = [(p - Vector((0, 0, 1.05))).dot(direction) for p in coords]
                        self.assertAlmostEqual(min(spans), .07, places=5)
                        self.assertAlmostEqual(max(spans), length - .13, places=5)
                        found += 1
                self.assertEqual(found, 2)
            else:
                mesh = parts['lower_rails'].data
                for group in components(mesh):
                    centers = [sum((mesh.vertices[i].co for i in ring), Vector()) / 8
                               for ring in (group[:8], group[-8:])]
                    positions = sorted(-p.y / abs(direction.y) for p in centers)
                    self.assertAlmostEqual(positions[0], .07, places=5)
                    self.assertAlmostEqual(positions[1], length - .13, places=5)

    def test_turns_wall_mounts_split_and_bevel_clamping(self):
        root = self.create(flight_count=3, rail_cap_split=True, rail_cap_max_length=1.0,
                           rail_cap_bevel_top=True, rail_cap_bevel_bottom=True,
                           rail_cap_bevel_start=True, rail_cap_bevel_end=True,
                           rail_cap_top_bevel_width=.1, rail_cap_bottom_bevel_width=.1,
                           rail_cap_start_bevel_width=.1, rail_cap_end_bevel_width=.1,
                           landing_side_overhang=.25, landing_end_overhang=.3)
        for angle, direction, include, mode in itertools.product(
            ('90', '180'), ('LEFT', 'RIGHT'), (False, True), ('FLIGHT', 'WALL'),
        ):
            with self.subTest(angle=angle, direction=direction, include=include, mode=mode):
                self.configure(root, turn_angle=angle, turn_direction=direction,
                               rail_outer_mount=mode, rail_outer_include_landings=include)
                for obj in root.children:
                    self.assert_closed(obj.data)

    def test_save_reopen_and_invalid_gap_recovery(self):
        root = self.create(rail_cap_split=True, rail_cap_max_length=.85, rail_cap_joint_gap=.005,
                           rail_cap_bevel_top=True, rail_cap_bevel_start=True,
                           rail_cap_top_bevel_width=.003, rail_start_extension=.09)
        name = root.name
        path = Path(os.environ['STAIRS_TEST_OUTPUT']) / 'stairs_timber_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        loaded = bpy.data.objects[name]
        settings = loaded.modular_stairs
        self.assertTrue(settings.rail_cap_split)
        self.assertAlmostEqual(settings.rail_cap_joint_gap, .005)
        self.assertAlmostEqual(settings.rail_start_extension, .09)
        self.assertTrue(settings.rail_cap_bevel_top)
        self.assertTrue(settings.rail_cap_bevel_start)
        self.assertFalse(settings.rail_cap_bevel_bottom)
        self.assertTrue(all(settings.is_property_set(name) for name in INPUT_FIELDS))
        before = {child: child.data for child in loaded.children}
        count = len(bpy.data.meshes)
        settings.rail_cap_joint_gap = 2
        self.assertTrue(settings.last_error)
        self.assertEqual(before, {child: child.data for child in loaded.children})
        self.assertEqual(len(bpy.data.meshes), count)
        settings.rail_cap_joint_gap = .004
        self.assertFalse(settings.last_error)


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TimberTest))
        if not result.wasSuccessful():
            raise RuntimeError('Timber detail tests failed')
    finally:
        EasyGridAligner.unregister()
