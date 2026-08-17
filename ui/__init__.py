from . import tools_panel


modules = (tools_panel,)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
