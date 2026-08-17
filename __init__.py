bl_info = {
    "name": "Modular Stair Generator",
    "author": "Mykyta Petrenko (aka SqueezyPixels)",
    "version": (1, 0, 0),
    "blender": (4, 1, 0),
    "location": "View3D > Add > Mesh > Modular Stairs; Sidebar > Modular",
    "description": "Generate modular stairs and provide UV and grid-snapping tools.",
    "category": "Add Mesh",
}

from . import ops, props, ui


modules = (props, ops, ui)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
