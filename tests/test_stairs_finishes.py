"""Finished levels, exact volume partition, material persistence and landing turns."""
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
from EasyGridAligner.geometry.railing_parts import _railing_route
from EasyGridAligner.geometry.stairs import _flight_layout, build_stair_mesh
from EasyGridAligner.services.stairs import INPUT_FIELDS, STAIR_FIELDS, find_stairs


def volume(mesh):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        if not all(len(edge.link_faces) == 2 and edge.is_contiguous for edge in bm.edges):
            raise AssertionError(f'{mesh.name}: non-manifold or inconsistent edges')
        if not all(face.calc_area() > 1e-12 for face in bm.faces):
            raise AssertionError(f'{mesh.name}: zero area faces')
        return bm.calc_volume(signed=True)
    finally:
        bm.free()


class FinishTest(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def create(self, **options):
        bpy.ops.mesh.modular_assets_add_stairs()
        root = bpy.context.object
        self.configure(root, **options)
        return root

    def configure(self, root, **options):
        root.modular_stairs.auto_update = False
        for name, value in options.items():
            setattr(root.modular_stairs, name, value)
        root.modular_stairs.auto_update = True
        self.assertFalse(root.modular_stairs.last_error, root.modular_stairs.last_error)

    def plates(self, root):
        return next(child for child in root.children if child.get('modular_stair_part') == 'tread_plates')

    def test_exact_partition_and_levels(self):
        root = self.create(tread_finish='PLATES', plate_bevel_width=0)
        for flights, angle, offset, ribs, cut in itertools.product(
            (1, 3), ('90', '180'), (-.05, 0, .05), (False, True), ('NONE', 'FLOOR', 'BOX'),
        ):
            with self.subTest(flights=flights, angle=angle, offset=offset, ribs=ribs, cut=cut):
                self.configure(root, flight_count=flights, turn_angle=angle, riser_offset=offset,
                               use_side_ribs=ribs, start_cut_type=cut, landing_side_overhang=.2,
                               landing_end_overhang=.15)
                parameters = {name: getattr(root.modular_stairs, name) for name in STAIR_FIELDS}
                original = build_stair_mesh('Original', **(parameters | {'tread_finish': 'ORIGINAL'}))
                try:
                    plates = self.plates(root)
                    self.assertGreater(volume(root.data), 0)
                    self.assertGreater(volume(plates.data), 0)
                    self.assertAlmostEqual(volume(root.data) + volume(plates.data), volume(original), places=4)
                    self.assertAlmostEqual(max(v.co.z for v in plates.data.vertices),
                                           max(v.co.z for v in original.vertices), places=5)
                    self.assertAlmostEqual(min(v.co.z for v in root.data.vertices),
                                           min(v.co.z for v in original.vertices), places=5)
                    self.assertEqual(find_stairs(plates), root)
                finally:
                    bpy.data.meshes.remove(original)

    def test_plate_bevels_are_independent(self):
        root = self.create(tread_finish='PLATES', step_count=1, use_top_bevel=True, use_bottom_bevel=True)
        counts = {}
        for front, sides in itertools.product((False, True), repeat=2):
            self.configure(root, plate_bevel_front=front, plate_bevel_sides=sides)
            plates = self.plates(root)
            self.assertGreater(volume(plates.data), 0)
            self.assertAlmostEqual(max(v.co.z for v in plates.data.vertices), .2, places=5)
            self.assertAlmostEqual(min(v.co.z for v in plates.data.vertices), .18, places=5)
            counts[front, sides] = len(plates.data.polygons)
        self.assertEqual(counts[False, False], 6)
        self.assertGreater(counts[True, False], 6)
        self.assertGreater(counts[False, True], counts[True, False])
        self.assertGreater(counts[True, True], counts[False, True])

    def test_types_supports_and_finish_switch(self):
        root = self.create(tread_finish='PLATES', rail_enabled=True, flight_count=2,
                           landing_side_overhang=.25, landing_end_overhang=.3)
        for kind, angle, direction in itertools.product(('TYPE_1', 'TYPE_2'), ('90', '180'), ('LEFT', 'RIGHT')):
            self.configure(root, rail_type=kind, turn_angle=angle, turn_direction=direction)
            for child in root.children:
                self.assertGreater(volume(child.data), 0)
        material = bpy.data.materials.new('Custom Tread Finish')
        root.modular_stairs.plate_material = material
        self.assertEqual(self.plates(root).data.materials[0], material)
        self.assertNotEqual(root.data.materials[0], material)
        root.location = (2, 3, 4)
        bpy.context.view_layer.objects.active = self.plates(root)
        self.configure(root, tread_finish='ORIGINAL')
        self.assertFalse(any(child.get('modular_stair_part') == 'tread_plates' for child in root.children))
        self.assertEqual(bpy.context.object, root)
        self.configure(root, tread_finish='PLATES', plate_thickness=.03)
        self.assertEqual(self.plates(root).data.materials[0], material)
        self.assertEqual(tuple(root.location), (2, 3, 4))

    def test_invalid_thickness_keeps_geometry(self):
        root = self.create(tread_finish='PLATES')
        original, plates = root.data, self.plates(root).data
        root.modular_stairs.plate_thickness = .3
        self.assertTrue(root.modular_stairs.last_error)
        self.assertEqual(root.data, original)
        self.assertEqual(self.plates(root).data, plates)
        root.modular_stairs.plate_thickness = .02
        self.assertFalse(root.modular_stairs.last_error)

    def test_old_finish_migration_and_new_stairs_copy(self):
        root = self.create(use_top_bevel=True, top_bevel_width=.014)
        settings = root.modular_stairs
        settings.auto_update = False
        settings.schema_version = 3
        for name in ('tread_finish', 'plate_thickness', 'plate_bevel_front', 'plate_bevel_sides',
                     'plate_bevel_width', 'plate_bevel_segments', 'plate_bevel_profile'):
            settings.property_unset(name)
        settings.auto_update = True
        self.assertFalse(settings.last_error)
        self.assertEqual(settings.schema_version, 5)
        self.assertEqual(settings.tread_finish, 'ORIGINAL')
        self.assertTrue(settings.use_top_bevel)
        self.assertAlmostEqual(settings.top_bevel_width, .014)
        self.configure(root, tread_finish='PLATES', plate_thickness=.032)
        material = settings.plate_material
        bpy.ops.mesh.modular_assets_add_stairs()
        copied = bpy.context.object
        self.assertNotEqual(copied, root)
        self.assertEqual(copied.modular_stairs.tread_finish, 'PLATES')
        self.assertAlmostEqual(copied.modular_stairs.plate_thickness, .032)
        self.assertEqual(copied.modular_stairs.plate_material, material)

    def test_beveled_plates_with_offsets_and_reinforcement(self):
        root = self.create(tread_finish='PLATES', flight_count=3, use_side_ribs=True)
        for angle, offset, cut_top, width, profile in itertools.product(
            ('90', '180'), (-.05, .05), (False, True), (.003, .1), (.2, .8),
        ):
            self.configure(root, turn_angle=angle, riser_offset=offset, cut_top=cut_top,
                           plate_bevel_width=width, plate_bevel_profile=profile)
            self.assertGreater(volume(root.data), 0)
            self.assertGreater(volume(self.plates(root).data), 0)
            self.assertAlmostEqual(max(v.co.z for v in self.plates(root).data.vertices), 4.8, places=5)

    def test_plate_settings_save_reopen(self):
        root = self.create(tread_finish='PLATES', plate_thickness=.025, plate_bevel_front=False,
                           plate_bevel_width=.004, plate_bevel_segments=4, flight_count=2)
        material = bpy.data.materials.new('Saved Plate Material')
        root.modular_stairs.plate_material = material
        name = root.name
        path = Path(os.environ['STAIRS_TEST_OUTPUT']) / 'stairs_finishes_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        loaded = bpy.data.objects[name]
        self.assertEqual(loaded.modular_stairs.tread_finish, 'PLATES')
        self.assertAlmostEqual(loaded.modular_stairs.plate_thickness, .025)
        self.assertFalse(loaded.modular_stairs.plate_bevel_front)
        self.assertEqual(loaded.modular_stairs.plate_material.name, 'Saved Plate Material')
        self.assertTrue(all(loaded.modular_stairs.is_property_set(name) for name in INPUT_FIELDS))
        loaded.modular_stairs.tread = .35
        self.assertFalse(loaded.modular_stairs.last_error)
        self.assertEqual(self.plates(loaded).data.materials[0], loaded.modular_stairs.plate_material)

    def test_overhang_path_levels_before_turning(self):
        root = self.create()
        settings = root.modular_stairs
        for angle, direction in itertools.product(('90', '180'), ('LEFT', 'RIGHT')):
            self.configure(root, flight_count=3, turn_angle=angle, turn_direction=direction,
                           landing_side_overhang=.3, landing_end_overhang=.4)
            p = {name: getattr(settings, name) for name in STAIR_FIELDS}
            frames, landings = _flight_layout(p['flight_count'], p['step_count'], p['width'], p['riser'],
                p['tread'], p['turn_angle'], p['turn_direction'], p['landing_depth'], p['flight_gap'],
                p['landing_side_overhang'], p['landing_end_overhang'])
            for side in (-1, 1):
                controls, _ = _railing_route(p, frames, landings, side, .08, .09, .9)
                for previous, point, following in zip(controls, controls[1:], controls[2:]):
                    incoming, outgoing = point - previous, following - point
                    a, b = incoming.xy, outgoing.xy
                    if abs(incoming.z) > 1e-5 or abs(outgoing.z) > 1e-5:
                        self.assertAlmostEqual(a.normalized().dot(b.normalized()), 1, places=5,
                                               msg='Slope and plan direction must change at separate corners')


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(FinishTest))
        if not result.wasSuccessful():
            raise RuntimeError('Stair finish tests failed')
    finally:
        EasyGridAligner.unregister()
