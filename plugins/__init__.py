"""内置插件集合。

load_builtin() 在控制器启动时调用一次，把内置扩展点注册进 registry。
扩展方式有两种：

1. 在 plugins/ 下加一个模块，并在 load_builtin() 里补一行 import；
2. 不改本仓库，在 config.json 的 `plugin_modules` 里写自己的模块路径
   （例如 "mycompany.eve_plugins"），由 load_external() 加载。
"""
_LOADED = False


def load_builtin():
    """注册内置插件。幂等。"""
    global _LOADED
    if _LOADED:
        return
    from . import executors  # noqa: F401
    from . import guards  # noqa: F401
    from . import hooks  # noqa: F401
    from . import schedules  # noqa: F401
    _LOADED = True


def load_external(modules):
    """加载 config.plugin_modules 指定的外部插件模块。"""
    import importlib

    loaded = []
    for name in modules or []:
        importlib.import_module(name)
        loaded.append(name)
    return loaded
