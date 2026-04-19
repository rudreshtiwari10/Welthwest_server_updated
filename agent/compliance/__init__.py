"""
Compliance layer — enforces SEBI-safe output from the agent.

Usage:
    from agent.compliance import moderate_response
    result = moderate_response(text)
    if result.violations:
        text = result.sanitized
"""

from agent.compliance.output_filter import moderate_response, ModerationResult

__all__ = ["moderate_response", "ModerationResult"]
