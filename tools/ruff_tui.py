#!/usr/bin/env python3
"""
Interactive Ruff explorer (inquirer-based).

Features:
- Summary of Ruff findings grouped by rule code.
- Choose sort order: by frequency or alphabetically by code.
- Drill-down to per-violation file:line:col with message.
- Open directly in VS Code at file:line:col (`code -g`).
- Show Ruff's proposed fix as a unified diff (via `--diff`) per file or rule.
- View rule documentation (`ruff rule CODE`).
- Show annotated Ruff output with "help:" suggestions for a rule.
- Apply fixes for a rule (current path) or for a single file.
- Explicit "Return", "Re-run Ruff", "Change path", and "Quit" actions on menus.

Usage:
    python ruff_tui.py               # scan current dir
    python ruff_tui.py backend/      # scan a subdir
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

try:
    import inquirer  # pip install inquirer
except Exception:
    print("This script requires the 'inquirer' package: pip install inquirer", file=sys.stderr)
    raise

# Sentinel values for control flow
RET = "__return__"
QUIT = "__quit__"
RERUN = "__rerun__"
CHPATH = "__changepath__"


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    filepath: str
    line: int
    col: int


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command and return CompletedProcess with text output (never raises)."""
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def run_ruff_json(target: str) -> list[dict[str, Any]]:
    """Run ruff and return parsed JSON list of issues."""
    cmd = ["ruff", "check", "--quiet", "--output-format=json", target]
    res = _run(cmd)
    out = (res.stdout or "").strip()

    # Ruff exits non-zero when there are findings. We only care about stdout JSON.
    if not out:
        # If nothing in stdout, print stderr for context (e.g., config error)
        if res.stderr:
            print(res.stderr, file=sys.stderr)
        return []

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        # Fallback: try to extract a JSON array if there was extra noise
        start = out.find("[")
        end = out.rfind("]")
        if start != -1 and end != -1:
            data = json.loads(out[start : end + 1])
        else:
            raise
    if not isinstance(data, list):
        return []
    return data


def parse_issues(raw: list[dict[str, Any]]) -> list[Issue]:
    issues: list[Issue] = []
    for it in raw:
        code = it.get("code") or ""
        message = it.get("message") or ""
        filename = it.get("filename") or it.get("file") or ""
        loc = it.get("location") or {}
        line = int(loc.get("row") or loc.get("line") or 1)
        col = int(loc.get("column") or loc.get("col") or 1)
        issues.append(Issue(code=code, message=message, filepath=filename, line=line, col=col))
    return issues


def group_by_code(
    issues: list[Issue],
) -> tuple[Counter[str], dict[str, str], dict[str, list[Issue]]]:
    counts: Counter[str] = Counter()
    first_msg: dict[str, str] = {}
    by_code: dict[str, list[Issue]] = defaultdict(list)
    for iss in issues:
        counts[iss.code] += 1
        if iss.code not in first_msg:
            first_msg[iss.code] = iss.message
        by_code[iss.code].append(iss)
    return counts, first_msg, by_code


def refresh(path: str) -> tuple[list[Issue], Counter[str], dict[str, str], dict[str, list[Issue]]]:
    raw = run_ruff_json(path)
    issues = parse_issues(raw)
    counts, first_msg, by_code = group_by_code(issues)
    return issues, counts, first_msg, by_code


def format_summary_line(code: str, msg: str, count: int) -> str:
    short = msg.strip().replace("\n", " ")
    if len(short) > 90:
        short = short[:87] + "..."
    return f"{code}: {short} — {count}"


def pick_sort_order() -> str | None:
    q = [
        inquirer.List(
            "order",
            message="How do you want to sort the rules?",
            choices=[
                ("By frequency (most common first)", "freq"),
                ("Alphabetically by code", "alpha"),
                ("⮐ Return", RET),
                ("Quit", QUIT),
            ],
            default="freq",
        )
    ]
    ans = inquirer.prompt(q)
    if not ans:
        return RET
    return ans["order"]


def ask_change_path(current_path: str) -> str | None:
    q = [
        inquirer.Text(
            "path",
            message=f"Enter new path (current: {current_path})",
            default=current_path,
        )
    ]
    ans = inquirer.prompt(q)
    if not ans:
        return None
    return ans["path"]


