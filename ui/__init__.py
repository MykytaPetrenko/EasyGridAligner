from . import tools_panel, stairs


modules = (tools_panel, stairs)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
