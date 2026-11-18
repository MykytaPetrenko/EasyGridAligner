"""Finish faces shade smoothly; only surviving unrounded corners stay sharp."""
import itertools
from pathlib import Path
import sys
import unittest

import bmesh
import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import EasyGridAligner
from EasyGridAligner.geometry.railing_parts import _make_mesh
from EasyGridAligner.geometry.railing_timber import append_timber_cap, _board_rings
from EasyGridAligner.geometry.railings_balusters import _mitered_bar_rings
from EasyGridAligner.services.stairs import INPUT_FIELDS


class FinishShadingTest(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def inspect(self, mesh):
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.normal_update()
        self.addCleanup(bm.free)
        return bm

    def configure(self, root, **options):
        settings = root.modular_stairs
        settings.auto_update = False
        for name, value in options.items():
            setattr(settings, name, value)
        settings.auto_update = True
        self.assertFalse(settings.last_error, settings.last_error)

    def root(self, **options):
        bpy.ops.mesh.modular_assets_add_stairs()
        root = bpy.context.object
        self.configure(root, **options)
        return root

    def plate(self, **options):
        root = self.root(step_count=1, tread_finish='PLATES', **options)
        return next(child.data for child in root.children if child.get('modular_stair_part') == 'tread_plates')

    def timber(self, smooth=True, points=None, rings=None, **options):
        points = points if points is not None else [Vector((0, 0, 0)), Vector((0, 1, 0))]
        rings = rings if rings is not None else _mitered_bar_rings(points, .065, .04)
        part, sharp = ([], [], []), []
        append_timber_cap(part, points, rings, .065, .04, smooth=smooth, sharp_edges=sharp, **options)
        mesh = _make_mesh('Shading Test Timber', part, sharp_edges=sharp)
        self.addCleanup(bpy.data.meshes.remove, mesh)
        return mesh

    def assert_closed(self, bm):
        self.assertTrue(all(len(edge.link_faces) == 2 and edge.is_contiguous for edge in bm.edges))
        self.assertTrue(all(face.calc_area() > 1e-12 for face in bm.faces))
        self.assertGreater(bm.calc_volume(signed=True), 0)
        self.assertTrue(all(edge.smooth for edge in bm.edges if edge.calc_face_angle(0.0) <= .0001))

    def test_plate_top_bevel_boundaries_smooth_rear_and_vertical_corner_sharp(self):
        bm = self.inspect(self.plate(plate_bevel_front=True, plate_bevel_sides=True, plate_bevel_corners=False))
        self.assert_closed(bm)
        self.assertTrue(all(face.smooth for face in bm.faces))
        top = next(face for face in bm.faces if face.normal.z > .999)
        rounded_top = [edge for edge in top.edges if not all(abs(v.co.y + .3) < 1e-5 for v in edge.verts)]
        self.assertTrue(rounded_top)
        self.assertTrue(all(edge.smooth for edge in rounded_top), 'No sharp loop around top/bevel tangent')
        rear = next(face for face in bm.faces if face.normal.y < -.999)
        self.assertTrue(all(not edge.smooth for edge in rear.edges), 'The unrounded back cap remains sharp')
        vertical_corners = [edge for edge in bm.edges
                            if any(face.normal.x < -.999 for face in edge.link_faces)
                            and any(face.normal.y > .999 for face in edge.link_faces)]
        self.assertEqual(len(vertical_corners), 1)
        self.assertFalse(vertical_corners[0].smooth)
        miter_seams = [edge for edge in bm.edges
                       if all(face.normal.z > .01 for face in edge.link_faces)
                       and any(face.normal.x < -.01 and abs(face.normal.y) < 1e-5 for face in edge.link_faces)
                       and any(face.normal.y > .01 and abs(face.normal.x) < 1e-5 for face in edge.link_faces)]
        self.assertTrue(miter_seams)
        self.assertTrue(all(not edge.smooth for edge in miter_seams), 'Unrounded corner continues through the bevel miter')

    def test_front_corner_bevel_removes_front_crease(self):
        bm = self.inspect(self.plate(plate_bevel_front=True, plate_bevel_sides=True, plate_bevel_corners=True))
        self.assert_closed(bm)
        front_region = [edge for edge in bm.edges if all(v.co.y > -.05 and v.co.z > .18001 for v in edge.verts)]
        self.assertTrue(front_region)
        self.assertTrue(all(edge.smooth for edge in front_region), 'Front corner rounding must be one smooth surface')
        rear = next(face for face in bm.faces if face.normal.y < -.999)
        self.assertTrue(all(not edge.smooth for edge in rear.edges))

    def test_only_vertical_corner_bevel_keeps_top_outline_sharp(self):
        bm = self.inspect(self.plate(plate_bevel_front=False, plate_bevel_sides=False, plate_bevel_corners=True))
        self.assert_closed(bm)
        self.assertGreater(len(bm.faces), 6)
        top = next(face for face in bm.faces if face.normal.z > .999)
        self.assertTrue(all(not edge.smooth for edge in top.edges))
        vertical_curves = [edge for edge in bm.edges if all(abs(face.normal.z) < .0001 for face in edge.link_faces)
                           and edge.calc_face_angle(0.0) > .01]
        self.assertTrue(any(edge.smooth for edge in vertical_curves))

    def test_timber_top_bevel_smooth_with_unrounded_caps_and_bottom(self):
        bm = self.inspect(self.timber(bevel_top=True))
        self.assert_closed(bm)
        self.assertTrue(all(face.smooth for face in bm.faces))
        top = next(face for face in bm.faces if face.normal.z > .999)
        longitudinal = [edge for edge in top.edges if abs(edge.verts[1].co.y - edge.verts[0].co.y) > .5]
        self.assertEqual(len(longitudinal), 2)
        self.assertTrue(all(edge.smooth for edge in longitudinal))
        for face in bm.faces:
            if abs(face.normal.y) > .999 or face.normal.z < -.999:
                self.assertTrue(all(not edge.smooth for edge in face.edges))

    def test_end_bevel_respects_top_bottom_and_preserves_unrounded_sharp_edges(self):
        for top, bottom in itertools.product((False, True), repeat=2):
            with self.subTest(top=top, bottom=bottom):
                bm = self.inspect(self.timber(bevel_top=top, bevel_bottom=bottom, bevel_ends=True,
                                             top_width=.012, bottom_width=.006, ends_width=.012))
                self.assert_closed(bm)
                excluded_z = -.02 if top and not bottom else .02 if bottom and not top else None
                for sign in (-1, 1):
                    cap = next(face for face in bm.faces if face.normal.y * sign > .999)
                    for edge in cap.edges:
                        excluded = excluded_z is not None and all(abs(v.co.z - excluded_z) < 1e-5
                                                                   for v in edge.verts)
                        self.assertEqual(edge.smooth, not excluded,
                                         'Only the excluded horizontal end edge stays sharp')
                    if excluded_z is not None:
                        border = [edge for edge in cap.edges
                                  if all(abs(v.co.z - excluded_z) < 1e-5 for v in edge.verts)]
                        self.assertEqual(len(border), 1)
                        self.assertTrue(all(abs(v.co.y - (0 if sign < 0 else 1)) < 1e-5
                                            for v in border[0].verts), 'Excluded edge must stay on the end plane')
                if top or bottom:
                    for edge in bm.edges:
                        expected_sharp = (excluded_z is not None
                                          and all(abs(v.co.z - excluded_z) < 1e-5 for v in edge.verts))
                        self.assertEqual(not edge.smooth, expected_sharp,
                                         'Rounded end transitions must not acquire stray sharp seams')
                if excluded_z is not None:
                    horizontal = next(face for face in bm.faces
                                      if face.normal.z * excluded_z > .01999)
                    self.assertTrue(all(not edge.smooth for edge in horizontal.edges),
                                    'Unrounded top/bottom border stays sharp through the end bevel')

    def test_angled_board_ends_keep_only_the_excluded_surface_sharp(self):
        for turn, top in itertools.product((-1, 1), (False, True)):
            points = [Vector(p) for p in ((0, 0, 0), (0, -1, .5), (0, -2, .5), (turn, -2, .5))]
            rings = _mitered_bar_rings(points, .065, .04)
            for index, board in enumerate(_board_rings(points, rings, .065, .04, 10, .003)):
                with self.subTest(turn=turn, top=top, board=index):
                    bm = self.inspect(self.timber(points=points[index:index + 2], rings=board,
                                                 bevel_top=top, bevel_bottom=not top, bevel_ends=True,
                                                 top_width=.0196, bottom_width=.0196, ends_width=.0196))
                    self.assert_closed(bm)
                    corner = 0 if top else 3
                    origin = board[0][corner]
                    normal = (board[0][1] - board[0][0]).cross(board[1][corner] - origin).normalized()
                    sharp = [edge for edge in bm.edges if not edge.smooth]
                    self.assertTrue(sharp)
                    self.assertTrue(all(abs((vertex.co - origin).dot(normal)) < 1e-5
                                        for edge in sharp for vertex in edge.verts),
                                    'Sharp seams must stay on the excluded top/bottom surface')

    def test_unbeveled_timber_uses_smooth_faces_and_sharp_corners(self):
        bm = self.inspect(self.timber())
        self.assert_closed(bm)
        self.assertTrue(all(face.smooth for face in bm.faces))
        self.assertTrue(all(not edge.smooth for edge in bm.edges))
        bm_flat = self.inspect(self.timber(smooth=False, bevel_top=True))
        self.assertTrue(all(not face.smooth for face in bm_flat.faces))

    def test_plate_toggle_matrix_offsets_and_bevel_clamping(self):
        root = self.root(step_count=3, tread_finish='PLATES', flight_count=2)
        for front, sides, corners, offset, amount in itertools.product(
            (False, True), (False, True), (False, True), (-.04, .04), (.003, .1),
        ):
            with self.subTest(front=front, sides=sides, corners=corners, offset=offset, amount=amount):
                self.configure(root, plate_bevel_front=front, plate_bevel_sides=sides,
                               plate_bevel_corners=corners, riser_offset=offset, plate_bevel_width=amount)
                mesh = next(child.data for child in root.children if child.get('modular_stair_part') == 'tread_plates')
                self.assert_closed(self.inspect(mesh))
                self.assertTrue(all(face.use_smooth for face in mesh.polygons))

    def test_timber_assembly_keeps_shading_across_merge_and_two_materials(self):
        root = self.root(flight_count=3, rail_enabled=True, rail_type='TYPE_3',
                         rail_cap_bevel_top=True, rail_cap_bevel_ends=True)
        for split, include, mount in itertools.product((False, True), (False, True), ('FLIGHT', 'WALL')):
            self.configure(root, rail_cap_split=split, rail_inner_include_landings=include,
                           rail_outer_mount=mount)
            for child in root.children:
                if child.get('modular_stair_part') not in ('balustrade', 'wall_balustrade'):
                    continue
                mesh = child.data
                self.assertEqual(len(mesh.materials), 2)
                wood = [face for face in mesh.polygons if face.material_index == 1]
                self.assertTrue(wood)
                self.assertTrue(all(face.use_smooth for face in wood))
                bm = self.inspect(mesh)
                edges = [edge for edge in bm.edges if all(face.material_index == 1 for face in edge.link_faces)]
                self.assertTrue(any(edge.smooth and edge.calc_face_angle(0.0) > .01 for edge in edges))
                self.assertTrue(any(not edge.smooth for edge in edges))

    def test_schema8_adds_optional_front_corner_setting(self):
        root = self.root(tread_finish='PLATES')
        settings = root.modular_stairs
        settings.auto_update = False
        settings.schema_version = 8
        settings.property_unset('plate_bevel_corners')
        settings.auto_update = True
        self.assertFalse(settings.last_error)
        self.assertEqual(settings.schema_version, 13)
        self.assertFalse(settings.plate_bevel_corners)
        self.assertTrue(all(settings.is_property_set(name) for name in INPUT_FIELDS))


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(FinishShadingTest))
        if not result.wasSuccessful():
            raise RuntimeError('Finish shading tests failed')
    finally:
        EasyGridAligner.unregister()
