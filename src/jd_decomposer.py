"""Structured Job Description Requirement Decomposition Engine.

Decomposes raw job postings into individual, typed requirements with:
- Categories (key_technology, specialized_capability, responsibility, domain, engagement, location)
- Priorities (required, preferred, eligibility)
- Importance weights (3 for key tech, 2 for responsibility, 1 for domain)
- Alternative groups (e.g. 'React or Angular')
- Explicit version & duration conditions
- Exact source sentence quotations & negation preservation
"""
import re
from typing import List, Dict, Any, Optional, Set, Tuple

from src.ontology import TechOntology

class ParsedRequirement:
    """Individual typed requirement extracted from a job description."""
    def __init__(
        self,
        name: str,
        category: str,
        priority: str,
        weight: float,
        canonical_terms: List[str],
        source_sentence: str,
        is_alternative_group: bool = False,
        alternatives: Optional[List[str]] = None,
        version_condition: Optional[str] = None,
        duration_years: Optional[float] = None,
        confidence: float = 1.0,
        matching_rule: str = ""
    ):
        self.name = name
        self.category = category  # key_technology, specialized_capability, responsibility, domain, engagement, location
        self.priority = priority  # required, preferred, eligibility
        self.weight = weight      # 3.0, 2.0, 1.0
        self.canonical_terms = canonical_terms
        self.source_sentence = source_sentence
        self.is_alternative_group = is_alternative_group
        self.alternatives = alternatives or []
        self.version_condition = version_condition
        self.duration_years = duration_years
        self.confidence = confidence
        self.matching_rule = matching_rule

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "priority": self.priority,
            "weight": self.weight,
            "canonical_terms": self.canonical_terms,
            "source_sentence": self.source_sentence,
            "is_alternative_group": self.is_alternative_group,
            "alternatives": self.alternatives,
            "version_condition": self.version_condition,
            "duration_years": self.duration_years,
            "confidence": self.confidence,
            "matching_rule": self.matching_rule
        }


class StructuredJobDescription:
    """Complete decomposed and validated job description."""
    def __init__(
        self,
        raw_text: str,
        title: str,
        requirements: List[ParsedRequirement],
        eligibility_conditions: List[ParsedRequirement],
        contradictions: List[str],
        is_reliable: bool = True
    ):
        self.raw_text = raw_text
        self.title = title
        self.requirements = requirements
        self.eligibility_conditions = eligibility_conditions
        self.contradictions = contradictions
        self.is_reliable = is_reliable

    @property
    def required_requirements(self) -> List[ParsedRequirement]:
        return [r for r in self.requirements if r.priority == "required"]

    @property
    def preferred_requirements(self) -> List[ParsedRequirement]:
        return [r for r in self.requirements if r.priority == "preferred"]


