"""Smart Admission Document Validation (MH26-01): rule-based, no GenAI/LLM."""
from .pipeline import validate_application  # noqa: F401
from .config import PhotoRules, MarkRules   # noqa: F401
