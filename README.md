# Modular Stair Generator

Blender add-on for generating modular stair meshes, snapping mesh/UV data to a
grid, and generating UVs from 3D coordinates.

## Install

Use this folder as the add-on folder in Blender, then enable **Modular Stair Generator**.

The operator is available at:

`Shift+A > Mesh > Modular Stairs`

## Persistent stairs configurator

Open **3D View > Sidebar (N) > Modular > Stairs Configurator** and click **New Stairs**.
The Add menu above creates the same configured object. Creation no longer opens a large parameter popup.
New stairs appear at the 3D cursor; when configured stairs are selected, New Stairs copies their input settings into an independent instance.

Select the stair mesh or any generated railing part to edit the owning stairs. All stair, landing,
bevel, shading and railing inputs are stored in **Object > modular_stairs** and saved in the `.blend`.
Sections use collapsible controls: Steps & Slab, Flights & Landings, Reinforcement, Bevels,
Shading, Start Cut and Railing System. Each object keeps its own settings and section state.

**Auto Update** rebuilds geometry when a parameter changes. Disable it while changing many inputs,
then press **Update**, or enable Auto Update again. Rebuilds preserve the stair object's position,
rotation, scale and material slots, and preserve material assignments on each railing part.
Invalid settings display an error and retain the previous geometry. Switch to Object Mode before
updating; mesh edits are replaced by the next rebuild.

Generated railing parts are child meshes of the stairs, grouped as Handrail, Infill Rails, Posts,
Handrail Supports and Coupling Sleeves. Integral stems are part of Posts and have no separate support
object. Moving the stairs moves the assembly. User-added children are retained.
No timers, frame handlers or dependency-graph handlers are installed, and registering the addon or
loading a file does not rebuild saved objects.

Meshes made by the earlier creation-only operator did not store their parameters and remain ordinary
meshes. Create a new configured stairs object for this persistent workflow. Restart Blender after
updating the addon to load the new modules.

## Type 1 railings

In **Railing System**, enable **Enable Railing** and choose the left/right sides. The railing follows
flights and the inner/outer landing routes, including 90° and 180° turns in either direction.
On 90° turns with an enlarged Flight Gap, the inner route follows the exposed edges of the
landing projection at Edge Inset. The handrail, infill rails and landing posts share that route.
**Outer Railing** can disable the outer route on multi-flight stairs while keeping the inner route.
Its interpretation follows Turn Direction. On a straight single flight, use Left Side / Right Side.

Terminology: **handrail** is the upper graspable tube; **railing system** is the complete assembly.
The smaller tubes are **infill rails**, the uprights are **posts**, their thin top connections are
**handrail supports**, and the sleeves at elbows are **coupling sleeves**.

- **Railing Height / Edge Inset** control the centerline above the sloping stair reference and landings,
  and its distance inward from the stair edge.
- **Handrail Radius / Elbow Radius** control the thick main tube and rounded elbows. Short landing
  segments limit elbow size; configurations too tight for the tube report an error.
- **Coupling Length / Thickness** control hollow sleeves at both ends of each main-tube elbow.
- **Infill Rail Count** sets the number of thin continuous rails; default `4`, with `0` supported.
  Their radius and lower clearance are independent. They have rounded turns and no couplings.
- **Post Spacing** sets the target frequency. Flight posts snap to tread centers, with posts at the
  first and last steps; landing posts are distributed along the railing route.
- **Post Radius** controls the uprights. The base flange, shaft and upper collar are one closed,
  connected mesh per post, joined by annular shoulder faces; there are no overlapping cylinders or
  hidden shaft end caps in the flange/collar.
- **Support Construction** offers **Separate Support** or **Integral Stem**. Separate supports are
  child geometry as before. An integral stem joins the upper post collar through a flat horizontal
  annular shoulder and shares its mesh
  rings, with no cap between the collar and stem. **Support Stem Radius / Length** set its dimensions.
