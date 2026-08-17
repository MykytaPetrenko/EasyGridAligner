from . import snap, stairs, uv_from_coordinates


modules = (stairs, snap, uv_from_coordinates)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
