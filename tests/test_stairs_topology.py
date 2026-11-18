"""Run in Blender: --background --factory-startup --python-exit-code 1 --python this_file."""
import importlib.util
import itertools
from pathlib import Path
import sys
import unittest

import bmesh
import bpy


SOURCE = (Path(sys.argv[sys.argv.index('--') + 1]) if '--' in sys.argv
          else Path(__file__).resolve().parents[1] / 'ops/stairs.py')
SPEC = importlib.util.spec_from_file_location('stairs_test', SOURCE)
STAIRS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAIRS)


def positive_integral(start, end, length):
    if start >= 0 and end >= 0:
        return length * (start + end) / 2
    if start <= 0 and end <= 0:
        return 0.0
    return length * max(start, end)**2 / (2 * abs(end - start))


def expected_volume(p):
    count, w, r, t, slab = (p[name] for name in ('step_count', 'width', 'riser', 'tread', 'slab_height'))
    rw = min(p['rib_width'], w / 2 - STAIRS.EPSILON) if p['use_side_ribs'] and p['rib_z_offset'] > STAIRS.EPSILON else 0
    rd = p['rib_z_offset']
    volume = 0.0
    for index in range(count):
        bottom = index * r - slab
        if p['start_cut_type'] == 'FLOOR':
            base = positive_integral(bottom, bottom + r, t)
            rib = positive_integral(bottom - rd, bottom + r - rd, t)
            volume += w * ((index + 1) * r * t - base) + 2 * rw * (base - rib)
        else:
            volume += w * (r * t / 2 + slab * t) + 2 * rw * rd * t
            if index == 0 and p['start_cut_type'] == 'BOX':
                cut = min(p['start_cut_width'], t)
                removed = positive_integral(-bottom, -bottom - r * cut / t, cut)
                removed_rib = positive_integral(rd - bottom, rd - bottom - r * cut / t, cut)
                volume -= w * removed + 2 * rw * (removed_rib - removed)
    return volume + count * w * r * p['riser_offset'] / 2


DEFAULTS = dict(step_count=4, width=2.0, riser=.2, tread=.3, slab_height=.2,
                use_side_ribs=False, rib_width=.15, rib_z_offset=.08, cut_top=False,
                start_cut_type='NONE', start_cut_width=.1, start_cut_edge_flow='THROUGH',
                riser_offset=0.0, use_top_bevel=False, top_bevel_width=.015,
                top_bevel_segments=3, top_bevel_profile=.5, use_bottom_bevel=False,
                bottom_bevel_width=.007, bottom_bevel_segments=2, bottom_bevel_profile=.5)