- Cylinder resolution is independent per component:

  | Component | Default sides | Inheritance |
  | --- | ---: | --- |
  | Handrail and coupling sleeves | 16 | Own setting |
  | Infill rails | 8 | Own setting |
  | Posts, including flange/collar | 16 | **Same as Handrail** enabled by default |
  | Separate handrail supports | 8 | **Same as Post** disabled by default |
  | Integral support stems | Post count | Always follows the effective post setting |

  Disabled resolution fields display the effective inherited count. **Elbow Segments** controls bend
  tessellation independently. Material assignment remains separate per generated part.

Existing configured objects keep their saved handrail side count. New resolution controls are
initialized on the next update without replacing saved input values. Restart Blender after the
addon change and press **Update** on existing stairs to rebuild the post topology.

The **Modular** tab in the 3D View sidebar contains the grid snapping and UV
tools. UV generation operates on selected faces in Edit Mode, including across
multiple edited mesh objects.

**Generate UVs from View** automatically selects the world axes closest to the
current 3D View's horizontal and vertical directions. It offsets each channel
to the configured **Offset Step**, so the minimum mapped value lies in the
`[0, step)` interval. Both automatic and custom-axis modes apply their
3D-coordinate offset before the shared scale.

## Development dependency

[BlenderUtils](https://github.com/MykytaPetrenko/BlenderUtils) is included as a
Git submodule for shared UI and operator-state helpers. Clone with:

`git clone --recurse-submodules <repository-url>`

## Geometry

- Object origin: `0, 0, 0`
- Stair direction: negative `Y`
- Width axis: `X`, centered around the origin
- Height axis: `Z`
- All generated modules form one connected, closed mesh shell. Shared step, slab and rib interfaces have no internal caps; only exposed end faces are generated.
- Every regular, unbeveled step has one triangular side face above a continuous sloping slab. The slab is mandatory; its side is a separate quad per module. Cuts and bevels subdivide only the affected portions.
- Multiple flights and their intermediate landings form the same connected shell. The generator omits the shared slab caps and matches connection vertices directly; there are no internal landing/flight walls. Landing slabs use the same Slab Height. Side ribs terminate below the flat landings with exposed end faces.

## Parameters

- **Flights**: number of ascending flights. One flight preserves the original straight stair; additional flights add one intermediate landing each.
- **Steps per Flight**: number of steps in every flight. Flight run is `Steps per Flight × Tread`; flight rise is `Steps per Flight × Riser`.
- **Turn Angle**: `180°` for parallel return flights, or `90°` for quarter-turn flights.
- **Turn Direction**: left or right while ascending. Applies to every intermediate landing.
- **Landing Depth**: intermediate platform depth. For 90° turns, the effective depth is at least `Width + Flight Gap`, so both flight openings fit; the panel indicates when this minimum is used.
- **Flight Gap**: clear spacing between neighboring flights, at least 1 mm. For 90° turns, the inner corner keeps this gap in both directions.
- **Side Overhang**: extension beyond the exposed lateral landing edges. For 180° turns both lateral edges extend; for 90° turns the exposed side opposite the outgoing flight extends.
- **End Overhang**: additional extension of the far landing edge beyond Landing Depth.
- **Width**: total width along `X`
- **Riser**: vertical rise per step
- **Tread**: run per step along negative `Y`
- **Riser Offset**: signed horizontal shift of each riser's upper edge. Positive values project the tread nose forward and create a recessed, sloping riser; negative values shift the nose backward. The riser foot, step spacing and underside remain fixed. The value must be greater than `-Tread`.
- **Slab Height**: total vertical thickness of the required sloping slab, measured below the triangular steps. Minimum 1 mm; default 0.2 m. Replaces the optional Lower Slab and Slab Z Offset controls.
- **Upper Bevel**: rounds the convex tread noses. Independent **Width**, **Segments** and **Profile** controls.
- **Lower Bevel**: rounds the concave tread/riser junctions, excluding the first step of every flight. The floor/landing-to-first-riser edge is always preserved without a lower bevel. Independent **Width**, **Segments** and **Profile** controls.
- Bevel widths are automatically clamped to avoid overlap; zero leaves that corner sharp. One segment gives a chamfer; additional segments give a roundover. Profile `0.5` gives a circular cross-section. Side outlines, slab, ribs and coplanar subdivisions are excluded from beveling.
- **Smooth Shading**: shades the generated faces smoothly. Enabled by default. The following independent **Mark Sharp** controls define the shading boundaries:
  - **Sides**: outer side contours, including the ends of both bevels. Coplanar internal side diagonals stay smooth.
  - **Underside / Reinforcement**: longitudinal rib corners; without ribs, the slab's lower longitudinal side corners.
  - **Upper End**: outer perimeter of the upper end face, including its slab/rib outline.
  - **Front / Cut Faces**: exposed front slab, rib and cut contours. The first riser/slab junction is sharp when Riser Offset is nonzero, and remains smooth when the faces are coplanar. Bevel strips themselves remain smooth.
  - **Unbeveled Corners**: tread/riser corners whose corresponding bevel is disabled or has zero width.
  - **Landing Borders**: exposed outer borders of intermediate landing slabs. Coplanar flight/landing top joins remain smooth. The first riser junction is never beveled and is covered by Front / Cut Faces and Unbeveled Corners.
- **Side Ribs**: adds reinforcement ribs below both side edges of regular stair modules
- **Rib Width**: width of each side rib, measured inward from the side
- **Rib Z Offset**: downward extrusion distance for side ribs
- **Cut Top**: when enabled, rib edge loops continue through the top stair polygons; when disabled, only the rib corner remains inset and the upper loop vertices collapse back to the sides
- **Cut Type**: start cut mode: **None**, **Floor Cut**, or **Box Cut**
- **Cut Width**: box cut distance from the origin along negative `Y`, capped at one tread. Removes slab/rib geometry below `Z=0` in this interval, retaining any portion above the floor.
- **Cut Edge Flow**: available for **Box Cut** only; **Corner** keeps the top surface continuous, while **Through** continues the cut through it.
- **Floor Cut**: clips the full generated mesh at `Z=0`, removing any slab or rib geometry below the floor.

## Geometry checks

Run the topology regression configurations using Blender's Python:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python tests/test_stairs_topology.py
```

Tests cover triangular side topology, mandatory slab thickness, both cut flows, single and multiple steps, reinforcement, deep floor cuts, positive/negative riser offsets, independent bevels and smooth/sharp settings. Multiple-flight tests cover 90°/180° turns, both directions, gaps, overhangs, landing sizes/positions and flight/landing connections. Every edge must have exactly two adjacent faces; the shell must be connected, consistently oriented and enclose the expected volume (with an allowance for rounded corners). Tests also verify specific sharp/smooth edges, the conditional front join and independent control of both bevels.

Run configurator and railing integration checks with:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python tests/test_stairs_configurator.py
```

These checks cover automatic/manual rebuilding, independent and shared-mesh copies, root transforms,
material preservation, child selection, invalid-input recovery, Type 1 tube/post controls, closed railing
components, undo, registration lifecycle and save/reopen persistence. Persistence tests write a `.blend`
in a temporary directory; set `STAIRS_TEST_OUTPUT` to choose the output folder.

`tests/test_stairs_railing_details.py` additionally verifies connected post profiles, the absence of
internal shaft caps, both support constructions, side-count inheritance, the outer-route switch for
both turn directions and migration of existing saved configurations. Run it with the same Blender
command, replacing the Python script path.

For a recessed profile, start with **Riser Offset = 0.04 m**, **Slab Height = 0.12 m**, **Upper Bevel Width = 0.018 m / 5 segments** and **Lower Bevel Width = 0.006 m / 3 segments**, with both profiles at `0.5`. These controls are in the **Stairs Configurator** side panel. The development junction points directly to the EasyGridAligner source folder; procedural geometry is in `geometry/`, object settings in `props/`, rebuilding in `services/`, actions in `ops/`, and panels in `ui/`.
