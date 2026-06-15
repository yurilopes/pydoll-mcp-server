"""Architecture constraints that keep the repository efficient for coding agents."""

import ast
import warnings
from pathlib import Path

from pydoll_mcp_server.tool_catalog import TOOLS

TARGET_LINES = 400
HARD_LIMIT_LINES = 450


def test_python_files_stay_within_flexible_line_budget() -> None:
    root = Path(__file__).parents[2]
    oversized: list[str] = []
    review_required: list[str] = []
    for base in (root / 'src', root / 'tests'):
        for path in base.rglob('*.py'):
            lines = len(path.read_text(encoding='utf-8').splitlines())
            if lines > HARD_LIMIT_LINES:
                oversized.append(f'{path.relative_to(root)}: {lines}')
            elif lines > TARGET_LINES:
                review_required.append(f'{path.relative_to(root)}: {lines}')
    if review_required:
        warnings.warn(
            'Python files above the 400-line target require review justification:\n' + '\n'.join(review_required),
            stacklevel=1,
        )
    assert not oversized, 'Python files above the 450-line hard limit:\n' + '\n'.join(oversized)


def test_broad_exception_catches_exist_only_at_mcp_tool_boundaries() -> None:
    root = Path(__file__).parents[2]
    tool_names = {tool.__name__ for tool in TOOLS}
    violations: list[str] = []

    for path in (root / 'src').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        violations.extend(_find_broad_exception_violations(tree, path.relative_to(root), tool_names))

    assert not violations, 'Broad exception handling outside MCP tool boundaries:\n' + '\n'.join(violations)


def _find_broad_exception_violations(
    node: ast.AST,
    path: Path,
    tool_names: set[str],
    owner: str = '<module>',
) -> list[str]:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        owner = node.name

    violations: list[str] = []
    if isinstance(node, ast.ExceptHandler):
        catches_exception = isinstance(node.type, ast.Name) and node.type.id == 'Exception'
        if (node.type is None or catches_exception) and owner not in tool_names:
            violations.append(f'{path}:{node.lineno} ({owner})')

    if isinstance(node, ast.Call):
        is_suppress = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == 'suppress'
            and any(isinstance(argument, ast.Name) and argument.id == 'Exception' for argument in node.args)
        )
        if is_suppress:
            violations.append(f'{path}:{node.lineno} (suppress(Exception))')

    for child in ast.iter_child_nodes(node):
        violations.extend(_find_broad_exception_violations(child, path, tool_names, owner))
    return violations
