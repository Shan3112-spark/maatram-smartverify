from dataclasses import dataclass, field, asdict
from typing import Optional

LABELS = {"PASS": "✅", "FAIL": "❌", "REVIEW": "⚠️"}


@dataclass
class CheckResult:
    name: str
    status: str                      # PASS | FAIL | REVIEW
    label: str                       # Match / Mismatch / Pass / Fail / Needs review ...
    details: str = ""
    entered: Optional[str] = None
    uploaded: Optional[str] = None
    confidence: Optional[float] = None
    group: str = "marks"             # marks | photo

    def to_dict(self):
        return asdict(self)


@dataclass
class Report:
    application_id: str
    overall: str                     # PASS | FAIL | REVIEW
    checks: list = field(default_factory=list)
    reasons: list = field(default_factory=list)   # exception report lines

    def to_dict(self):
        return {"application_id": self.application_id, "overall": self.overall,
                "reasons": self.reasons, "checks": [c.to_dict() for c in self.checks]}
