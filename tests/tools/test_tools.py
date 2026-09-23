import pytest

from backend.tools.builtin.calculator import CalculatorTool
from backend.tools.builtin.files import ReadFileTool, SearchFilesTool
from backend.tools.policy import PolicyDecisionType, ToolPolicy


def test_calculator_rejects_unsafe_expression():
    with pytest.raises(ValueError):
        CalculatorTool().execute({"expression": "__import__('os').system('echo unsafe')"})


def test_calculator_computes_basic_expression():
    result = CalculatorTool().execute({"expression": "123 * 456"})

    assert result.ok is True
    assert result.data == 56088


def test_workspace_path_traversal_rejected(tmp_path):
    tool = ReadFileTool(tmp_path)

    with pytest.raises(ValueError):
        tool.execute({"path": "../outside.txt"})


def test_read_and_search_files(tmp_path):
    (tmp_path / "note.txt").write_text("agent harness trace memory", encoding="utf-8")
    read = ReadFileTool(tmp_path).execute({"path": "note.txt"})
    search = SearchFilesTool(tmp_path).execute({"query": "trace"})

    assert "agent harness" in read.content
    assert search.data[0]["path"] == "note.txt"


def test_policy_allow_for_read_only():
    tool = CalculatorTool()

    assert ToolPolicy().evaluate(tool).decision == PolicyDecisionType.ALLOW
