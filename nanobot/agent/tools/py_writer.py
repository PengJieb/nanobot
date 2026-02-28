"""PyWriter tool: write Python files with class-centric structure validation and auto-doc generation."""

import ast
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.filesystem import _resolve_path


class PyWriterTool(Tool):
    """Tool to write validated Python files and auto-generate companion documentation."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "py_writer"

    @property
    def description(self) -> str:
        return (
            "Write a Python file with structural validation and auto-generate a companion .md doc. "
            "The Python code must contain at least one top-level class definition. "
            "Prefer this over write_file for all .py files."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Target file path (must end with .py)",
                },
                "content": {
                    "type": "string",
                    "description": "Python source code to write",
                },
                "class_name": {
                    "type": "string",
                    "description": "Optional: primary class name to validate exists in the code",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, class_name: str | None = None, **kwargs: Any) -> str:
        # Validate .py extension
        if not path.endswith(".py"):
            return "Error: path must end with .py"

        # Resolve and enforce directory restriction
        try:
            file_path = _resolve_path(path, self._workspace, self._allowed_dir)
        except PermissionError as e:
            return f"Error: {e}"

        # Parse and validate Python syntax
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return f"Error: Python syntax error: {e}"

        # Collect top-level classes and functions
        top_classes = [node for node in ast.iter_child_nodes(tree) if isinstance(node, ast.ClassDef)]
        top_functions = [node for node in ast.iter_child_nodes(tree) if isinstance(node, ast.FunctionDef)]

        if not top_classes:
            return "Error: Python file must contain at least one top-level class definition"

        # Validate class_name if specified
        class_names = {cls.name for cls in top_classes}
        if class_name and class_name not in class_names:
            return (
                f"Error: class '{class_name}' not found. "
                f"Available classes: {', '.join(sorted(class_names))}"
            )

        # Warn about top-level functions that don't reference any class
        warnings = []
        for func in top_functions:
            if not _func_references_classes(func, class_names):
                warnings.append(
                    f"Warning: top-level function '{func.name}' does not reference any class"
                )

        # Write the .py file
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        except Exception as e:
            return f"Error writing file: {e}"

        # Generate companion .md documentation
        md_path = file_path.with_suffix(".md")
        md_content = _generate_doc(tree, top_classes, class_name)
        try:
            md_path.write_text(md_content, encoding="utf-8")
        except Exception as e:
            return f"Error writing documentation: {e}"

        result = f"Successfully wrote {file_path} and generated {md_path}"
        if warnings:
            result += "\n" + "\n".join(warnings)
        return result


def _func_references_classes(func: ast.FunctionDef, class_names: set[str]) -> bool:
    """Check if a function body references any of the given class names."""
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and node.id in class_names:
            return True
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in class_names:
            return True
    return False


def _get_docstring(node: ast.AST) -> str | None:
    """Extract docstring from a module, class, or function node."""
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, (ast.Constant,))
        and isinstance(node.body[0].value.value, str)
    ):
        return node.body[0].value.value.strip()
    return None


def _format_args(args: ast.arguments) -> str:
    """Format function arguments as a signature string."""
    parts = []
    # Calculate defaults offset: defaults align to the end of args
    num_args = len(args.args)
    num_defaults = len(args.defaults)
    default_offset = num_args - num_defaults

    for i, arg in enumerate(args.args):
        if arg.arg == "self":
            continue
        annotation = ""
        if arg.annotation:
            annotation = f": {ast.unparse(arg.annotation)}"
        default = ""
        default_idx = i - default_offset
        if default_idx >= 0:
            default = f" = {ast.unparse(args.defaults[default_idx])}"
        parts.append(f"{arg.arg}{annotation}{default}")

    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    for arg in args.kwonlyargs:
        annotation = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        parts.append(f"{arg.arg}{annotation}")
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)


def _generate_doc(tree: ast.Module, classes: list[ast.ClassDef], primary_class_name: str | None) -> str:
    """Generate markdown documentation from the AST."""
    lines: list[str] = []

    # Module docstring
    module_doc = _get_docstring(tree)
    if module_doc:
        lines.append(f"# {module_doc}")
        lines.append("")
    else:
        lines.append("# Module Documentation")
        lines.append("")

    # Determine primary class
    if primary_class_name:
        primary = next((c for c in classes if c.name == primary_class_name), classes[0])
    else:
        primary = classes[0]

    # Document each class
    for cls in classes:
        is_primary = cls is primary
        prefix = "(Primary) " if is_primary and len(classes) > 1 else ""
        lines.append(f"## {prefix}Class `{cls.name}`")
        lines.append("")

        class_doc = _get_docstring(cls)
        if class_doc:
            lines.append(class_doc)
            lines.append("")

        # Constructor
        init_method = None
        methods = []
        for item in cls.body:
            if isinstance(item, ast.FunctionDef):
                if item.name == "__init__":
                    init_method = item
                elif not item.name.startswith("_"):
                    methods.append(item)

        if init_method:
            args_str = _format_args(init_method.args)
            lines.append("### Constructor")
            lines.append("")
            lines.append("```python")
            lines.append(f"{cls.name}({args_str})")
            lines.append("```")
            lines.append("")

            # List constructor parameters
            params = [a for a in init_method.args.args if a.arg != "self"]
            if params:
                lines.append("**Parameters:**")
                lines.append("")
                num_args = len(init_method.args.args)
                num_defaults = len(init_method.args.defaults)
                default_offset = num_args - num_defaults
                for i, arg in enumerate(init_method.args.args):
                    if arg.arg == "self":
                        continue
                    annotation = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
                    default_idx = i - default_offset
                    default = f" = {ast.unparse(init_method.args.defaults[default_idx])}" if default_idx >= 0 else ""
                    lines.append(f"- `{arg.arg}{annotation}{default}`")
                lines.append("")

        # Public methods
        if methods:
            lines.append("### Methods")
            lines.append("")
            for method in methods:
                args_str = _format_args(method.args)
                ret = f" -> {ast.unparse(method.returns)}" if method.returns else ""
                lines.append(f"- `{method.name}({args_str}){ret}`")
                method_doc = _get_docstring(method)
                if method_doc:
                    lines.append(f"  {method_doc}")
            lines.append("")

    # Running Logic section
    lines.append("## Running Logic")
    lines.append("")
    lines.append(f"Primary class: `{primary.name}`")
    lines.append("")
    init = None
    for item in primary.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            init = item
            break
    if init:
        args_str = _format_args(init.args)
        lines.append(f"Instantiate: `{primary.name}({args_str})`")
        lines.append("")
    public_methods = [
        item for item in primary.body
        if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
    ]
    if public_methods:
        lines.append("Public interface:")
        lines.append("")
        for m in public_methods:
            lines.append(f"1. `{m.name}()` — {_get_docstring(m) or 'No description'}")
        lines.append("")

    return "\n".join(lines)
