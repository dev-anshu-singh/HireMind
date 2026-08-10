"""
Re-export schemas from centralized location app.schemas.hiring_profile.
"""

from app.schemas.hiring_profile import ParsedSkill, ParsedHiringProfile

__all__ = ["ParsedSkill", "ParsedHiringProfile"]
