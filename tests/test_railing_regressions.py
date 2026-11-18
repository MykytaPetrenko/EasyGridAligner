"""Reproduce the supplied test_case.blend: redundant corner posts and lower-rail overhangs."""
import itertools
from pathlib import Path
import sys
import unittest

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import EasyGridAligner
from EasyGridAligner.tests.test_stairs_type4 import Type4Test
from EasyGridAligner.tests.test_stairs_type2 import components


CASE = dict(step_count=9, flight_count=2, width=2, riser=.2, tread=.3,
            turn_angle='180', turn_direction='RIGHT', landing_depth=2.73, flight_gap=1.29,
            rail_post_every_steps=2, rail_post_step_mode='BALANCED', rail_landing_post_auto=True,
            rail_inset=.08, rail_bend_radius=.09)


def support_centers(root):
    settings = root.modular_stairs
    parts = {child['modular_stair_part']: child for child in root.children}
    if settings.rail_type in ('TYPE_3', 'TYPE_4'):
        mesh = parts['balustrade'].data
        groups = [group for group in components(mesh) if len(group) == 16]
        sides = 4
    else:
        mesh = parts['posts'].data
        groups = components(mesh)
        sides = (settings.rail_segments if settings.rail_post_match_handrail else settings.rail_post_segments
                 ) if settings.rail_type == 'TYPE_1' else 4
    return [sum((mesh.vertices[i].co for i in group[:sides]), Vector()) / sides for group in groups]


def lower_vertices(root):
    settings = root.modular_stairs
    parts = {child['modular_stair_part']: child for child in root.children}
    if settings.rail_type in ('TYPE_1', 'TYPE_2'):
        return [v.co.copy() for role in ('lower_rails', 'infill_corners') if role in parts
                for v in parts[role].data.vertices]
    mesh = parts['balustrade'].data
    slope = settings.riser / settings.tread
    scale = (1 + slope ** 2) ** .5
    # On the single straight flight used by the bound test, lower-rail vertices
    # have a low height above its slope and its component has exactly eight vertices.
    return [mesh.vertices[i].co.copy() for group in components(mesh) if len(group) == 8
            and all((mesh.vertices[i].co.z + mesh.vertices[i].co.y * slope) / scale < .5 for i in group)
            and (mesh.vertices[group[0]].co.xy - mesh.vertices[group[4]].co.xy).length > .1
            for i in group]


class RailingRegressionTest(unittest.TestCase):
    configure = Type4Test.configure
    parts = Type4Test.parts
    assert_closed = Type4Test.assert_closed

    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def create(self, **options):
        bpy.ops.mesh.modular_assets_add_stairs()
        root = bpy.context.object
        self.configure(root, rail_enabled=True, **options)
        return root

    def test_supplied_case_has_no_close_redundant_corner_or_landing_posts(self):
        root = self.create(rail_type='TYPE_1', **CASE)
        for style, direction, radius in itertools.product(
            ('TYPE_1', 'TYPE_2', 'TYPE_3', 'TYPE_4'), ('LEFT', 'RIGHT'), (.06, .09, .15),
        ):
            with self.subTest(style=style, direction=direction, radius=radius):
                self.configure(root, rail_type=style, turn_direction=direction, rail_bend_radius=radius)
                centers = support_centers(root)
                for i, first in enumerate(centers):
                    for second in centers[i + 1:]:
                        if abs(first.z - second.z) < 1e-5:
                            self.assertGreater((first - second).xy.length, .15,
                                               'A landing/elbow point must share the neighboring transition support')
                for obj in root.children:
                    self.assert_closed(obj.data)

    def test_lower_members_terminate_at_post_planes_for_all_types(self):
        root = self.create(rail_type='TYPE_1')
        for style, steps, setback in itertools.product(
            ('TYPE_1', 'TYPE_2', 'TYPE_3', 'TYPE_4'), (1, 2, 9), (0, .05),
        ):
            with self.subTest(style=style, steps=steps, setback=setback):
                self.configure(root, rail_type=style, step_count=steps,
                               rail_infill_start_setback=setback, rail_infill_end_setback=setback)
                centers = support_centers(root)
                vertices = lower_vertices(root)
                if steps == 1:
                    self.assertFalse(vertices, 'One terminal post leaves no lower bay')
                    continue
                self.assertTrue(vertices)
                low, high = min(p.y for p in centers), max(p.y for p in centers)
                self.assertAlmostEqual(min(p.y for p in vertices), low, places=5)
                self.assertAlmostEqual(max(p.y for p in vertices), high, places=5)
                for obj in root.children:
                    self.assert_closed(obj.data)


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(RailingRegressionTest))
        if not result.wasSuccessful():
            raise RuntimeError('Supplied railing regression tests failed')
    finally:
        EasyGridAligner.unregister()
