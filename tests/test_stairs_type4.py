"""All-metal balusters, continuous returned handrails and landing-break termination."""
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
from EasyGridAligner.geometry.railing_parts import _railing_route
from EasyGridAligner.geometry.railings_rectangular import _rect_axes
from EasyGridAligner.geometry.stairs import _flight_layout
from EasyGridAligner.services.stairs import INPUT_FIELDS, STAIR_FIELDS
from EasyGridAligner.tests.test_stairs_type2 import components
from EasyGridAligner.tests.test_stairs_type3 import Type3Test


class Type4Test(unittest.TestCase):
    configure = Type3Test.configure
    parts = Type3Test.parts
    assert_closed = Type3Test.assert_closed

    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def create(self, **options):
        bpy.ops.mesh.modular_assets_add_stairs()
        root = bpy.context.object
        self.configure(root, rail_enabled=True, rail_type='TYPE_4', **options)
        return root

    def vertical_groups(self, mesh, size):
        return [group for group in Type3Test.vertical_groups(self, mesh, size)
                if all((mesh.vertices[group[-8 + i]].co.xy - mesh.vertices[group[-4 + i]].co.xy).length < 1e-5
                       for i in range(4))]

    def handrails(self, mesh):
        curved = {index for face in mesh.polygons if face.use_smooth for index in face.vertices}
        return [group for group in components(mesh) if curved.intersection(group)]

    def test_metal_sections_and_flush_vertical_tops(self):
        root = self.create()
        settings = root.modular_stairs
        for slope, width, thickness in itertools.product((.12, .2), (.05, .06), (.008, .016)):
            self.configure(root, riser=slope, rail_type4_handrail_width=width,
                           rail_type4_handrail_thickness=thickness)
            mesh = self.parts(root)['balustrade'].data
            self.assertEqual(list(mesh.materials), [settings.rail_metal_material])
            self.assertEqual({face.material_index for face in mesh.polygons}, {0})
            self.assertLess(settings.rail_baluster_width, settings.rail_base_rail_width)
            self.assertLess(settings.rail_base_rail_width, settings.rail_post_size)
            self.assertLess(settings.rail_post_size, settings.rail_type4_handrail_width)
            for size in (8, 16):
                groups = self.vertical_groups(mesh, size)
                self.assertTrue(groups)
                for group in groups:
                    for index in group[-4:]:
                        point = mesh.vertices[index].co
                        scale = (1 + (settings.riser / settings.tread) ** 2) ** .5
                        depth = (point.z + point.y * settings.riser / settings.tread - settings.rail_height) / scale
                        self.assertAlmostEqual(depth, -thickness / 2, places=5)
            # Exactly one lower rail and one returned handrail per side, without a timber cap or upper backing rail.
            groups = components(mesh)
            self.assertEqual(len(groups) - len(self.vertical_groups(mesh, 8)) - len(self.vertical_groups(mesh, 16)), 4)
            self.assert_closed(mesh)

    def test_both_returns_are_closed_half_circles_tangent_to_handrail(self):
        root = self.create(rail_inner_mount='NONE', rail_start_extension=.07, rail_end_extension=.11)
        settings = root.modular_stairs
        stairs = {name: getattr(settings, name) for name in STAIR_FIELDS}
        frames, landings = _flight_layout(stairs['flight_count'], stairs['step_count'], stairs['width'],
                                         stairs['riser'], stairs['tread'], stairs['turn_angle'],
                                         stairs['turn_direction'], stairs['landing_depth'], stairs['flight_gap'],
                                         stairs['landing_side_overhang'], stairs['landing_end_overhang'])
        route, _ = _railing_route(stairs, frames, landings, -1, settings.rail_inset,
                                  settings.rail_corner_length, settings.rail_post_spacing)
        for riser, radius, segments in itertools.product((.12, .2, .6), (.025, .06), (3, 6, 16)):
            self.configure(root, riser=riser, rail_type4_return_radius=radius, rail_type4_return_segments=segments)
            mesh = self.parts(root)['balustrade'].data
            groups = self.handrails(mesh)
            self.assertEqual(len(groups), 1)
            coords = [mesh.vertices[i].co for i in groups[0]]
            centers = [sum(coords[i:i + 4], Vector()) / 4 for i in range(0, len(coords), 4)]
            self.assertEqual(len(centers), 2 + 2 * segments)
            path = [centers[segments], centers[-segments - 1]]
            self.assertAlmostEqual(max(p.y for p in coords), route[0].y, places=5)
            self.assertAlmostEqual(min(p.y for p in coords), route[-1].y, places=5)
            for end, arc in ((0, list(reversed(centers[:segments + 1]))),
                             (1, centers[-segments - 1:])):
                direction = (path[1] - path[0]).normalized()
                _, normal = _rect_axes(direction)
                endpoint = path[end]
                circle_center = endpoint - normal * radius
                self.assertLess((arc[0] - endpoint).length, 1e-5)
                self.assertLess((arc[-1] - endpoint + normal * (2 * radius)).length, 1e-5)
                for center in arc:
                    self.assertAlmostEqual((center - circle_center).length, radius, places=5)
                outward = direction if end else -direction
                self.assertGreater(max((center - endpoint).dot(outward) for center in arc), radius * .85)
            self.assert_closed(mesh)
            bm = bmesh.new()
            try:
                bm.from_mesh(mesh)
                bm.normal_update()
                curved = [edge for edge in bm.edges if edge.smooth and edge.calc_face_angle(0) > .01]
                self.assertTrue(curved, 'Return segments shade smoothly along the arc')
            finally:
                bm.free()

    def test_returns_at_each_landing_break_and_only_open_ends_on_continuous_routes(self):
        root = self.create(flight_count=3, landing_side_overhang=.25, landing_end_overhang=.3)
        for angle, direction, coverage, outer in itertools.product(
            ('90', '180'), ('LEFT', 'RIGHT'), itertools.product((False, True), repeat=2), ('FLIGHT', 'WALL'),
        ):
            with self.subTest(angle=angle, direction=direction, coverage=coverage, outer=outer):
                self.configure(root, turn_angle=angle, turn_direction=direction,
                               rail_inner_include_landings=coverage[0], rail_outer_include_landings=coverage[1],
                               rail_outer_mount=outer)
                count = 0
                for role, obj in self.parts(root).items():
                    self.assert_closed(obj.data)
                    self.assertEqual(len(obj.data.materials), 1)
                    if role in ('balustrade', 'wall_balustrade'):
                        count += len(self.handrails(obj.data))
                self.assertEqual(count, sum(1 if include else 3 for include in coverage),
                                 'Every separate flight section receives two returns')

    def test_timber_controls_and_backing_rail_do_not_affect_type4(self):
        root = self.create()
        before = self.parts(root)['balustrade'].data
        coords = [tuple(v.co) for v in before.vertices]
        self.configure(root, rail_cap_split=True, rail_cap_bevel_top=True, rail_cap_bevel_ends=True,
                       rail_cap_max_length=.1, rail_top_rail_height=.08,
                       rail_start_extension=.2, rail_end_extension=.3,
                       rail_infill_start_setback=.2, rail_infill_end_setback=.3)
        after = self.parts(root)['balustrade'].data
        self.assertEqual(coords, [tuple(v.co) for v in after.vertices])
        self.assertEqual(len(after.materials), 1)

    def test_lower_rail_and_infill_stop_at_terminal_posts(self):
        root = self.create()
        for steps, stride, riser in itertools.product((1, 2, 8), (2, 8), (.12, .2)):
            with self.subTest(steps=steps, every_steps=stride, riser=riser):
                self.configure(root, step_count=steps, rail_post_every_steps=stride, riser=riser)
                mesh = self.parts(root)['balustrade'].data
                posts = self.vertical_groups(mesh, 16)
                balusters = self.vertical_groups(mesh, 8)
                handrails = self.handrails(mesh)
                remaining = [group for group in components(mesh)
                             if group not in posts and group not in handrails]
                for side in (-1, 1):
                    terminal = sorted(sum(mesh.vertices[i].co.y for i in group[-4:]) / 4
                                      for group in posts if mesh.vertices[group[0]].co.x * side > 0)
                    self.assertTrue(terminal)
                    infill = [group for group in remaining if mesh.vertices[group[0]].co.x * side > 0]
                    if len(terminal) == 1:
                        self.assertFalse(infill, 'One post leaves no lower rail or infill bay')
                        continue
                    self.assertTrue(infill)
                    lower = [group for group in infill if group not in balusters]
                    self.assertEqual(len(lower), 1)
                    for group in infill:
                        coords = [mesh.vertices[i].co for i in group]
                        self.assertGreaterEqual(min(p.y for p in coords), terminal[0] - 1e-5)
                        self.assertLessEqual(max(p.y for p in coords), terminal[-1] + 1e-5)
                    lower_coords = [mesh.vertices[i].co for i in lower[0]]
                    self.assertAlmostEqual(min(p.y for p in lower_coords), terminal[0], places=5)
                    self.assertAlmostEqual(max(p.y for p in lower_coords), terminal[-1], places=5)
                self.assert_closed(mesh)

    def test_material_slot_edits_panel_edits_and_switching_types(self):
        root = self.create(rail_outer_mount='WALL')
        metal = bpy.data.materials.new('Type 4 Custom Metal')
        self.configure(root, rail_metal_material=metal)
        self.assertTrue(all(list(obj.data.materials) == [metal] for obj in root.children))
        for style in ('TYPE_3', 'TYPE_1', 'TYPE_2', 'TYPE_4'):
            self.configure(root, rail_type=style)
        self.assertTrue(all(list(obj.data.materials) == [metal] for obj in root.children))
        slot = bpy.data.materials.new('Type 4 Slot Edit')
        obj = self.parts(root)['wall_balustrade']
        obj.data.materials[0] = slot
        bpy.context.view_layer.objects.active = obj
        self.configure(root, rail_type4_return_radius=.05)
        self.assertEqual(root.modular_stairs.rail_metal_material, slot)
        self.assertTrue(all(list(obj.data.materials) == [slot] for obj in root.children))

    def test_wall_only_handrail_ignores_hidden_frame_dimensions(self):
        root = self.create(rail_inner_mount='NONE', rail_outer_mount='WALL',
                           rail_base_rail_width=.08, rail_post_size=.08,
                           rail_baluster_width=.04, rail_top_rail_height=.08)
        parts = self.parts(root)
        self.assertIn('wall_balustrade', parts)
        self.assertNotIn('balustrade', parts)
        self.assertEqual(len(self.handrails(parts['wall_balustrade'].data)), 1)
        for obj in parts.values():
            self.assert_closed(obj.data)
            self.assertEqual(len(obj.data.materials), 1)

    def test_invalid_sections_and_return_radius_preserve_geometry(self):
        root = self.create()
        for field, invalid, valid in (('rail_type4_handrail_width', .03, .05),
                                      ('rail_base_rail_width', .045, .03),
                                      ('rail_base_rail_width', .01, .03),
                                      ('rail_type4_return_radius', .005, .04)):
            before = {obj: obj.data for obj in (root, *root.children)}
            count = len(bpy.data.meshes)
            setattr(root.modular_stairs, field, invalid)
            self.assertTrue(root.modular_stairs.last_error)
            self.assertEqual(before, {obj: obj.data for obj in (root, *root.children)})
            self.assertEqual(len(bpy.data.meshes), count)
            setattr(root.modular_stairs, field, valid)
            self.assertFalse(root.modular_stairs.last_error)

    def test_migration_save_reopen_and_copy(self):
        root = self.create(flight_count=2, rail_inner_include_landings=False,
                           rail_type4_return_radius=.055, rail_type4_return_segments=18)
        settings = root.modular_stairs
        settings.auto_update = False
        settings.schema_version = 10
        settings.property_unset('rail_type4_handrail_width')
        settings.auto_update = True
        self.assertFalse(settings.last_error)
        self.assertEqual(settings.schema_version, 13)
        self.assertTrue(all(settings.is_property_set(name) for name in INPUT_FIELDS))
        name = root.name
        path = Path(os.environ['STAIRS_TEST_OUTPUT']) / 'stairs_type4_test.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        root = bpy.data.objects[name]
        self.assertEqual(root.modular_stairs.rail_type, 'TYPE_4')
        self.assertAlmostEqual(root.modular_stairs.rail_type4_return_radius, .055)
        self.assertEqual(root.modular_stairs.rail_type4_return_segments, 18)
        bpy.context.view_layer.objects.active = root
        bpy.ops.mesh.modular_assets_add_stairs()
        copied = bpy.context.object
        self.assertEqual(copied.modular_stairs.rail_type, 'TYPE_4')
        self.assertAlmostEqual(copied.modular_stairs.rail_type4_return_radius, .055)
        self.assertEqual(copied.modular_stairs.rail_type4_return_segments, 18)
        self.assertTrue(all(len(obj.data.materials) == 1 for obj in copied.children))


if __name__ == '__main__':
    EasyGridAligner.register()
    try:
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Type4Test))
        if not result.wasSuccessful():
            raise RuntimeError('Type 4 metal railing tests failed')
    finally:
        EasyGridAligner.unregister()
