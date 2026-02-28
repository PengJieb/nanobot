---
name: py-writer
description: Enforce class-centric Python file structure with auto-documentation. Always active — guides the agent to use py_writer tool instead of write_file for .py files.
always: true
---

# Python Writer

## Rules

1. **All skill implementations must use Python** as the primary language.
2. **Use `py_writer` tool** (not `write_file`) for every `.py` file.
3. **One class per file** — each `.py` file must contain a primary class as its core abstraction.
4. **Module-level functions delegate to the class** — top-level functions should instantiate or call into the class, not contain standalone logic.
5. **After implementing a skill, create `LOGIC.md`** in the skill directory describing the running logic.

## py_writer Tool

The `py_writer` tool validates and writes Python files:

```
py_writer(path="module.py", content="...", class_name="MyClass")
```

- Validates Python syntax via `ast.parse`
- Ensures at least one top-level class exists
- Optionally validates a specific `class_name`
- Warns if top-level functions don't reference any class
- Auto-generates a companion `.md` file with class docs and method signatures

## LOGIC.md Template

After implementing a Python-based skill, create a `LOGIC.md`:

```markdown
# Running Logic

## Entry Point
- Primary class and how it is instantiated

## Flow
1. Step-by-step execution flow
2. Key method calls and their purpose

## Dependencies
- External libraries or tools required
```
