---
name: py-writer
description: Enforce class-centric Python file structure with auto-documentation. Always active — guides the agent to use py_writer tool instead of write_file for .py files.
always: true
---

# Python Writer

## When to Use

Use `py_writer` when a skill or task **needs Python code**. Not all skills require Python — markdown-only or shell-script-based skills should NOT be forced into a Python class structure.

## Rules

1. **All skill implementations must use Python** as the primary language.
2. **Use `py_writer` tool** (not `write_file`) for every `.py` file.
3. **One class per file** — each `.py` file must contain a primary class as its core abstraction.
4. **Module-level functions delegate to the class** — top-level functions should instantiate or call into the class, not contain standalone logic.

## py_writer Tool

```
py_writer(path="module.py", content="...", class_name="MyClass")
```

- Validates Python syntax via `ast.parse`
- Ensures at least one top-level class exists
- Optionally validates a specific `class_name`
- Warns if top-level functions don't reference any class
- Auto-generates a companion `.md` file with class docs and method signatures
