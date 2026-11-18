from . import snap_settings, stairs


modules = (snap_settings, stairs)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
