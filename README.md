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
- All generated modules are created as one merged mesh object.

## Parameters

- **Steps**: number of stair modules
- **Width**: total width along `X`
- **Riser**: vertical rise per step
- **Tread**: run per step along negative `Y`
- **Lower Slab**: adds a lower offset slab under regular stair modules
- **Slab Z Offset**: vertical offset of the lower slab, enabled only when **Lower Slab** is checked
- **Side Ribs**: adds reinforcement ribs below both side edges of regular stair modules
- **Rib Width**: width of each side rib, measured inward from the side
- **Rib Z Offset**: downward extrusion distance for side ribs
- **Cut Top**: when enabled, rib edge loops continue through the top stair polygons; when disabled, only the rib corner remains inset and the upper loop vertices collapse back to the sides
- **Cut Type**: start cut mode: **None**, **Floor Cut**, or **Box Cut**
- **Cut Width**: box cut distance from the origin along negative `Y`; values at or above **Tread** remove the first module's lower triangle/slab/rib portion
- **Cut Edge Flow**: available for **Box Cut** only; **Corner** merges the cut top to the tread corner, while **Through** keeps cut edges through the first module
- **Floor Cut**: clips the full generated mesh at `Z=0`, removing any lower triangle, slab, or rib geometry below the floor