class StairTopologyTest(unittest.TestCase):
    def mesh(self, **options):
        return STAIRS.build_stair_mesh('Test', **(DEFAULTS | options))

    def assert_shell(self, **options):
        p = DEFAULTS | options
        mesh = self.mesh(**options)
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            self.assertTrue(all(len(edge.link_faces) == 2 for edge in bm.edges), 'Open shell or internal faces')
            self.assertTrue(all(edge.is_contiguous for edge in bm.edges), 'Inconsistent normals')
            self.assertTrue(all(vertex.link_faces for vertex in bm.verts), 'Loose vertices')
            self.assertTrue(all(face.calc_area() > 0 for face in bm.faces), 'Degenerate faces')
            pending, visited = {next(iter(bm.verts))}, set()
            while pending:
                vertex = pending.pop()
                visited.add(vertex)
                pending.update(edge.other_vert(vertex) for edge in vertex.link_edges if edge.other_vert(vertex) not in visited)
            self.assertEqual(len(visited), len(bm.verts))
            self.assertEqual(len(bm.verts) - len(bm.edges) + len(bm.faces), 2)
            volume = expected_volume(p)
            tolerance = max(1e-7, volume * 3e-6)
            if p['use_top_bevel']:
                tolerance += p['step_count'] * p['width'] * min(p['top_bevel_width'], p['riser'], p['tread'])**2 * 8
            if p['use_bottom_bevel']:
                tolerance += p['step_count'] * p['width'] * min(p['bottom_bevel_width'], p['riser'], p['tread'])**2 * 8
            self.assertAlmostEqual(bm.calc_volume(signed=True), volume, delta=tolerance)
            self.assertFalse(mesh.validate())
        finally:
            bm.free()
            bpy.data.meshes.remove(mesh)

    def test_geometry_modes(self):
        for count, slab, ribs, top, cut, offset, bevels in itertools.product(
            (1, 2, 8), (.06, .2, .45), (False, True), (False, True),
            ('NONE', 'FLOOR', 'BOX', 'BOX_FULL'), (-.06, 0.0, .04),
            ((False, False), (True, False), (False, True), (True, True)),
        ):
            with self.subTest(count=count, slab=slab, ribs=ribs, top=top, cut=cut, offset=offset, bevels=bevels):
                self.assert_shell(step_count=count, slab_height=slab, use_side_ribs=ribs,
                                  cut_top=top, start_cut_type='BOX' if cut == 'BOX_FULL' else cut,
                                  start_cut_width=.3 if cut == 'BOX_FULL' else .1,
                                  riser_offset=offset, use_top_bevel=bevels[0], use_bottom_bevel=bevels[1])

    def test_triangular_sides_and_mandatory_slab(self):
        mesh = self.mesh(slab_height=.12, riser_offset=.04)
        try:
            sides = [face for face in mesh.polygons if abs(face.normal.x) > .999]
            self.assertEqual(sum(len(face.vertices) == 3 for face in sides), 8)
            self.assertEqual(sum(len(face.vertices) == 4 for face in sides), 8)
            self.assertAlmostEqual(min(vertex.co.z for vertex in mesh.vertices), -.12)
        finally:
            bpy.data.meshes.remove(mesh)
        for height in (0.0, -.1):
            with self.assertRaisesRegex(ValueError, 'Slab Height'):
                self.mesh(slab_height=height)

    def test_box_cut_flows_and_widths(self):
        for flow, cut_width, count, slab, top in itertools.product(
            ('CORNER', 'THROUGH'), (0.0, .04, .1, .3, .6), (1, 8), (.06, .2, .45), (False, True),
        ):
            with self.subTest(flow=flow, cut_width=cut_width, count=count, slab=slab, top=top):
                self.assert_shell(step_count=count, slab_height=slab, use_side_ribs=True,
                                  cut_top=top, start_cut_type='BOX', start_cut_width=cut_width,
                                  start_cut_edge_flow=flow, riser_offset=.04,
                                  use_top_bevel=True, use_bottom_bevel=True)

    def test_zero_ribs_deep_cuts_and_clamping(self):
        for cut, flow, depth, bevel_width in itertools.product(
            ('NONE', 'FLOOR', 'BOX'), ('CORNER', 'THROUGH'), (0.0, .8), (.0, .5),
        ):
            with self.subTest(cut=cut, flow=flow, depth=depth, bevel_width=bevel_width):
                self.assert_shell(start_cut_type=cut, start_cut_edge_flow=flow,
                                  use_side_ribs=True, rib_z_offset=depth,
                                  use_top_bevel=True, use_bottom_bevel=True,
                                  top_bevel_width=bevel_width, bottom_bevel_width=bevel_width)

    def assert_edge_sharp(self, mesh, first, second, expected):
        key = {tuple(round(value, 5) for value in coord) for coord in (first, second)}
        for edge in mesh.edges:
            coordinates = {tuple(round(value, 5) for value in mesh.vertices[index].co)
                           for index in edge.vertices}
            if coordinates == key:
                self.assertEqual(edge.use_edge_sharp, expected, str(key))
                return
        self.fail(f'Expected edge does not exist: {key}')

    def test_smooth_and_sharp_controls(self):
        sharp_off = dict(sharp_side=False, sharp_reinforcement=False, sharp_top_end=False,
                         sharp_start=False, sharp_unbeveled=False)
        for smooth, mark in itertools.product((False, True), (False, True)):
            mesh = self.mesh(use_smooth_shading=smooth, use_top_bevel=True, use_bottom_bevel=True,
                             **({} if mark else sharp_off))
            try:
                self.assertTrue(all(face.use_smooth == smooth for face in mesh.polygons))
                self.assertEqual(any(edge.use_edge_sharp for edge in mesh.edges), mark)
            finally:
                bpy.data.meshes.remove(mesh)

    def test_sharp_front_depends_on_offset(self):
        for offset in (0.0, -.04, .04):
            mesh = self.mesh(riser_offset=offset, slab_height=.12,
                             use_top_bevel=True, top_bevel_width=.02, use_bottom_bevel=True)
            try:
                self.assert_edge_sharp(mesh, (-1, 0, 0), (1, 0, 0), offset != 0.0)
                self.assert_edge_sharp(mesh, (-1, -1.2, .8), (1, -1.2, .8), True)
                if offset == 0.0:
                    # The first nose's bevel/riser boundary must not be marked
                    # sharp just because it lies on the front Y=0 plane.
                    self.assert_edge_sharp(mesh, (-1, 0, .18), (1, 0, .18), False)
            finally:
                bpy.data.meshes.remove(mesh)

    def test_side_contour_and_internal_diagonal(self):
        mesh = self.mesh(slab_height=.12, riser_offset=.04)
        try:
            self.assert_edge_sharp(mesh, (1, 0, 0), (1, -.3, .2), False)
            self.assert_edge_sharp(mesh, (1, .04, .2), (1, -.3, .2), True)
            self.assert_edge_sharp(mesh, (1, 0, -.12), (1, -.3, .08), True)
        finally:
            bpy.data.meshes.remove(mesh)

    def test_reinforcement_longitudinal_sharps(self):
        for ribs in (False, True):
            mesh = self.mesh(use_side_ribs=ribs, sharp_side=False, sharp_start=False,
                             sharp_top_end=False, sharp_unbeveled=False)
            try:
                self.assertEqual(sum(edge.use_edge_sharp for edge in mesh.edges), 24 if ribs else 8)
                if ribs:
                    self.assert_edge_sharp(mesh, (.85, 0, -.2), (.85, -.3, 0), True)
                    self.assert_edge_sharp(mesh, (.85, 0, -.28), (.85, -.3, -.08), True)
            finally:
                bpy.data.meshes.remove(mesh)

    def test_independent_bevel_controls(self):
        cases = (
            {}, dict(use_top_bevel=True), dict(use_bottom_bevel=True),
            dict(use_top_bevel=True, use_bottom_bevel=True),
            dict(use_top_bevel=True, top_bevel_segments=6, use_bottom_bevel=True),
            dict(use_top_bevel=True, use_bottom_bevel=True, bottom_bevel_segments=6),
        )
        meshes = [self.mesh(**options) for options in cases]
        try:
            counts = [len(mesh.polygons) for mesh in meshes]
            self.assertGreater(counts[1], counts[0])
            self.assertGreater(counts[2], counts[0])
            self.assertGreater(counts[3], max(counts[1], counts[2]))
            self.assertGreater(counts[4], counts[3])
            self.assertGreater(counts[5], counts[3])
        finally:
            for mesh in meshes:
                bpy.data.meshes.remove(mesh)

    def test_mixed_bevel_profiles_and_segments(self):
        for segments, profiles, widths in itertools.product(
            ((1, 1), (1, 5), (5, 1)), ((.25, .75), (.75, .25)), ((.02, .005), (.5, .5)),
        ):
            with self.subTest(segments=segments, profiles=profiles, widths=widths):
                self.assert_shell(use_side_ribs=True, cut_top=True, riser_offset=.04,
                                  use_top_bevel=True, use_bottom_bevel=True,
                                  top_bevel_segments=segments[0], bottom_bevel_segments=segments[1],
                                  top_bevel_profile=profiles[0], bottom_bevel_profile=profiles[1],
                                  top_bevel_width=widths[0], bottom_bevel_width=widths[1])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(StairTopologyTest))
    if not result.wasSuccessful():
        raise RuntimeError('Stair geometry/shading regression tests failed')
