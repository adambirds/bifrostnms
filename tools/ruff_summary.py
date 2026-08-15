#!/usr/bin/env python3
import json
import subprocess
import sys
from collections import Counter, defaultdict
from typing import Any


def main() -> None:
    # Run ruff once; don't raise on non-zero (ruff returns 1 when it finds issues)
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["ruff", "check", "--quiet", "--output-format=json", "."],
        capture_output=True,
        text=True,
        check=False,
    )

    stdout = (result.stdout or "").strip()
    if not stdout:
        # If there's no JSON, show stderr for context (e.g. config error) and exit
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        print("No issues found.")
        return

    # Parse JSON output (a list of issue dicts)
    issues: list[dict[str, Any]]
    try:
        issues = json.loads(stdout)
    except json.JSONDecodeError:
        print("Failed to parse Ruff JSON output.", file=sys.stderr)
        print(stdout)
        sys.exit(1)

    # Tally counts by rule code and keep a representative message
    counts: Counter[str] = Counter()
    messages: defaultdict[str, str] = defaultdict(str)

    for issue in issues:
        code = issue.get("code", "")
        message = issue.get("message", "")
        if not code:
            continue
        counts[code] += 1
        if not messages[code]:
            messages[code] = message

    if not counts:
        print("No issues found.")
        return

    # Print results sorted by most frequent
    for code, count in counts.most_common():
        print(f"{code}: {messages[code]} — {count}")


if __name__ == "__main__":
    main()
