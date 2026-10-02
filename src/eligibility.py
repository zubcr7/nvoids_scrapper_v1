"""Candidate Eligibility Gater.

Evaluates explicit engagement, location, and experience requirements
against candidate's user-confirmed ground truth profile.
Employs a 3-state evaluation model:
- Satisfied: Evidence explicitly confirms eligibility
- Not satisfied: Explicit conflict detected (e.g. W2 only or unsupported location)
- Unknown: Missing or ambiguous information (routes to review)
"""
import re
import json
import os
from typing import Dict, Any, List, Optional, Tuple

from src.jd_decomposer import StructuredJobDescription

class EligibilityAssessment:
    """Outcome of evaluating a candidate's ground truth profile against job conditions."""
    def __init__(
        self,
        overall_status: str,  # "Satisfied", "Not satisfied", "Unknown"
        reasons: List[str],
        c2c_status: str = "Unknown",
        location_status: str = "Unknown",
        experience_status: str = "Satisfied",
        has_confirmed_conflict: bool = False
    ):
        self.overall_status = overall_status
        self.reasons = reasons
        self.c2c_status = c2c_status
        self.location_status = location_status
        self.experience_status = experience_status
        self.has_confirmed_conflict = has_confirmed_conflict

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "reasons": self.reasons,
            "c2c_status": self.c2c_status,
            "location_status": self.location_status,
            "experience_status": self.experience_status,
            "has_confirmed_conflict": self.has_confirmed_conflict
        }


class EligibilityGater:
    """Evaluates candidate eligibility using ground-truth profile."""

    def __init__(self, profile_path: str = "config/profile.json"):
        self.profile = {}
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    self.profile = json.load(f)
            except Exception as e:
                print(f"[Eligibility] Error loading profile: {e}")

    def evaluate_eligibility(self, job: StructuredJobDescription) -> EligibilityAssessment:
        """Evaluate job against candidate ground truth."""
        prefs = self.profile.get("engagement_preferences", {})
        cand = self.profile.get("candidate", {})
        reasons = []
        has_conflict = False

        # 1. C2C Engagement Check
        c2c_status = "Unknown"
        job_text_lower = job.raw_text.lower()

        # Check for explicit conflict (W2 only / no C2C)
        w2_only_markers = [
            "w2 only", "w-2 only", "no c2c", "no c-to-c", "no corp-to-corp",
            "no corp to corp", "no 1099", "strictly w2", "only w2"
        ]
        if any(marker in job_text_lower for marker in w2_only_markers):
            c2c_status = "Not satisfied"
            has_conflict = True
            reasons.append("Engagement conflict: Job explicitly specifies W2 only / No C2C.")
        elif any(marker in job_text_lower for marker in ["c2c", "corp to corp", "corp-to-corp", "c-to-c", "1099"]):
            c2c_status = "Satisfied"
            reasons.append("Engagement satisfied: Job accepts C2C / Corp-to-Corp.")
        else:
            # Not mentioned in posting -> Unknown
            c2c_status = "Unknown"
            reasons.append("Engagement note: C2C not explicitly mentioned in posting (defaulting to portal standard).")

        # 2. Location & Onsite Availability Check
        location_status = "Satisfied"
        supported_locations = [l.lower() for l in prefs.get("locations_supported", [])]

        # Extract days onsite
        onsite_days_match = re.search(r'(\d+)\s*days?\s*onsite', job_text_lower)
        if onsite_days_match:
            days_req = int(onsite_days_match.group(1))
            max_days = prefs.get("max_onsite_days_per_week", 5)
            if days_req > max_days:
                location_status = "Not satisfied"
                has_conflict = True
                reasons.append(f"Location conflict: Requires {days_req} days onsite (max confirmed is {max_days}).")
            else:
                reasons.append(f"Location satisfied: Candidate willing to do {days_req} days onsite.")

        # Check specific location matching
        for loc in ["dallas", "buffalo", "new york", "charlotte", "atlanta", "san francisco", "remote"]:
            if loc in job_text_lower:
                if any(loc in sup for sup in supported_locations) or "remote" in supported_locations or "usa nationwide" in supported_locations:
                    location_status = "Satisfied"
                    reasons.append(f"Location confirmed: {loc.title()} is in candidate's supported locations.")
                    break

        # 3. Candidate Experience Duration Check
        cand_years = float(cand.get("total_experience_years", 10.0))
        experience_status = "Satisfied"
        exp_match = re.search(r'(\d+)\+?\s*years?(?:\s*of)?\s*experience', job_text_lower)
        if exp_match:
            req_years = float(exp_match.group(1))
            if req_years > cand_years + 2.0:  # Allow small flexibility, but block 15+ years for a 10-year candidate
                experience_status = "Not satisfied"
                has_conflict = True
                reasons.append(f"Experience conflict: Requires {int(req_years)}+ years (Candidate has {cand_years} years).")
            else:
                reasons.append(f"Experience satisfied: Candidate has {cand_years} years (Job requests {int(req_years)}+ years).")

        # Overall synthesis
        if has_conflict:
            overall = "Not satisfied"
        elif c2c_status == "Satisfied" and location_status == "Satisfied" and experience_status == "Satisfied":
            overall = "Satisfied"
        else:
            overall = "Unknown"

        return EligibilityAssessment(
            overall_status=overall,
            reasons=reasons,
            c2c_status=c2c_status,
            location_status=location_status,
            experience_status=experience_status,
            has_confirmed_conflict=has_conflict
        )
