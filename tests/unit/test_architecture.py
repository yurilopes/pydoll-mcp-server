"""Architecture constraints that keep the repository efficient for coding agents."""

from pathlib import Path


def test_python_files_stay_within_flexible_line_budget() -> None:
    root = Path(__file__).parents[2]
    oversized: list[str] = []
    for base in (root / 'src', root / 'tests'):
        for path in base.rglob('*.py'):
            lines = len(path.read_text(encoding='utf-8').splitlines())
            if lines > 420:
                oversized.append(f'{path.relative_to(root)}: {lines}')
    assert not oversized, 'Python files above the 420-line hard limit:\n' + '\n'.join(oversized)
