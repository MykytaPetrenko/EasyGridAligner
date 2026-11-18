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
    volume += count * w * r * p['riser_offset'] / 2
    flights = p.get('flight_count', 1)
    if flights > 1:
        uncut = expected_volume(p | dict(flight_count=1, start_cut_type='NONE'))
        volume += (flights - 1) * uncut
        gap, side, end = p['flight_gap'], p['landing_side_overhang'], p['landing_end_overhang']
        if p['turn_angle'] == '180':
            area = (2 * w + gap + 2 * side) * (p['landing_depth'] + end)
        else:
            area = (w + gap + side) * (max(p['landing_depth'], w + gap) + end)
        volume += (flights - 1) * area * slab
    return volume


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
            self.assertAlmostEqual(bm.calc_volume(signed=True), volume, delta=tolerance * p.get('flight_count', 1))
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

    def test_multiflight_landings(self):
        for flights, angle, direction, ribs, top, beveled in itertools.product(
            (2, 3, 4), ('90', '180'), ('RIGHT', 'LEFT'), (False, True), (False, True), (False, True),
        ):
            with self.subTest(flights=flights, angle=angle, direction=direction,
                              ribs=ribs, top=top, bevels=beveled):
                self.assert_shell(flight_count=flights, turn_angle=angle, turn_direction=direction,
                                  landing_depth=1.2, flight_gap=.2, landing_side_overhang=.15,
                                  landing_end_overhang=.25, use_side_ribs=ribs, cut_top=top,
                                  riser_offset=.04, use_top_bevel=beveled, use_bottom_bevel=beveled)

    def test_multiflight_cuts_gaps_and_overhangs(self):
        for angle, gap, overhangs, cut, offset, top in itertools.product(
            ('90', '180'), (.001, .3), ((0.0, 0.0), (.2, .4)),
            ('NONE', 'FLOOR', 'BOX'), (-.04, .04), (False, True),
        ):
            with self.subTest(angle=angle, gap=gap, overhangs=overhangs, cut=cut, offset=offset, top=top):
                self.assert_shell(flight_count=3, turn_angle=angle, turn_direction='RIGHT',
                                  landing_depth=3.0, flight_gap=gap,
                                  landing_side_overhang=overhangs[0], landing_end_overhang=overhangs[1],
                                  start_cut_type=cut, riser_offset=offset, cut_top=top,
                                  use_side_ribs=True, use_top_bevel=True, use_bottom_bevel=True)

    def test_flight_positions_and_landing_dimensions(self):
        frames, landings = STAIRS._flight_layout(3, 4, 2, .2, .3, '180', 'RIGHT', 1.2, .2, .1, .3)
        self.assertEqual(tuple(round(value, 5) for value in frames[1].translation), (2.2, -1.2, .8))
        self.assertEqual(tuple(round(value, 5) for value in frames[2].translation), (0.0, 0.0, 1.6))
        self.assertEqual(tuple(round(value, 5) for value in landings[0]['bounds']), (-1.1, 3.3, -2.7, -1.2))
        frames, landings = STAIRS._flight_layout(2, 4, 2, .2, .3, '90', 'RIGHT', 1.2, .2, .1, .3)
        self.assertEqual(tuple(round(value, 5) for value in frames[1].translation), (1.2, -2.4, .8))
        self.assertEqual(tuple(round(value, 5) for value in landings[0]['bounds']), (-1.1, 1.2, -3.7, -1.2))

    def test_landing_shading_controls(self):
        mesh = self.mesh(flight_count=3, turn_angle='90', flight_gap=.2, landing_depth=1.2,
                         landing_side_overhang=.1, landing_end_overhang=.1,
                         use_top_bevel=True, use_bottom_bevel=True,
                         sharp_side=False, sharp_reinforcement=False, sharp_top_end=False,
                         sharp_start=False, sharp_unbeveled=False, sharp_landings=False)
        try:
            self.assertTrue(all(face.use_smooth for face in mesh.polygons))
            self.assertFalse(any(edge.use_edge_sharp for edge in mesh.edges))
            self.assertEqual({item.value for item in mesh.attributes['stair_flight'].data}, {-1, 0, 1, 2})
            self.assertAlmostEqual(max(vertex.co.z for vertex in mesh.vertices), 2.4, places=5)
        finally:
            bpy.data.meshes.remove(mesh)

    def test_landing_bevel_variants(self):
        for angle, flags, width, ribs in itertools.product(
            ('90', '180'), ((True, False), (False, True), (True, True)), (.025, .5), (False, True),
        ):
            with self.subTest(angle=angle, flags=flags, width=width, ribs=ribs):
                self.assert_shell(flight_count=3, turn_angle=angle, turn_direction='LEFT',
                                  landing_depth=1.4, flight_gap=.15, landing_side_overhang=0.0,
                                  landing_end_overhang=0.0, use_side_ribs=ribs, riser_offset=-.04,
                                  use_top_bevel=flags[0], use_bottom_bevel=flags[1],
                                  top_bevel_width=width, bottom_bevel_width=width,
                                  top_bevel_segments=1, bottom_bevel_segments=4,
                                  top_bevel_profile=.25, bottom_bevel_profile=.75)

    def test_invalid_layout_creates_no_mesh(self):
        count = len(bpy.data.meshes)
        for options in (dict(flight_count=0), dict(turn_angle='45'),
                        dict(flight_count=2, flight_gap=0.0), dict(landing_depth=0.0),
                        dict(landing_side_overhang=-.1), dict(landing_end_overhang=-.1)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.mesh(**options)
        self.assertEqual(len(bpy.data.meshes), count)

    def test_first_step_has_no_lower_bevel(self):
        for angle, direction, ribs, top, offset in itertools.product(
            ('90', '180'), ('LEFT', 'RIGHT'), (False, True), (False, True), (-.04, 0.0, .04),
        ):
            with self.subTest(angle=angle, direction=direction, ribs=ribs, top=top, offset=offset):
                mesh = self.mesh(flight_count=3, turn_angle=angle, turn_direction=direction,
                                 flight_gap=.2, landing_depth=1.2, use_side_ribs=ribs, cut_top=top,
                                 riser_offset=offset, use_top_bevel=True, use_bottom_bevel=True,
                                 sharp_start=False, sharp_unbeveled=True)
                try:
                    frames, _ = STAIRS._flight_layout(3, 4, 2, .2, .3, angle, direction, 1.2, .2, 0, 0)
                    for index, frame in enumerate(frames):
                        inverse = frame.inverted()
                        coordinates = [inverse @ vertex.co for vertex in mesh.vertices]
                        roots = [edge for edge in mesh.edges
                                 if all(abs(coordinates[vertex].y) < 1e-5
                                        and abs(coordinates[vertex].z) < 1e-5
                                        and abs(coordinates[vertex].x) <= 1.00001
                                        for vertex in edge.vertices)]
                        self.assertTrue(roots, f'Missing original first-step join on flight {index}')
                        self.assertAlmostEqual(sum((coordinates[edge.vertices[1]] - coordinates[edge.vertices[0]]).length
                                                   for edge in roots), 2.0, places=5)
                        if index > 0:
                            self.assertTrue(all(edge.use_edge_sharp for edge in roots))
                        # The next tread/riser junction must still be rounded.
                        self.assertFalse(any(all(abs(coordinates[vertex].y + .3) < 1e-5
                                                 and abs(coordinates[vertex].z - .2) < 1e-5
                                                 for vertex in edge.vertices) for edge in mesh.edges))
                    bm = bmesh.new()
                    try:
                        bm.from_mesh(mesh)
                        self.assertTrue(all(len(edge.link_faces) == 2 for edge in bm.edges))
                    finally:
                        bm.free()
                finally:
                    bpy.data.meshes.remove(mesh)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(StairTopologyTest))
    if not result.wasSuccessful():
        raise RuntimeError('Stair geometry/shading regression tests failed')
