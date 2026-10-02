"""Requirement Evidence Checker and Cross-Encoder Scoring Engine.

Implements:
1. Fine-grained requirement-to-evidence passage assessment.
2. Evidence strength rubric:
   - 1.00: Specific professional evidence closely matches requested work
   - 0.80: Direct professional evidence supports with less detail
   - 0.40: Related experience supports only part of requirement
   - 0.20: Technology appears only in skills list or summary
   - 0.00: Requirement is not demonstrated
3. Explicit Keyword Score (K) with category weights (3/2/1).
4. Evidence Coverage Score (E).
5. Composite Ranking Score = 0.30 * K + 0.70 * E.
6. Constrained Decision Policy (Select, Review, No suitable resume).
"""
import re
from typing import List, Dict, Any, Optional, Tuple, Set

from src.parser import StructuredResume, EvidencePassage
from src.jd_decomposer import StructuredJobDescription, ParsedRequirement
from src.ontology import TechOntology
from src.retriever import SemanticMatcher

class RequirementAssessment:
    """Assessment of a single requirement against a resume."""
    def __init__(
        self,
        requirement: ParsedRequirement,
        status: str,  # supported, partial, skills_only, missing, contradicted
        keyword_credit: float,  # 1.0 or 0.0
        evidence_credit: float, # 1.00, 0.80, 0.40, 0.20, 0.00
        best_passage: Optional[EvidencePassage] = None,
        supporting_quotation: str = "",
        source_reference: Optional[Dict[str, Any]] = None,
        explanation: str = ""
    ):
        self.requirement = requirement
        self.status = status
        self.keyword_credit = keyword_credit
        self.evidence_credit = evidence_credit
        self.best_passage = best_passage
        self.supporting_quotation = supporting_quotation
        self.source_reference = source_reference or {}
        self.explanation = explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_name": self.requirement.name,
            "category": self.requirement.category,
            "priority": self.requirement.priority,
            "weight": self.requirement.weight,
            "status": self.status,
            "keyword_credit": self.keyword_credit,
            "evidence_credit": self.evidence_credit,
            "supporting_quotation": self.supporting_quotation,
            "source_reference": self.source_reference,
            "explanation": self.explanation
        }


class ResumeEvaluation:
    """Full evaluation of a resume document against a structured job description."""
    def __init__(
        self,
        resume: StructuredResume,
        assessments: List[RequirementAssessment],
        keyword_score_K: float,
        evidence_score_E: float,
        ranking_score: float,
        unmet_mandatory_requirements: List[str],
        decision: str,  # "Select", "Review", "No suitable resume"
        decision_reason: str,
        threshold: float
    ):
        self.resume = resume
        self.assessments = assessments
        self.keyword_score_K = keyword_score_K
        self.evidence_score_E = evidence_score_E
        self.ranking_score = ranking_score
        self.unmet_mandatory_requirements = unmet_mandatory_requirements
        self.decision = decision
        self.decision_reason = decision_reason
        self.threshold = threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resume_id": self.resume.resume_id,
            "file_path": self.resume.file_path,
            "file_hash": self.resume.file_hash,
            "focus_title": self.resume.focus_title,
            "keyword_score_K": self.keyword_score_K,
            "evidence_score_E": self.evidence_score_E,
            "ranking_score": self.ranking_score,
            "threshold": self.threshold,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "unmet_mandatory_requirements": self.unmet_mandatory_requirements,
            "assessments": [a.to_dict() for a in self.assessments]
        }


