from . import snap_settings


modules = (snap_settings,)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
