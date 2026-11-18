"""Mandatory supports, both tread modes, uniform landings and fixed-pitch bays."""
import itertools
import os
from pathlib import Path
import sys
import unittest

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import EasyGridAligner
from EasyGridAligner.geometry.railing_layout import flight_post_steps, plan_railing_posts, fixed_bay_infill
from EasyGridAligner.geometry.railing_parts import _railing_route, _landing_route, _closest_on_path, _trim_path
from EasyGridAligner.geometry.stairs import _flight_layout
from EasyGridAligner.services.stairs import STAIR_FIELDS
from EasyGridAligner.tests.test_stairs_type4 import Type4Test
from EasyGridAligner.tests.test_stairs_type2 import components


class RailingLayoutTest(unittest.TestCase):
    configure = Type4Test.configure
    parts = Type4Test.parts
    assert_closed = Type4Test.assert_closed
    vertical_groups = Type4Test.vertical_groups

    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def create(self, **options):
        bpy.ops.mesh.modular_assets_add_stairs()
        root = bpy.context.object
        self.configure(root, rail_enabled=True, **options)
        return root

    def layout(self, root, side):
        s = root.modular_stairs
        stairs = {name: getattr(s, name) for name in STAIR_FIELDS}
        frames, landings = _flight_layout(stairs['flight_count'], stairs['step_count'], stairs['width'],
            stairs['riser'], stairs['tread'], stairs['turn_angle'], stairs['turn_direction'],
            stairs['landing_depth'], stairs['flight_gap'], stairs['landing_side_overhang'], stairs['landing_end_overhang'])
        route, _ = _railing_route(stairs, frames, landings, side, s.rail_inset, s.rail_corner_length, s.rail_post_spacing)
        posts = plan_railing_posts(stairs, frames, landings, route, side, s.rail_inset, s.rail_corner_length,
            s.rail_post_every_steps, s.rail_post_step_mode, s.rail_landing_post_auto,
            s.rail_landing_post_spacing, s.rail_post_size)
        return stairs, frames, landings, route, posts

    def assert_has_point(self, point, points):
        self.assertTrue(any((point - other).length < 1e-5 for other in points), str(tuple(point)))

    def test_both_flight_distribution_modes_keep_terminal_treads(self):
        self.assertEqual(flight_post_steps(8, 3, 'BALANCED'), [0, 2, 5, 7])
        self.assertEqual(flight_post_steps(8, 3, 'EVERY_N'), [0, 3, 6, 7])
        for steps, stride, mode in itertools.product(range(1, 35), range(1, 10), ('BALANCED', 'EVERY_N')):
            indices = flight_post_steps(steps, stride, mode)
            self.assertEqual(indices[0], 0)
            self.assertEqual(indices[-1], steps - 1)
            self.assertEqual(indices, sorted(set(indices)))
            gaps = [b - a for a, b in zip(indices, indices[1:])]
            if gaps and mode == 'BALANCED':
                self.assertLessEqual(max(gaps) - min(gaps), 1)
            if mode == 'EVERY_N':
                self.assertTrue(all(gap == stride for gap in gaps[:-1]))

    def test_mandatory_treads_landing_ends_and_outer_corners(self):
        root = self.create(rail_type='TYPE_4', flight_count=3,
                           landing_side_overhang=.25, landing_end_overhang=.3)
        for angle, direction, gap, side in itertools.product(('90', '180'), ('LEFT', 'RIGHT'), (.001, .2), (-1, 1)):
            self.configure(root, turn_angle=angle, turn_direction=direction, flight_gap=gap)
            s, frames, landings, route, posts = self.layout(root, side)
            mandatory = [p.base for p in posts if p.mandatory]
            bases = [p.base for p in posts]
            x = side * (s['width'] / 2 - root.modular_stairs.rail_inset)
            for index, frame in enumerate(frames):
                for step in (0, s['step_count'] - 1):
                    self.assert_has_point(frame @ Vector((x, -(step + .5) * s['tread'], (step + 1) * s['riser'])), bases)
                if index:
                    before = _trim_path(_landing_route(s, landings[index - 1], side, root.modular_stairs.rail_inset, root.modular_stairs.rail_corner_length), 0, s['tread'] / 2)[-1]
                    self.assert_has_point(before, bases)
                    local = frame.inverted() @ before
                    self.assertGreaterEqual(local.y, root.modular_stairs.rail_post_size * .9 + .005)
            for landing in landings:
                points = _trim_path(_landing_route(s, landing, side, root.modular_stairs.rail_inset, root.modular_stairs.rail_corner_length), 0, s['tread'] / 2)
                self.assertTrue(any((points[0] - base).length <= s['tread'] / 2 + 1e-5 for base in mandatory))
                self.assert_has_point(points[-1], mandatory)
                inner = 1 if direction == 'RIGHT' else -1
                if side != inner or gap == .2:
                    for point in points:
                        self.assertTrue(any((point - base).length <= s['tread'] / 2 + 1e-5 for base in mandatory))
            self.assertEqual(len(posts), len({tuple(round(v, 5) for v in p.target) for p in posts}))

    def test_optional_gap_corners_are_omitted_only_in_tight_inner_gap(self):
        root = self.create(rail_type='TYPE_4', flight_count=2)
        for direction, gap in itertools.product(('LEFT', 'RIGHT'), (.001, .4)):
            self.configure(root, turn_direction=direction, flight_gap=gap)
            side = 1 if direction == 'RIGHT' else -1
            s, frames, landings, route, posts = self.layout(root, side)
            points = _trim_path(_landing_route(s, landings[0], side, root.modular_stairs.rail_inset, root.modular_stairs.rail_corner_length), 0, s['tread'] / 2)
            for point in points[1:-1]:
                present = any((p.target - point).length < 1e-5 for p in posts)
                self.assertEqual(present, gap == .4)
            for point in (points[0], points[-1]):
                self.assertTrue(any((point - p.base).length <= s['tread'] / 2 + 1e-5 for p in posts))

    def test_landing_straights_are_uniform_with_auto_and_manual_targets(self):
        root = self.create(rail_type='TYPE_4', flight_count=2, landing_depth=2.2,
                           landing_side_overhang=.25, landing_end_overhang=.3)
        for auto, stride in itertools.product((False, True), (1, 3)):
            self.configure(root, rail_landing_post_auto=auto, rail_landing_post_spacing=.37,
                           rail_post_every_steps=stride)
            s, frames, landings, route, posts = self.layout(root, -1)
            points = _trim_path(_landing_route(s, landings[0], -1, root.modular_stairs.rail_inset, root.modular_stairs.rail_corner_length), 0, s['tread'] / 2)
            target = s['tread'] * stride if auto else .37
            for start, end in zip(points, points[1:]):
                length = (end - start).length
                offsets = sorted((p.target - start).length for p in posts
                    if (p.base - p.target).length < 1e-5
                    and (_closest_on_path(p.target, (start, end)) - p.target).length < 1e-5)
                gaps = [b - a for a, b in zip(offsets, offsets[1:])]
                if not gaps:
                    self.assertLessEqual(length, s['tread'] + 1e-5, 'Short transitions may share nearby supports')
                    continue
                self.assertLess(max(gaps) - min(gaps), 1e-5)
                if length > target:
                    self.assertLessEqual(abs(gaps[0] - target), target / 2 + 1e-5)

    def test_fixed_infill_pitch_and_centered_residual_gaps(self):
        path = [Vector((0, 0, 0)), Vector((0, 1.03, .5))]
        posts = [path[0], path[0].lerp(path[1], .47 / 1.03), path[1]]
        for spacing in (.08, .117, .16):
            samples = fixed_bay_infill(path, posts, spacing, .04, .025)
            for first, last in zip(posts, posts[1:]):
                ys = sorted(point.y for point, _ in samples if first.y < point.y < last.y)
                self.assertTrue(ys)
                for a, b in zip(ys, ys[1:]):
                    self.assertAlmostEqual(b - a, spacing, places=6)
                self.assertAlmostEqual(ys[0] - first.y, last.y - ys[-1], places=6)
                self.assertGreaterEqual(ys[0] - first.y, (.04 + .025) / 2 + .005 - 1e-6)

    def test_generated_assemblies_have_landing_transition_posts_even_with_no_landing_rails(self):
        root = self.create(rail_type='TYPE_4', flight_count=3)
        for style, include, angle in itertools.product(('TYPE_3', 'TYPE_4'), (False, True), ('90', '180')):
            self.configure(root, rail_type=style, rail_inner_include_landings=include,
                           rail_outer_include_landings=include, turn_angle=angle)
            mesh = self.parts(root)['balustrade'].data
            posts = self.vertical_groups(mesh, 16)
            actual = [sum((mesh.vertices[i].co for i in group[:4]), Vector()) / 4 for group in posts]
            s, frames, landings, route, planned = self.layout(root, 1)
            for side in (-1, 1):
                x = side * (s['width'] / 2 - root.modular_stairs.rail_inset)
                for index, frame in enumerate(frames[1:], 1):
                    before = (_trim_path(_landing_route(s, landings[index - 1], side, root.modular_stairs.rail_inset, root.modular_stairs.rail_corner_length), 0, s['tread'] / 2)[-1]
                              if include else frame @ Vector((x, s['tread'] / 2, 0)))
                    self.assert_has_point(before, actual)
            self.assert_closed(mesh)

    def test_open_upper_flight_handrail_covers_mandatory_landing_post(self):
        root = self.create(rail_type='TYPE_4', flight_count=2, rail_inner_mount='NONE',
                           rail_outer_include_landings=False)
        mesh = self.parts(root)['balustrade'].data
        rails = Type4Test.handrails(self, mesh)
        upper = max(rails, key=lambda group: sum(mesh.vertices[i].co.z for i in group) / len(group))
        s, frames, landings, route, planned = self.layout(root, -1)
        inverse = frames[1].inverted()
        segments = root.modular_stairs.rail_type4_return_segments
        start = sum((inverse @ mesh.vertices[i].co for i in upper[segments * 4:(segments + 1) * 4]), Vector()) / 4
        self.assertGreater(start.y, root.modular_stairs.rail_post_size / 2)

    def test_generated_bay_infill_preserves_exact_pitch(self):
        root = self.create(rail_type='TYPE_4', rail_post_every_steps=3)
        for style, mode in itertools.product(('TYPE_3', 'TYPE_4'), ('BALANCED', 'EVERY_N')):
            self.configure(root, rail_type=style, rail_post_step_mode=mode, rail_baluster_spacing=.117)
            mesh = self.parts(root)['balustrade'].data
            post_groups = self.vertical_groups(mesh, 16)
            infill_groups = self.vertical_groups(mesh, 8)
            for side in (-1, 1):
                posts = sorted(sum(mesh.vertices[i].co.y for i in group[-4:]) / 4
                               for group in post_groups if mesh.vertices[group[0]].co.x * side > 0)
                bars = sorted(sum(mesh.vertices[i].co.y for i in group[-4:]) / 4
                              for group in infill_groups if mesh.vertices[group[0]].co.x * side > 0)
                for first, last in zip(posts, posts[1:]):
                    ys = [y for y in bars if first < y < last]
                    for a, b in zip(ys, ys[1:]):
                        self.assertAlmostEqual(b - a, .117, places=5)
                    if ys:
                        self.assertAlmostEqual(ys[0] - first, last - ys[-1], places=5)

    def test_all_styles_use_the_same_mandatory_treads_and_landing_clearance(self):
        root = self.create(rail_type='TYPE_1', flight_count=3, rail_post_every_steps=3)
        for style, mode, include, angle, direction in itertools.product(
            ('TYPE_1', 'TYPE_2', 'TYPE_3', 'TYPE_4'), ('BALANCED', 'EVERY_N'),
            (False, True), ('90', '180'), ('LEFT', 'RIGHT'),
        ):
            with self.subTest(style=style, mode=mode, include=include, angle=angle, direction=direction):
                self.configure(root, rail_type=style, rail_post_step_mode=mode,
                               rail_inner_include_landings=include, rail_outer_include_landings=include,
                               turn_angle=angle, turn_direction=direction)
                settings = root.modular_stairs
                parts = self.parts(root)
                if style in ('TYPE_3', 'TYPE_4'):
                    mesh = parts['balustrade'].data
                    groups = self.vertical_groups(mesh, 16)
                    sides = 4
                else:
                    mesh = parts['posts'].data
                    groups = components(mesh)
                    sides = (settings.rail_segments if settings.rail_post_match_handrail
                             else settings.rail_post_segments) if style == 'TYPE_1' else 4
                actual = [sum((mesh.vertices[i].co for i in group[:sides]), Vector()) / sides for group in groups]
                stairs, frames, landings, _, _ = self.layout(root, 1)
                indices = (0, 2, 5, 7) if mode == 'BALANCED' else (0, 3, 6, 7)
                for side in (-1, 1):
                    x = side * (stairs['width'] / 2 - settings.rail_inset)
                    for index, frame in enumerate(frames):
                        for step in indices:
                            self.assert_has_point(frame @ Vector((x, -(step + .5) * stairs['tread'],
                                                                   (step + 1) * stairs['riser'])), actual)
                        if index:
                            corner = settings.rail_bend_radius if style == 'TYPE_1' else settings.rail_corner_length
                            before = (_trim_path(_landing_route(stairs, landings[index - 1], side, settings.rail_inset, corner), 0, stairs['tread'] / 2)[-1]
                                      if include else frame @ Vector((x, stairs['tread'] / 2, 0)))
                            self.assert_has_point(before, actual)
                            local = frame.inverted() @ before
                            footprint = settings.rail_post_radius * 1.8 if style == 'TYPE_1' else settings.rail_post_size * .9
                            self.assertGreater(local.y, footprint + .005)
                            # The old mandatory support sat on this riser plane and intersected the tread.
                            old = frame @ Vector((x, 0, 0))
                            self.assertFalse(any((old - point).length < 1e-5 for point in actual))
                for obj in parts.values():
                    self.assert_closed(obj.data)

    def test_tubular_integral_stems_keep_landmark_feet_and_reach_curved_handrails(self):
        root = self.create(rail_type='TYPE_1', flight_count=3, turn_angle='90',
                           landing_side_overhang=.1, landing_end_overhang=.2)
        sides = root.modular_stairs.rail_segments
        mesh = self.parts(root)['posts'].data
        before = [sum((mesh.vertices[i].co for i in group[:sides]), Vector()) / sides
                  for group in components(mesh)]
        self.configure(root, rail_connector_mode='INTEGRATED')
        mesh = self.parts(root)['posts'].data
        leaned = False
        for group in components(mesh):
            base = sum((mesh.vertices[i].co for i in group[:sides]), Vector()) / sides
            self.assert_has_point(base, before)
            tip = sum((mesh.vertices[i].co for i in group[-sides:]), Vector()) / sides
            leaned = leaned or (tip.xy - base.xy).length > .001
        self.assertTrue(leaned, 'Rounded corners may require the stem to lean while the main post stays vertical')
        self.assert_closed(mesh)

    def test_default_infill_has_one_fewer_bar_and_dense_retains_original_pitch(self):
        for length in (.15, .47, .6, 1.01):
            path = [Vector((0, 0, 0)), Vector((0, length, .5))]
            normal = fixed_bay_infill(path, path, .12, .04, .025)
            dense = fixed_bay_infill(path, path, .12, .04, .025, dense=True)
            self.assertEqual(len(dense), len(normal) + 1)
            for samples in (normal, dense):
                ys = [point.y for point, _ in samples]
                for a, b in zip(ys, ys[1:]):
                    self.assertAlmostEqual(b - a, .12, places=6)
                if ys:
                    self.assertAlmostEqual(ys[0], length - ys[-1], places=6)
            if normal:
                self.assertGreater(normal[0][0].y, dense[0][0].y)
        root = self.create(rail_type='TYPE_4')
        self.assertFalse(root.modular_stairs.rail_baluster_dense)
        for style in ('TYPE_3', 'TYPE_4'):
            self.configure(root, rail_type=style, rail_baluster_dense=False)
            mesh = self.parts(root)['balustrade'].data
            count = len(self.vertical_groups(mesh, 8))
            bays = len(self.vertical_groups(mesh, 16)) - 2
            self.configure(root, rail_baluster_dense=True)
            mesh = self.parts(root)['balustrade'].data
            self.assertEqual(len(self.vertical_groups(mesh, 8)), count + bays)
            self.assert_closed(mesh)

    def test_legacy_metric_spacing_migrates_and_new_controls_save_copy(self):
        root = self.create(rail_type='TYPE_4')
        s = root.modular_stairs
        s.auto_update = False
        s.schema_version = 11
        s.rail_post_spacing = 1.1
        for name in ('rail_post_every_steps', 'rail_post_step_mode', 'rail_landing_post_auto', 'rail_landing_post_spacing'):
            s.property_unset(name)
        s.auto_update = True
        self.assertFalse(s.last_error)
        self.assertEqual(s.schema_version, 13)
        self.assertEqual(s.rail_post_every_steps, 3)
        self.assertTrue(s.rail_landing_post_auto)
        self.assertAlmostEqual(s.rail_landing_post_spacing, 1.1)
        self.configure(root, rail_post_step_mode='EVERY_N', rail_landing_post_auto=False,
                       rail_landing_post_spacing=.43, rail_baluster_dense=True)
        name = root.name
        path = Path(os.environ['STAIRS_TEST_OUTPUT']) / 'stairs_layout_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        root = bpy.data.objects[name]
        self.assertEqual(root.modular_stairs.rail_post_step_mode, 'EVERY_N')
        self.assertFalse(root.modular_stairs.rail_landing_post_auto)
        self.assertTrue(root.modular_stairs.rail_baluster_dense)
        self.assertAlmostEqual(root.modular_stairs.rail_landing_post_spacing, .43)
        bpy.context.view_layer.objects.active = root
        bpy.ops.mesh.modular_assets_add_stairs()
        copied = bpy.context.object.modular_stairs
        self.assertEqual(copied.rail_post_every_steps, 3)
        self.assertEqual(copied.rail_post_step_mode, 'EVERY_N')
        self.assertFalse(copied.rail_landing_post_auto)
        self.assertTrue(copied.rail_baluster_dense)
        self.assertAlmostEqual(copied.rail_landing_post_spacing, .43)


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(RailingLayoutTest))
        if not result.wasSuccessful():
            raise RuntimeError('Railing layout tests failed')
    finally:
        EasyGridAligner.unregister()
