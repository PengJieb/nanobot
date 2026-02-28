"""Tests for PyWriterTool."""

from pathlib import Path

import pytest

from nanobot.agent.tools.py_writer import PyWriterTool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def tool(workspace: Path) -> PyWriterTool:
    return PyWriterTool(workspace=workspace, allowed_dir=workspace)


VALID_CODE = '''\
"""Example module."""


class Greeter:
    """A simple greeter."""

    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        """Return greeting."""
        return f"Hello, {self.name}!"
'''

VALID_CODE_WITH_FUNC = '''\
"""Module with delegating function."""


class Adder:
    """Adds numbers."""

    def __init__(self, a: int, b: int):
        self.a = a
        self.b = b

    def result(self) -> int:
        return self.a + self.b


def add(a: int, b: int) -> int:
    return Adder(a, b).result()
'''

CODE_NO_CLASS = '''\
def hello():
    print("hi")
'''

CODE_SYNTAX_ERROR = '''\
def broken(
    print("hi")
'''

CODE_UNRELATED_FUNC = '''\
"""Module."""


class Foo:
    pass


def standalone():
    return 42
'''


async def test_reject_non_py_path(tool: PyWriterTool) -> None:
    result = await tool.execute(path="file.txt", content=VALID_CODE)
    assert "Error" in result
    assert ".py" in result


async def test_reject_syntax_error(tool: PyWriterTool) -> None:
    result = await tool.execute(path="bad.py", content=CODE_SYNTAX_ERROR)
    assert "Error" in result
    assert "syntax" in result.lower()


async def test_reject_no_class(tool: PyWriterTool) -> None:
    result = await tool.execute(path="noclass.py", content=CODE_NO_CLASS)
    assert "Error" in result
    assert "class" in result.lower()


async def test_reject_wrong_class_name(tool: PyWriterTool) -> None:
    result = await tool.execute(path="greeter.py", content=VALID_CODE, class_name="NotExist")
    assert "Error" in result
    assert "NotExist" in result
    assert "Greeter" in result


async def test_successful_write(tool: PyWriterTool, workspace: Path) -> None:
    result = await tool.execute(path="greeter.py", content=VALID_CODE)
    assert "Successfully" in result

    py_file = workspace / "greeter.py"
    md_file = workspace / "greeter.md"
    assert py_file.exists()
    assert md_file.exists()

    py_content = py_file.read_text()
    assert "class Greeter" in py_content

    md_content = md_file.read_text()
    assert "Greeter" in md_content
    assert "greet" in md_content
    assert "Constructor" in md_content


async def test_successful_write_with_class_name(tool: PyWriterTool, workspace: Path) -> None:
    result = await tool.execute(path="greeter.py", content=VALID_CODE, class_name="Greeter")
    assert "Successfully" in result
    assert (workspace / "greeter.py").exists()
    assert (workspace / "greeter.md").exists()


async def test_delegating_function_no_warning(tool: PyWriterTool) -> None:
    result = await tool.execute(path="adder.py", content=VALID_CODE_WITH_FUNC)
    assert "Warning" not in result
    assert "Successfully" in result


async def test_warn_unrelated_function(tool: PyWriterTool) -> None:
    result = await tool.execute(path="foo.py", content=CODE_UNRELATED_FUNC)
    assert "Successfully" in result
    assert "Warning" in result
    assert "standalone" in result


async def test_path_restriction(tmp_path: Path) -> None:
    allowed = tmp_path / "safe"
    allowed.mkdir()
    tool = PyWriterTool(workspace=allowed, allowed_dir=allowed)
    result = await tool.execute(path="/etc/evil.py", content=VALID_CODE)
    assert "Error" in result


async def test_md_contains_running_logic(tool: PyWriterTool, workspace: Path) -> None:
    await tool.execute(path="greeter.py", content=VALID_CODE)
    md_content = (workspace / "greeter.md").read_text()
    assert "Running Logic" in md_content
    assert "Greeter" in md_content


async def test_subdirectory_creation(tool: PyWriterTool, workspace: Path) -> None:
    result = await tool.execute(path="sub/dir/module.py", content=VALID_CODE)
    assert "Successfully" in result
    assert (workspace / "sub" / "dir" / "module.py").exists()
    assert (workspace / "sub" / "dir" / "module.md").exists()


async def test_md_documents_module_docstring(tool: PyWriterTool, workspace: Path) -> None:
    await tool.execute(path="greeter.py", content=VALID_CODE)
    md_content = (workspace / "greeter.md").read_text()
    assert "Example module" in md_content


async def test_md_documents_constructor_params(tool: PyWriterTool, workspace: Path) -> None:
    await tool.execute(path="greeter.py", content=VALID_CODE)
    md_content = (workspace / "greeter.md").read_text()
    assert "name" in md_content
    assert "str" in md_content