def pick_rule(counts: Counter[str], first_msg: dict[str, str]) -> str | None:
    if not counts:
        print("No issues found.")
        return None

    order = pick_sort_order()
    if order in (None, RET):
        return RET
    if order == QUIT:
        return QUIT

    if order == "freq":
        sorted_codes = [code for code, _ in counts.most_common()]
    else:
        sorted_codes = sorted(counts.keys())

    choices = [
        inquirer.List(
            "rule",
            message="Pick a rule to drill into:",
            choices=[
                ("⟳ Re-run Ruff", RERUN),
                ("⇱ Change path", CHPATH),
                ("⮐ Return", RET),
                ("Quit", QUIT),
                *[
                    (format_summary_line(code, first_msg.get(code, ""), counts[code]), code)
                    for code in sorted_codes
                ],
            ],
            carousel=True,
        )
    ]
    ans = inquirer.prompt(choices)
    if not ans:
        return RET
    return ans["rule"]


def pick_occurrence(issues: list[Issue]) -> Issue | str | None:
    items: list[tuple[str, Issue | str]] = [
        ("⮐ Return", RET),
        ("⟳ Re-run Ruff", RERUN),
        ("Quit", QUIT),
    ]
    for iss in sorted(issues, key=lambda x: (x.filepath, x.line, x.col)):
        label = f"{iss.filepath}:{iss.line}:{iss.col} — {iss.message}"
        if len(label) > 180:
            label = label[:177] + "..."
        items.append((label, iss))

    questions = [
        inquirer.List(
            "occ",
            message="Select an occurrence:",
            choices=items,
            carousel=True,
        )
    ]
    ans = inquirer.prompt(questions)
    if not ans:
        return RET
    return ans["occ"]


def open_in_vscode(issue: Issue) -> None:
    path = issue.filepath
    if not os.path.exists(path):
        print(f"File not found: {path}. Location: {path}+{issue.line}", file=sys.stderr)
        return
    subprocess.run(["code", "-g", f"{path}:{issue.line}:{issue.col}"], check=False)


def show_rule_docs(rule_code: str) -> None:
    """Display Ruff's rule documentation for a code."""
    res = _run(["ruff", "rule", rule_code])
    out = res.stdout.strip() or res.stderr.strip() or "(no documentation available)"
    print("\n" + out + "\n")
    input("(press Enter to return)")


def show_rule_diff_for_path(rule_code: str, path: str) -> None:
    """Show unified diff of proposed fixes for a rule across the current path."""
    res = _run(["ruff", "check", "--quiet", "--select", rule_code, "--diff", path])
    out = res.stdout.strip()
    if not out:
        print(f"\nNo diff available for {rule_code} on path: {path}\n")
    else:
        print("\n" + out + "\n")
    input("(press Enter to return)")


def show_file_diff_for_rule(rule_code: str, file_path: str) -> None:
    """Show unified diff of proposed fixes for this rule in a single file."""
    res = _run(["ruff", "check", "--quiet", "--select", rule_code, "--diff", file_path])
    out = res.stdout.strip()
    if not out:
        print(f"\nNo diff available for {rule_code} in file: {file_path}\n")
    else:
        print("\n" + out + "\n")
    input("(press Enter to return)")


def show_rule_help(rule_code: str, path: str) -> None:
    """Show Ruff’s annotated output (with 'help:' hints) for this rule on the current path."""
    print(f"\nShowing Ruff help output for {rule_code} in {path}...\n")

    def run(fmt: str) -> str:
        res = subprocess.run(
            ["ruff", "check", "--select", rule_code, f"--output-format={fmt}", path],
            text=True,
            capture_output=True,
            check=False,
        )
        return (res.stdout or res.stderr or "").strip()

    # Try 'full' first (includes code frames and `help:`), then degrade.
    for fmt in ("full", "text", "concise"):
        out = run(fmt)
        if out:
            print(out)
            break
    else:
        print("(no help available)")

    print()
    input("(press Enter to return)")


def apply_rule_fix_for_path(rule_code: str, path: str) -> None:
    """Apply fixes for a rule across the current path."""
    print(f"\nApplying Ruff fixes for {rule_code} in {path} ...\n")
    res = _run(["ruff", "check", "--quiet", "--select", rule_code, "--fix", path])
    if res.stderr.strip():
        print(res.stderr)
    print("Done.\n")
    input("(press Enter to return)")


