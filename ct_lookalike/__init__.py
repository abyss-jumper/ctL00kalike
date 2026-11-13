"""ct-lookalike: find lookalike domains in Certificate Transparency logs."""

__version__ = "0.1.0"

from .similarity import Candidate, analyze, score_candidate  # noqa: F401
