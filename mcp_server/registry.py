TOOL_REGISTRY = {}


def register_tool(name: str):
    def decorator(cls):
        TOOL_REGISTRY[name] = cls()
        return cls
    return decorator


def get_tool(name: str):
    return TOOL_REGISTRY.get(name)


def list_tools():
    return list(TOOL_REGISTRY.keys())