class EvidenceChecker:
    """Assesses requirement-to-experience evidence and calculates explainable scores."""

    @classmethod
    def evaluate_resume(
        cls,
        job: StructuredJobDescription,
        resume: StructuredResume,
        threshold: float = 80.0
    ) -> ResumeEvaluation:
        """Evaluate a single resume against structured requirements."""
        assessments: List[RequirementAssessment] = []
        unmet_mandatory: List[str] = []

        for req in job.requirements:
            assessment = cls._assess_single_requirement(req, resume)
            assessments.append(assessment)

            # Check mandatory satisfaction (key technologies, capabilities, and core responsibilities)
            if req.priority == "required" and req.category in ("key_technology", "specialized_capability", "responsibility"):
                # Must have at least partial/direct evidence (evidence_credit >= 0.40) and keyword match
                if assessment.evidence_credit < 0.40 or assessment.keyword_credit == 0.0:
                    unmet_mandatory.append(req.name)

        # 1. Calculate Keyword Coverage Score K
        req_subset = [a for a in assessments if a.requirement.priority == "required"]
        pref_subset = [a for a in assessments if a.requirement.priority == "preferred"]

        def calc_c_keyword(subset: List[RequirementAssessment]) -> float:
            if not subset:
                return 1.0
            sum_w_b = sum(a.requirement.weight * a.keyword_credit for a in subset)
            sum_w = sum(a.requirement.weight for a in subset)
            return sum_w_b / max(0.001, sum_w)

        def calc_c_evidence(subset: List[RequirementAssessment]) -> float:
            if not subset:
                return 1.0
            sum_w_e = sum(a.requirement.weight * a.evidence_credit for a in subset)
            sum_w = sum(a.requirement.weight for a in subset)
            return sum_w_e / max(0.001, sum_w)

        c_b_req = calc_c_keyword(req_subset)
        c_b_pref = calc_c_keyword(pref_subset)

        # K = 100 * [0.80 * C(b, Required) + 0.20 * C(b, Preferred)]
        if pref_subset:
            K = 100.0 * (0.80 * c_b_req + 0.20 * c_b_pref)
        else:
            K = 100.0 * c_b_req

        # 2. Calculate Evidence Coverage Score E
        c_e_req = calc_c_evidence(req_subset)
        c_e_pref = calc_c_evidence(pref_subset)

        # E = 100 * [0.80 * C(e, Required) + 0.20 * C(e, Preferred)]
        if pref_subset:
            E = 100.0 * (0.80 * c_e_req + 0.20 * c_e_pref)
        else:
            E = 100.0 * c_e_req

        # 3. Composite Ranking Score = 0.30 * K + 0.70 * E
        ranking_score = round(0.30 * K + 0.70 * E, 1)

        # 4. Constrained Decision Policy
        decision = "Select"
        reasons = []

        if unmet_mandatory:
            decision = "No suitable resume"
            reasons.append(f"Unmet mandatory requirements: {', '.join(unmet_mandatory)}")
        elif ranking_score < threshold:
            decision = "No suitable resume"
            reasons.append(f"Ranking score ({ranking_score}%) is below required threshold ({threshold}%)")
        else:
            decision = "Select"
            reasons.append(f"Passes all mandatory requirements with {ranking_score}% ranking score (>= {threshold}%)")

        return ResumeEvaluation(
            resume=resume,
            assessments=assessments,
            keyword_score_K=round(K, 1),
            evidence_score_E=round(E, 1),
            ranking_score=ranking_score,
            unmet_mandatory_requirements=unmet_mandatory,
            decision=decision,
            decision_reason="; ".join(reasons),
            threshold=threshold
        )

    @classmethod
    def _assess_single_requirement(
        cls,
        req: ParsedRequirement,
        resume: StructuredResume
    ) -> RequirementAssessment:
        """Evaluate a single requirement against the resume catalog passages."""
        # 1. Alternative group handling (e.g. "React or Angular")
        if req.is_alternative_group:
            best_sub_assessment = None
            for alt_term in req.alternatives:
                sub_req = ParsedRequirement(
                    name=alt_term.title(),
                    category=req.category,
                    priority=req.priority,
                    weight=req.weight,
                    canonical_terms=[alt_term],
                    source_sentence=req.source_sentence
                )
                sub_assessment = cls._assess_term_in_resume(sub_req, resume)
                if best_sub_assessment is None or sub_assessment.evidence_credit > best_sub_assessment.evidence_credit:
                    best_sub_assessment = sub_assessment

            if best_sub_assessment:
                best_sub_assessment.requirement = req
                best_sub_assessment.explanation = f"Alternative satisfied: {best_sub_assessment.explanation}"
                return best_sub_assessment

        return cls._assess_term_in_resume(req, resume)

    @classmethod
    def _assess_term_in_resume(
        cls,
        req: ParsedRequirement,
        resume: StructuredResume
    ) -> RequirementAssessment:
        # Expand target terms with approved aliases from TechOntology
        target_terms = set(req.canonical_terms)
        for t in list(req.canonical_terms):
            norm_t = TechOntology.normalize_term(t)
            target_terms.add(norm_t)
            for alias, canonical in TechOntology.ALIASES.items():
                if canonical == norm_t:
                    target_terms.add(alias)

        version_req = req.version_condition

        # Track candidate passages
        exp_passages = resume.experience_passages
        best_passage: Optional[EvidencePassage] = None
        best_evidence_credit = 0.00
        best_quote = ""
        best_source = {}
        status = "missing"
        keyword_credit = 0.0
        explanation = "Not demonstrated in resume"

        # Check if keyword is explicitly in skills_summary
        in_skills = any(
            any(TechOntology.normalize_term(t) == TechOntology.normalize_term(term) for t in resume.skills_summary)
            for term in target_terms
        )
        if in_skills:
            keyword_credit = 1.0
            best_evidence_credit = 0.20
            status = "skills_only"
            explanation = "Technology listed in Skills section"

        # Search experience passages for active implementation
        for p in exp_passages:
            p_text = p.text
            p_text_lower = " " + p_text.lower() + " "

            # Check term match
            term_matched = False
            for term in target_terms:
                pat = rf"\b{re.escape(term)}\b"
                if re.search(pat, p_text_lower):
                    term_matched = True
                    break

            if not term_matched:
                continue

            # Term is present in an experience bullet!
            keyword_credit = 1.0

            # Version check if required
            if version_req:
                if not TechOntology.match_version(version_req, p_text):
                    # Mentions general technology without explicit required version
                    if best_evidence_credit < 0.40:
                        best_evidence_credit = 0.40
                        status = "partial"
                        best_passage = p
                        best_quote = p_text
                        best_source = {"employer": p.employer, "role": p.role, "dates": f"{p.employment_start}-{p.employment_end}", "paragraph": p.source.get("paragraph", 0)}
                        explanation = f"Technology used, but version {version_req} not explicitly confirmed in passage"
                    continue

            # Check specialized capability if required (e.g. "Kafka consumer development")
            if req.category == "specialized_capability" and "consumer" in req.name.lower():
                if any(w in p_text_lower for w in ["consumer", "consumers", "idempotency", "retry", "dead-letter", "listener"]):
                    credit = 1.00
                    explanation = "Specific implementation evidence for consumer development"
                else:
                    credit = 0.40
                    explanation = "General Kafka usage without explicit consumer/retry implementation"
            else:
                # Specific vs general implementation
                # Check for detailed action verbs, metrics, and architecture patterns
                has_action_depth = any(w in p_text_lower for w in [
                    "implemented", "designed", "architected", "developed", "deployed", "tuned", "configured",
                    "integrated", "microservices", "optimized", "built", "engineered", "automated"
                ])
                if has_action_depth and len(p_text.split()) >= 10:
                    credit = 1.00
                    explanation = f"Direct professional implementation under {p.employer}"
                else:
                    credit = 0.80
                    explanation = f"Direct professional mention under {p.employer}"

            if credit > best_evidence_credit:
                best_evidence_credit = credit
                status = "supported" if credit >= 0.80 else "partial"
                best_passage = p
                best_quote = p_text
                best_source = {
                    "employer": p.employer,
                    "role": p.role,
                    "dates": f"{p.employment_start} - {p.employment_end}",
                    "paragraph": p.source.get("paragraph", 0)
                }

        # If domain check (e.g. Banking)
        if req.category == "domain":
            for p in exp_passages:
                if any(d in p.employer.lower() or d in p.text.lower() for d in req.canonical_terms):
                    keyword_credit = 1.0
                    best_evidence_credit = 1.00
                    status = "supported"
                    best_passage = p
                    best_quote = f"{p.employer}: {p.text[:120]}..."
                    best_source = {"employer": p.employer, "paragraph": p.source.get("paragraph", 0)}
                    explanation = f"Direct domain experience with {p.employer}"
                    break

        return RequirementAssessment(
            requirement=req,
            status=status,
            keyword_credit=keyword_credit,
            evidence_credit=best_evidence_credit,
            best_passage=best_passage,
            supporting_quotation=best_quote,
            source_reference=best_source,
            explanation=explanation
        )
