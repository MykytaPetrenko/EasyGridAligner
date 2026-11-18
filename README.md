# Modular Stair Generator

Blender add-on for generating modular stair meshes, snapping mesh/UV data to a
grid, and generating UVs from 3D coordinates.

## Install

Use this folder as the add-on folder in Blender, then enable **Modular Stair Generator**.

The operator is available at:

`Shift+A > Mesh > Modular Stairs`

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

For a recessed profile, start with **Riser Offset = 0.04 m**, **Slab Height = 0.12 m**, **Upper Bevel Width = 0.018 m / 5 segments** and **Lower Bevel Width = 0.006 m / 3 segments**, with both profiles at `0.5`. These controls are in the **Modular Stairs** creation/redo panel (`F9`). Reload **Modular Stair Generator** or restart Blender after source changes; the development junction points directly to `EasyGridAligner/ops/stairs.py`.
