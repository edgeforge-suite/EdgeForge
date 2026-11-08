"""Models for static compatibility verification of generated apps."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class HarnessCheckSeverity(str, Enum):
    """Severity level for one harness check."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class HarnessCheck(BaseModel):
    """One compatibility verification result."""

    name: str
    severity: HarnessCheckSeverity
    passed: bool
    message: str


class HarnessReport(BaseModel):
    """Summary of compatibility verification against generated output."""

    output_dir: Path
    checks: list[HarnessCheck] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            check.passed
            for check in self.checks
            if check.severity == HarnessCheckSeverity.ERROR
        )

    @property
    def errors(self) -> list[HarnessCheck]:
        return [
            check
            for check in self.checks
            if not check.passed and check.severity == HarnessCheckSeverity.ERROR
        ]

    @property
    def warnings(self) -> list[HarnessCheck]:
        return [
            check
            for check in self.checks
            if not check.passed and check.severity == HarnessCheckSeverity.WARNING
        ]