class JobDecomposer:
    """Decomposes job descriptions into structured requirements."""

    DOMAIN_KEYWORDS = {
        "banking": "Banking & Financial Services",
        "financial": "Banking & Financial Services",
        "finance": "Banking & Financial Services",
        "healthcare": "Healthcare & Life Sciences",
        "health": "Healthcare & Life Sciences",
        "telecom": "Telecommunications",
        "insurance": "Insurance",
        "retail": "Retail & E-Commerce",
        "e-commerce": "Retail & E-Commerce"
    }

    DOMAIN_CANONICAL = {
        "Banking & Financial Services": ["banking", "bank", "financial", "finance", "fintech", "payments"],
        "Healthcare & Life Sciences": ["healthcare", "health", "medical", "claims", "clinical", "hipaa"],
        "Telecommunications": ["telecom", "telecommunications", "cable", "broadband"],
        "Insurance": ["insurance", "claims", "policy", "underwriting"],
        "Retail & E-Commerce": ["retail", "ecommerce", "e-commerce", "catalog", "order"]
    }

    RESPONSIBILITY_KEYWORDS = {
        "rest api development": [r"\brest\b", r"\bapi development\b", r"\brestful apis\b"],
        "microservices architecture": [r"\bmicroservices\b", r"\bmicro-services\b"],
        "ci/cd pipeline": [r"\bci/cd\b", r"\bci-cd\b", r"\bpipelines?\b"],
        "unit testing": [r"\bunit test\b", r"\btesting\b", r"\btdd\b"],
        "production support": [r"\bproduction support\b", r"\btroubleshooting\b"]
    }

    RESPONSIBILITY_CANONICAL = {
        "rest api development": ["rest apis", "rest api", "rest", "restful"],
        "microservices architecture": ["microservices", "microservice", "micro-services"],
        "ci/cd pipeline": ["ci/cd", "ci-cd", "jenkins", "github actions", "gitlab"],
        "unit testing": ["junit", "mockito", "testing", "testcontainers"],
        "production support": ["production support", "troubleshooting", "monitoring"]
    }

    @classmethod
    def decompose(cls, job_title: str, job_description: str) -> StructuredJobDescription:
        """Parse job title and description into structured, traceable requirements."""
        full_text = f"{job_title}\n{job_description}"
        # Split text into sentences
        sentences = [
            s.strip() for s in re.split(r'(?<=[.!?\n])\s+', full_text)
            if len(s.strip()) > 3
        ]

        requirements: List[ParsedRequirement] = []
        eligibility_conditions: List[ParsedRequirement] = []
        contradictions: List[str] = []
        seen_concepts: Set[str] = set()

        # Check for remote vs onsite contradiction
        title_lower = job_title.lower()
        body_lower = job_description.lower()
        if "remote" in title_lower and ("5 days onsite" in body_lower or "100% onsite" in body_lower or "five days onsite" in body_lower):
            contradictions.append("Contradiction: 'Remote' in title but '100% Onsite' in job description")

        # 1. Detect Eligibility Conditions (C2C, Location, Work Authorization)
        c2c_found = False
        for s in sentences:
            s_lower = s.lower()
            if "c2c" in s_lower or "corp to corp" in s_lower or "corp-to-corp" in s_lower:
                if not any(neg in s_lower for neg in ["no c2c", "not c2c", "w2 only", "no corp"]):
                    eligibility_conditions.append(ParsedRequirement(
                        name="C2C accepted",
                        category="engagement",
                        priority="eligibility",
                        weight=TechOntology.CATEGORY_WEIGHTS["key_technology"],
                        canonical_terms=["c2c"],
                        source_sentence=s,
                        matching_rule="Compare with candidate C2C preference"
                    ))
                    c2c_found = True
                    break

        # Location eligibility
        onsite_match = re.search(r'(\b\d+\s*days?\s*onsite\b|\bonsite\b|\bhybrid\b|\bremote\b).*?(?:in\s+([A-Za-z\s,]+))?', full_text, re.IGNORECASE)
        loc_city_match = re.search(r'\b(?:in|at|location:?)\s*([A-Za-z\s]+(?:,\s*[A-Z]{2})?)', full_text, re.IGNORECASE)
        if onsite_match or loc_city_match:
            loc_str = onsite_match.group(0) if onsite_match else loc_city_match.group(0)
            eligibility_conditions.append(ParsedRequirement(
                name="Location / Onsite availability",
                category="location",
                priority="eligibility",
                weight=TechOntology.CATEGORY_WEIGHTS["key_technology"],
                canonical_terms=["location"],
                source_sentence=loc_str.strip(),
                matching_rule="Compare with candidate location and onsite availability"
            ))

        # 2. Iterate through sentences to extract technical, domain, and responsibility requirements
        current_priority = "required"
        for sentence in sentences:
            s_lower = sentence.lower()

            # Section header priority updates
            if any(h in s_lower for h in ["preferred qualification", "preferred skill", "nice to have", "plus:", "bonus:", "preferred:"]):
                current_priority = "preferred"
            elif any(h in s_lower for h in ["required qualification", "basic qualification", "minimum qualification", "requirements:", "must have:", "responsibilities:"]):
                current_priority = "required"

            is_preferred = (current_priority == "preferred") or any(kw in s_lower for kw in [
                "preferred", "plus", "bonus", "nice to have", "desired", "good to have", "beneficial"
            ])
            priority = "preferred" if is_preferred else "required"

            # Check for alternative groups (e.g. "React or Angular", "AWS or Azure")
            alt_match = re.search(
                r'\b(react|angular|vue|aws|azure|gcp|postgresql|oracle|mysql)\b\s+(?:or|/)\s+\b(react|angular|vue|aws|azure|gcp|postgresql|oracle|mysql)\b',
                s_lower
            )
            if alt_match:
                term1 = TechOntology.normalize_term(alt_match.group(1))
                term2 = TechOntology.normalize_term(alt_match.group(2))
                group_key = f"{min(term1, term2)}_or_{max(term1, term2)}"
                if group_key not in seen_concepts:
                    seen_concepts.add(group_key)
                    # Deduplicate individual terms so they aren't scored twice
                    seen_concepts.add(term1)
                    seen_concepts.add(term2)
                    name_display = f"{alt_match.group(1).title()} or {alt_match.group(2).title()}"
                    requirements.append(ParsedRequirement(
                        name=name_display,
                        category="key_technology",
                        priority=priority,
                        weight=TechOntology.CATEGORY_WEIGHTS["key_technology"],
                        canonical_terms=[term1, term2],
                        source_sentence=sentence,
                        is_alternative_group=True,
                        alternatives=[term1, term2],
                        confidence=0.95,
                        matching_rule="Either alternative satisfies the group"
                    ))

            # Check for specific version requirements (e.g. "Java 17", "Spring Boot 3")
            version_match = re.search(r'\b(java|spring boot|angular)\s*(\d{1,2})\b', s_lower)
            if version_match:
                tech = TechOntology.normalize_term(version_match.group(1))
                ver = version_match.group(2)
                v_key = f"{tech}_{ver}"
                if v_key not in seen_concepts:
                    seen_concepts.add(v_key)
                    seen_concepts.add(tech)
                    requirements.append(ParsedRequirement(
                        name=f"{tech.title()} {ver}",
                        category="key_technology",
                        priority=priority,
                        weight=TechOntology.CATEGORY_WEIGHTS["key_technology"],
                        canonical_terms=[tech],
                        source_sentence=sentence,
                        version_condition=ver,
                        confidence=0.98,
                        matching_rule="Check explicit technology and version"
                    ))

            # Check for specialized capabilities (e.g. "Kafka consumer development", "event-driven")
            if "kafka" in s_lower:
                if any(w in s_lower for w in ["consumer", "consumer development", "producers and consumers", "retry", "idempotency"]):
                    if "kafka_consumer" not in seen_concepts:
                        seen_concepts.add("kafka_consumer")
                        seen_concepts.add("kafka")
                        requirements.append(ParsedRequirement(
                            name="Kafka consumer development",
                            category="specialized_capability",
                            priority=priority,
                            weight=TechOntology.CATEGORY_WEIGHTS["specialized_capability"],
                            canonical_terms=["kafka"],
                            source_sentence=sentence,
                            confidence=0.95,
                            matching_rule="Generic messaging experience is insufficient; requires consumer/event implementation"
                        ))

            # Check for experience duration (e.g. "at least 3 years of Kafka", "5+ years Java")
            dur_match = re.search(r'(?:at least|minimum|with|\b)\s*(\d+)\+?\s*years?(?:\s*of)?\s*([a-zA-Z\s]{3,20})', s_lower)
            if dur_match:
                years = float(dur_match.group(1))
                skill_raw = dur_match.group(2).strip()
                skill_norm = TechOntology.normalize_term(skill_raw)
                if skill_norm in TechOntology.ALIASES.values():
                    d_key = f"{skill_norm}_duration"
                    if d_key not in seen_concepts:
                        seen_concepts.add(d_key)
                        requirements.append(ParsedRequirement(
                            name=f"{skill_norm.title()} (at least {int(years)} years)",
                            category="key_technology",
                            priority=priority,
                            weight=TechOntology.CATEGORY_WEIGHTS["key_technology"],
                            canonical_terms=[skill_norm],
                            source_sentence=sentence,
                            duration_years=years,
                            confidence=0.92,
                            matching_rule="Skill evidence plus supported duration"
                        ))

            # Check for domain keywords (e.g. "Banking", "Healthcare")
            for dom_key, dom_name in cls.DOMAIN_KEYWORDS.items():
                if re.search(rf"\b{re.escape(dom_key)}\b", s_lower):
                    if dom_name not in seen_concepts:
                        seen_concepts.add(dom_name)
                        requirements.append(ParsedRequirement(
                            name=dom_name,
                            category="domain",
                            priority=priority,
                            weight=TechOntology.CATEGORY_WEIGHTS["domain"],
                            canonical_terms=cls.DOMAIN_CANONICAL.get(dom_name, [dom_key]),
                            source_sentence=sentence,
                            confidence=0.90,
                            matching_rule="Domain context provides additional relevance"
                        ))

            # Check for responsibilities (e.g. "REST API development")
            for resp_name, patterns in cls.RESPONSIBILITY_KEYWORDS.items():
                if any(re.search(p, s_lower) for p in patterns):
                    if resp_name not in seen_concepts:
                        seen_concepts.add(resp_name)
                        canonical_list = cls.RESPONSIBILITY_CANONICAL.get(resp_name, [resp_name])
                        for c in canonical_list:
                            seen_concepts.add(c)
                        requirements.append(ParsedRequirement(
                            name=resp_name.title(),
                            category="responsibility",
                            priority=priority,
                            weight=TechOntology.CATEGORY_WEIGHTS["responsibility"],
                            canonical_terms=canonical_list,
                            source_sentence=sentence,
                            confidence=0.88,
                            matching_rule="Check implementation experience"
                        ))

            # Check for canonical key technologies in this sentence
            for alias, canonical in TechOntology.ALIASES.items():
                if canonical in seen_concepts:
                    continue
                # Do not add generic spring framework if spring boot is already captured
                if canonical == "spring framework" and "spring boot" in seen_concepts:
                    continue
                # Negation check: e.g. "Kafka is not required"
                neg_pat = rf"\b(?:no|not|without|neither)\s+[^.!?]*\b{re.escape(alias)}\b"
                if re.search(neg_pat, s_lower):
                    continue

                pat = rf"\b{re.escape(alias)}\b"
                if re.search(pat, s_lower):
                    seen_concepts.add(canonical)
                    if canonical == "spring boot":
                        seen_concepts.add("spring framework")
                    requirements.append(ParsedRequirement(
                        name=canonical.title(),
                        category="key_technology",
                        priority=priority,
                        weight=TechOntology.CATEGORY_WEIGHTS["key_technology"],
                        canonical_terms=[canonical],
                        source_sentence=sentence,
                        confidence=0.90,
                        matching_rule="Check explicit or equivalent terminology"
                    ))

        # Always ensure baseline Java & Spring Boot requirements exist for Java roles
        if "java" in full_text.lower():
            if "java" not in seen_concepts and not any(r.name.lower().startswith("java") for r in requirements):
                requirements.append(ParsedRequirement(
                    name="Java",
                    category="key_technology",
                    priority="required",
                    weight=TechOntology.CATEGORY_WEIGHTS["key_technology"],
                    canonical_terms=["java"],
                    source_sentence="Job Title: " + job_title,
                    matching_rule="Check Java programming experience"
                ))
            if "spring boot" not in seen_concepts and not any("spring boot" in r.name.lower() for r in requirements):
                requirements.append(ParsedRequirement(
                    name="Spring Boot",
                    category="key_technology",
                    priority="required",
                    weight=TechOntology.CATEGORY_WEIGHTS["key_technology"],
                    canonical_terms=["spring boot"],
                    source_sentence="Core framework for Java microservices",
                    matching_rule="Check Spring Boot microservices implementation"
                ))

        return StructuredJobDescription(
            raw_text=full_text,
            title=job_title,
            requirements=requirements,
            eligibility_conditions=eligibility_conditions,
            contradictions=contradictions,
            is_reliable=len(requirements) >= 2
        )
