from importlib import import_module

_ROUTER_MODULES = {
    "analyze_router": "analyze",
    "cookies_router": "cookies",
    "downloads_router": "downloads",
    "enterprise_router": "enterprise",
    "media_router": "media",
    "render_router": "render",
    "system_router": "system",
}

__all__ = list(_ROUTER_MODULES)


def __getattr__(name: str):
    module_name = _ROUTER_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    router = import_module(f"backend.routers.{module_name}").router
    globals()[name] = router
    return router