def apply_rule_fix_for_file(rule_code: str, file_path: str) -> None:
    """Apply fixes for a rule in a single file."""
    print(f"\nApplying Ruff fixes for {rule_code} in {file_path} ...\n")
    res = _run(["ruff", "check", "--quiet", "--select", rule_code, "--fix", file_path])
    if res.stderr.strip():
        print(res.stderr)
    print("Done.\n")
    input("(press Enter to return)")


def show_rule_menu(rule_code: str, rule_issues: list[Issue], path: str) -> str:
    """
    Returns sentinel: RET to go back to rule list, QUIT to exit, RERUN to refresh.
    """
    while True:
        q = [
            inquirer.List(
                "action",
                message=f"{rule_code}: {len(rule_issues)} occurrences — choose an action",
                choices=[
                    ("⮐ Return to rule list", RET),
                    ("⟳ Re-run Ruff", RERUN),
                    ("Quit", QUIT),
                    ("Browse occurrences (open in VS Code)", "browse"),
                    ("Print all occurrences to stdout", "print"),
                    ("Show rule documentation", "docs"),
                    ("Show proposed fix (diff) for this rule — current path", "diff_rule_path"),
                    ("Show Ruff help for this rule (annotated hints)", "help_rule_path"),
                    ("Apply fixes for this rule — current path", "fix_rule_path"),
                ],
            )
        ]
        ans = inquirer.prompt(q)
        if not ans:
            return RET
        action = ans["action"]

        if action in (RET, QUIT, RERUN):
            return action

        if action == "browse":
            sel = pick_occurrence(rule_issues)
            if sel in (None, RET):
                continue
            if sel == QUIT:
                return QUIT
            if sel == RERUN:
                return RERUN
            assert isinstance(sel, Issue)

            # Submenu for a single occurrence/file
            while True:
                sub = [
                    inquirer.List(
                        "occ_action",
                        message=f"{sel.filepath}:{sel.line}:{sel.col}",
                        choices=[
                            ("⮐ Return", RET),
                            ("⟳ Re-run Ruff", RERUN),
                            ("Quit", QUIT),
                            ("Open in VS Code", "open"),
                            ("Show proposed fix (diff) for this file", "diff_file"),
                            ("Apply fixes for this rule in this file", "fix_file"),
                        ],
                    )
                ]
                a2 = inquirer.prompt(sub)
                if not a2:
                    break
                occ_action = a2["occ_action"]

                if occ_action == RET:
                    break
                if occ_action in (QUIT, RERUN):
                    return occ_action
                if occ_action == "open":
                    open_in_vscode(sel)
                elif occ_action == "diff_file":
                    show_file_diff_for_rule(rule_code, sel.filepath)
                elif occ_action == "fix_file":
                    apply_rule_fix_for_file(rule_code, sel.filepath)

        elif action == "print":
            for iss in sorted(rule_issues, key=lambda x: (x.filepath, x.line, x.col)):
                print(f"{iss.filepath}:{iss.line}:{iss.col}: {rule_code} {iss.message}")
            input("\n(press Enter to return)")

        elif action == "docs":
            show_rule_docs(rule_code)

        elif action == "diff_rule_path":
            show_rule_diff_for_path(rule_code, path)

        elif action == "help_rule_path":
            show_rule_help(rule_code, path)

        elif action == "fix_rule_path":
            apply_rule_fix_for_path(rule_code, path)

        # loop continues


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive Ruff findings explorer (inquirer).")
    parser.add_argument(
        "path", nargs="?", default=".", help="Path to check (default: current directory)."
    )
    args = parser.parse_args()

    path = args.path
    issues, counts, first_msg, by_code = refresh(path)

    if not issues:
        print("No issues found.")
        return

    while True:
        chosen = pick_rule(counts, first_msg)
        if chosen in (None, RET):
            break
        if chosen == QUIT:
            break
        if chosen == RERUN:
            issues, counts, first_msg, by_code = refresh(path)
            if not issues:
                print("No issues found.")
                break
            continue
        if chosen == CHPATH:
            new_path = ask_change_path(path)
            if new_path:
                path = new_path
                issues, counts, first_msg, by_code = refresh(path)
                if not issues:
                    print("No issues found.")
                    break
            continue

        # Chosen is a rule code (narrow type for mypy)
        assert isinstance(chosen, str)
        result = show_rule_menu(chosen, by_code.get(chosen, []), path)
        if result == QUIT:
            break
        if result == RERUN:
            issues, counts, first_msg, by_code = refresh(path)
            if not issues:
                print("No issues found.")
                break
            # fall back to top to pick rule again


if __name__ == "__main__":
    main()
