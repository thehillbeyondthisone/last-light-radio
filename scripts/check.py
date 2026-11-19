"""Dependency-free baseline: Python syntax and repository whitespace conventions."""

import ast
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems = []
    files = []
    for directory in ("last_light_radio", "tests", "scripts"):
        files.extend((root / directory).rglob("*.py"))
    for path in sorted(files):
        text = path.read_text(encoding="utf-8-sig")
        try:
            ast.parse(text, filename=str(path))
        except SyntaxError as error:
            problems.append(f"{path.relative_to(root)}:{error.lineno}: {error.msg}")
        for number, line in enumerate(text.splitlines(), 1):
            if line.rstrip() != line or "\t" in line:
                problems.append(f"{path.relative_to(root)}:{number}: trailing whitespace or tab")
        if text and not text.endswith("\n"):
            problems.append(f"{path.relative_to(root)}: missing final newline")
    for problem in problems:
        print(problem)
    print(f"Checked {len(files)} Python files; {len(problems)} problem(s).")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
