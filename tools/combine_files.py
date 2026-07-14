"""Bundle the app's Python source into one blob for the embedded (C++) runtime.

The harness is split across packages (providers/, retrieval/, tools/,
procedures/) plus api.py. The embedded interpreter cannot see these on disk, so
we register each module in ``sys.modules`` at runtime (its source carried as a
string), in dependency order, then run api.py — whose imports now resolve from
``sys.modules`` instead of the filesystem.

Third-party deps (fastapi, chromadb, openai, ...) are NOT bundled here — the
binary loads them from ``.venv/lib/.../site-packages`` via PYTHONPATH at runtime
(see src/main.cpp).
"""

import json
import os

# Each package: (name, [submodule files in dependency order], __init__ file).
# Submodules are registered before the package __init__ so its relative imports
# (``from .base import ...``) resolve.
PACKAGES = [
    (
        "providers",
        ["src/providers/base.py", "src/providers/openai_provider.py"],
        "src/providers/__init__.py",
    ),
    ("retrieval", ["src/retrieval/store.py"], "src/retrieval/__init__.py"),
    ("tools", ["src/tools/registry.py"], "src/tools/__init__.py"),
    ("procedures", ["src/procedures/loader.py"], "src/procedures/__init__.py"),
]
APP_FILE = os.path.join("src", "api.py")
OUTPUT_FILE = os.path.join("tools", "temp_combined.py")

BOOTSTRAP = '''import sys as _sys
import types as _types


def _ensure_package(name):
    module = _types.ModuleType(name)
    module.__name__, module.__path__, module.__package__ = name, [], name
    _sys.modules[name] = module
    parent, _, child = name.rpartition(".")
    if parent:
        setattr(_sys.modules[parent], child, module)


def _register_submodule(name, source):
    module = _types.ModuleType(name)
    module.__name__, module.__package__ = name, name.rpartition(".")[0]
    _sys.modules[name] = module
    exec(compile(source, name, "exec"), module.__dict__)
    parent, _, child = name.rpartition(".")
    setattr(_sys.modules[parent], child, module)


def _exec_init(name, source):
    exec(compile(source, name, "exec"), _sys.modules[name].__dict__)
'''


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    parts = [BOOTSTRAP, ""]
    for pkg, subs, init in PACKAGES:
        parts.append(f"_ensure_package({json.dumps(pkg)})")
        for sub in subs:
            name = f"{pkg}.{os.path.splitext(os.path.basename(sub))[0]}"
            parts.append(
                f"_register_submodule({json.dumps(name)}, {json.dumps(_read(sub))})"
            )
        parts.append(f"_exec_init({json.dumps(pkg)}, {json.dumps(_read(init))})")
        parts.append("")

    parts.append("# ----- api.py (runs as __main__) -----")
    parts.append(_read(APP_FILE))

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(
        f"Bundled {len(PACKAGES)} packages + api.py -> "
        f"'{os.path.abspath(OUTPUT_FILE)}'"
    )


if __name__ == "__main__":
    main()
