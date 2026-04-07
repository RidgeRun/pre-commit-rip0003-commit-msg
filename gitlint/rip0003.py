# Copyright (C) 2026 RidgeRun, LLC (http://www.ridgerun.com)
# All Rights Reserved.
#
# The contents of this software are proprietary and confidential to
# RidgeRun, LLC. No part of this program may be photocopied,
# reproduced or translated into another programming language without
# prior written consent of RidgeRun, LLC. The user is free to modify
# the source code after obtaining a software license from RidgeRun.
# All source code changes must be provided back to RidgeRun without
# any encumbrance.
"""Custom gitlint rules that enforce RIP-0003 commit message conventions."""

from __future__ import annotations

from functools import cache
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

from gitlint.rules import (  # pyright: ignore[reportMissingTypeStubs]
    CommitRule,
    RuleViolation,
)


MAINLINE_BRANCHES = {"main", "develop", "master"}


class _CommitMessage(Protocol):
    title: str | None
    body: str | None
    full: str | None


class _Commit(Protocol):
    message: _CommitMessage
    parents: Sequence[_Commit]


def _first_line_nr(lines: Sequence[str], pred: Callable[[str], bool]) -> int:
    for i, line in enumerate(lines, start=1):
        if pred(line):
            return i
    return 1


def _is_merge_commit(commit: _Commit) -> bool:
    """Return True when the commit has more than one parent."""
    return len(commit.parents) > 1


@cache
def _current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""

    return result.stdout.strip()


def _uses_mainline_rules(commit: _Commit) -> bool:
    """Return True when RIP-0003 merge/mainline rules should be applied."""
    del commit
    return _current_branch() in MAINLINE_BRANCHES


class RegularTitleRule(CommitRule):
    """Validate title format for regular (non-merge) commits."""

    id = "UC00"
    name = "rip0003-regular-title"

    def validate(self, commit: _Commit) -> list[RuleViolation] | None:
        """Reject reserved merge prefixes and enforce capitalized title text."""
        if _uses_mainline_rules(commit):
            return None

        title = (commit.message.title or "").strip()

        if title.startswith(("feat: ", "fix: ")):
            return [
                RuleViolation(
                    self.id,
                    "Regular commits must not start with 'feat: ' or 'fix: '",
                    line_nr=1,
                )
            ]

        if not title[:1].isupper():
            return [
                RuleViolation(
                    self.id, "Title must start with a capital letter", line_nr=1
                )
            ]
        return None


class RegularBodyNoBreakingChange(CommitRule):
    """Ensure regular commits do not include BREAKING CHANGE footers."""

    id = "UC01"
    name = "rip0003-regular-body-no-breaking-change"

    def validate(self, commit: _Commit) -> list[RuleViolation] | None:
        """Reject any BREAKING CHANGE footer in regular commits."""
        if _uses_mainline_rules(commit):
            return None

        lines = (commit.message.full or "").splitlines()

        bc_ln = _first_line_nr(lines, lambda line: line.startswith("BREAKING CHANGE"))
        if bc_ln != 1:  # found
            return [
                RuleViolation(
                    self.id,
                    "Regular commits must not contain 'BREAKING CHANGE: ...'",
                    line_nr=bc_ln,
                )
            ]
        return None


class MergeTitleRule(CommitRule):
    """Validate merge title prefix and capitalization."""

    id = "UC02"
    name = "rip0003-merge-title"

    def validate(self, commit: _Commit) -> list[RuleViolation] | None:
        """Require feat/fix prefix and capitalized title content."""
        if not _uses_mainline_rules(commit):
            return None

        title = (commit.message.title or "").strip()

        if not title.startswith(("feat: ", "fix: ")):
            return [
                RuleViolation(
                    self.id,
                    "Merge commits must start with 'feat: ' or 'fix: '",
                    line_nr=1,
                )
            ]

        after = title.split(": ", 1)[1] if ": " in title else ""
        if not after[:1].isupper():
            return [
                RuleViolation(
                    self.id,
                    "Title text after 'feat: ' / 'fix: ' must start with a "
                    "capital letter",
                    line_nr=1,
                )
            ]
        return None


class MergeBreakingChangeFooter(CommitRule):
    """Validate the optional BREAKING CHANGE footer for merge commits."""

    id = "UC03"
    name = "rip0003-merge-breaking-change-footer"

    def validate(self, commit: _Commit) -> list[RuleViolation] | None:
        """Enforce a single, properly formatted BREAKING CHANGE footer."""
        lines = (commit.message.full or "").splitlines()

        bc_lns = [
            (i, line)
            for i, line in enumerate(lines, start=1)
            if line.startswith("BREAKING CHANGE")
        ]
        if not _uses_mainline_rules(commit) or not bc_lns:
            return None

        if len(bc_lns) > 1:
            return [
                RuleViolation(
                    self.id,
                    "Only one 'BREAKING CHANGE: ...' footer line is allowed",
                    line_nr=bc_lns[1][0],
                )
            ]

        bc_ln, bc_line = bc_lns[0]

        if not bc_line.startswith("BREAKING CHANGE: "):
            return [
                RuleViolation(
                    self.id,
                    "Use exactly 'BREAKING CHANGE: <description>' "
                    "(colon + space required)",
                    line_nr=bc_ln,
                )
            ]

        # Must be last non-empty line
        last_nonempty = max(
            (i for i, line in enumerate(lines, start=1) if line.strip()),
            default=1,
        )
        if bc_ln != last_nonempty:
            return [
                RuleViolation(
                    self.id,
                    "'BREAKING CHANGE: ...' must be the last non-empty line",
                    line_nr=bc_ln,
                )
            ]

        # Must be separated as its own paragraph (blank line before),
        # if there is preceding content.
        if bc_ln > 1:
            prev = lines[bc_ln - 2]
            if prev.strip():
                return [
                    RuleViolation(
                        self.id,
                        "'BREAKING CHANGE: ...' must be preceded by a blank line",
                        line_nr=bc_ln,
                    )
                ]
        return None
