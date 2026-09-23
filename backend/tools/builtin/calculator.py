import ast
import operator
from typing import Any, Callable

from backend.tools.base import RiskLevel, Tool, ToolResult


class CalculatorTool(Tool):
    name = "calculator"
    description = "Evaluate a safe arithmetic expression with basic operators."
    risk_level = RiskLevel.READ_ONLY
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression, for example: 123 * 456",
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    }

    _binary_ops: dict[type[ast.operator], Callable[[float, float], float]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_ops: dict[type[ast.unaryop], Callable[[float], float]] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        expression = arguments.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError("calculator requires a non-empty string expression.")

        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 64:
            raise ValueError("Expression is too complex.")

        result = self._eval_node(tree.body)
        normalized = int(result) if isinstance(result, float) and result.is_integer() else result
        return ToolResult(ok=True, content=str(normalized), data=normalized)

    def _eval_node(self, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("Only numeric literals are allowed.")
            return node.value

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self._binary_ops:
                raise ValueError(f"Operator is not allowed: {op_type.__name__}")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("Exponent is too large.")
            result = self._binary_ops[op_type](left, right)
            if abs(result) > 1_000_000_000_000:
                raise ValueError("Result is too large.")
            return result

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self._unary_ops:
                raise ValueError(f"Unary operator is not allowed: {op_type.__name__}")
            return self._unary_ops[op_type](self._eval_node(node.operand))

        raise ValueError(f"Expression element is not allowed: {type(node).__name__}")
