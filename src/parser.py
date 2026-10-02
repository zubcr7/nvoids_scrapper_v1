"""Structured Resume Parser and Evidence Catalog.

Parses DOCX and PDF resumes into structured, traceable evidence statements
preserving employers, roles, dates, paragraph indices, and technology usages.
Caches parsed resumes by SHA-256 file hash for sub-millisecond repeat access.
"""
import os
import re
import json
import hashlib
import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Set, Tuple

from src.ontology import TechOntology

class EvidencePassage:
    """An individual traceable evidence passage from a resume."""
    def __init__(
        self,
        resume_id: str,
        section: str,
        text: str,
        employer: str = "",
        role: str = "",
        employment_start: str = "",
        employment_end: str = "",
        technologies: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        source: Optional[Dict[str, Any]] = None
    ):
        self.resume_id = resume_id
        self.section = section
        self.text = text
        self.employer = employer
        self.role = role
        self.employment_start = employment_start
        self.employment_end = employment_end
        self.technologies = technologies or []
        self.capabilities = capabilities or []
        self.source = source or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resume_id": self.resume_id,
            "section": self.section,
            "employer": self.employer,
            "role": self.role,
            "employment_start": self.employment_start,
            "employment_end": self.employment_end,
            "text": self.text,
            "technologies": self.technologies,
            "capabilities": self.capabilities,
            "source": self.source
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvidencePassage":
        return cls(
            resume_id=d.get("resume_id", ""),
            section=d.get("section", ""),
            text=d.get("text", ""),
            employer=d.get("employer", ""),
            role=d.get("role", ""),
            employment_start=d.get("employment_start", ""),
            employment_end=d.get("employment_end", ""),
            technologies=d.get("technologies", []),
            capabilities=d.get("capabilities", []),
            source=d.get("source", {})
        )


class StructuredResume:
    """Complete structured representation of a resume document."""
    def __init__(
        self,
        resume_id: str,
        file_path: str,
        file_hash: str,
        focus_title: str,
        passages: List[EvidencePassage],
        skills_summary: Set[str],
        parsing_status: str = "valid",
        parsing_error: str = ""
    ):
        self.resume_id = resume_id
        self.file_path = file_path
        self.file_hash = file_hash
        self.focus_title = focus_title
        self.passages = passages
        self.skills_summary = skills_summary
        self.parsing_status = parsing_status
        self.parsing_error = parsing_error

    @property
    def experience_passages(self) -> List[EvidencePassage]:
        return [p for p in self.passages if p.section == "professional_experience"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resume_id": self.resume_id,
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "focus_title": self.focus_title,
            "passages": [p.to_dict() for p in self.passages],
            "skills_summary": list(self.skills_summary),
            "parsing_status": self.parsing_status,
            "parsing_error": self.parsing_error
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StructuredResume":
        passages = [EvidencePassage.from_dict(p) for p in d.get("passages", [])]
        return cls(
            resume_id=d.get("resume_id", ""),
            file_path=d.get("file_path", ""),
            file_hash=d.get("file_hash", ""),
            focus_title=d.get("focus_title", ""),
            passages=passages,
            skills_summary=set(d.get("skills_summary", [])),
            parsing_status=d.get("parsing_status", "valid"),
            parsing_error=d.get("parsing_error", "")
        )


class ResumeCatalog:
    """Manages the versioned resume catalog and hash-based caching."""

    COMMON_CAPABILITIES = {
        "consumer development": [r"\bconsumer\b", r"\bconsumers\b", r"\bconsumer group\b"],
        "producer development": [r"\bproducer\b", r"\bproducers\b"],
        "idempotency": [r"\bidempotent\b", r"\bidempotency\b"],
        "retry handling": [r"\bretry\b", r"\bretries\b", r"\bbackoff\b"],
        "dead-letter recovery": [r"\bdead-letter\b", r"\bdlq\b", r"\bpoison message\b"],
        "stream processing": [r"\bkafka streams\b", r"\bstreaming\b", r"\bflink\b"],
        "microservices architecture": [r"\bmicroservices\b", r"\bmicroservice\b", r"\bdistributed\b"],
        "rest api development": [r"\brest\b", r"\brestful\b", r"\bopenapi\b", r"\bswagger\b"],
        "batch processing": [r"\bspring batch\b", r"\bbatch\b"],
        "cloud deployment": [r"\beks\b", r"\becs\b", r"\bkubernetes\b", r"\bhelm\b"],
        "unit and integration testing": [r"\bjunit\b", r"\bmockito\b", r"\btestcontainers\b"]
    }

    def __init__(self, resumes_dir: str = "resumes", cache_path: str = "data/resume_cache.json"):
        self.resumes_dir = resumes_dir
        self.cache_path = cache_path
        self._catalog: Dict[str, StructuredResume] = {}
        self._load_cache_and_catalog()

    def _compute_sha256(self, file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def _load_cache_and_catalog(self):
        """Load parsed resumes from cache file and parse any newly added/modified resumes."""
        cache_data = {}
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
            except Exception:
                cache_data = {}

        if not os.path.exists(self.resumes_dir):
            os.makedirs(self.resumes_dir, exist_ok=True)
            return

        updated_cache = False
        seen_hashes = set()

        for filename in sorted(os.listdir(self.resumes_dir)):
            if filename.startswith(".") or filename.startswith("~$"):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".docx", ".pdf", ".txt"):
                continue

            file_path = os.path.join(self.resumes_dir, filename)
            if not os.path.isfile(file_path):
                continue

            f_hash = self._compute_sha256(file_path)
            # Remove exact duplicate files
            if f_hash in seen_hashes:
                continue
            seen_hashes.add(f_hash)

            # Check cache by hash
            if f_hash in cache_data:
                cached_dict = cache_data[f_hash]
                cached_dict["file_path"] = file_path
                res_obj = StructuredResume.from_dict(cached_dict)
                # Do not overwrite a valid parsed resume with an empty/failed one
                if res_obj.resume_id in self._catalog:
                    existing = self._catalog[res_obj.resume_id]
                    if len(existing.passages) > 0 and len(res_obj.passages) == 0:
                        continue
                    if existing.file_path.endswith(".docx") and res_obj.file_path.endswith(".pdf"):
                        continue
                self._catalog[res_obj.resume_id] = res_obj
            else:
                # Parse fresh
                res_obj = self._parse_resume(file_path, f_hash)
                if res_obj.resume_id in self._catalog:
                    existing = self._catalog[res_obj.resume_id]
                    if len(existing.passages) > 0 and len(res_obj.passages) == 0:
                        continue
                    if existing.file_path.endswith(".docx") and res_obj.file_path.endswith(".pdf"):
                        continue
                self._catalog[res_obj.resume_id] = res_obj
                cache_data[f_hash] = res_obj.to_dict()
                updated_cache = True

        if updated_cache:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)

    def _parse_resume(self, file_path: str, file_hash: str) -> StructuredResume:
        """Parse a single DOCX/PDF resume into StructuredResume."""
        filename = os.path.basename(file_path)
        resume_id = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1].lower()

        paragraphs = []
        if ext == ".docx":
            try:
                with zipfile.ZipFile(file_path) as docx_zip:
                    xml_content = docx_zip.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    for p in tree.iterfind(".//w:p", ns):
                        texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                        if texts:
                            p_clean = "".join(texts).strip()
                            if p_clean:
                                paragraphs.append(p_clean)
            except Exception as e:
                return StructuredResume(
                    resume_id=resume_id,
                    file_path=file_path,
                    file_hash=file_hash,
                    focus_title="",
                    passages=[],
                    skills_summary=set(),
                    parsing_status="review_needed",
                    parsing_error=f"DOCX extraction failed: {e}"
                )
        elif ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                for page_idx, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    for line in page_text.splitlines():
                        if line.strip():
                            paragraphs.append(line.strip())
            except Exception as e:
                return StructuredResume(
                    resume_id=resume_id,
                    file_path=file_path,
                    file_hash=file_hash,
                    focus_title="",
                    passages=[],
                    skills_summary=set(),
                    parsing_status="review_needed",
                    parsing_error=f"PDF extraction failed: {e}"
                )
        elif ext == ".txt":
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    paragraphs = [l.strip() for l in f.splitlines() if l.strip()]
            except Exception as e:
                return StructuredResume(
                    resume_id=resume_id,
                    file_path=file_path,
                    file_hash=file_hash,
                    focus_title="",
                    passages=[],
                    skills_summary=set(),
                    parsing_status="review_needed",
                    parsing_error=f"TXT extraction failed: {e}"
                )

        if not paragraphs:
            return StructuredResume(
                resume_id=resume_id,
                file_path=file_path,
                file_hash=file_hash,
                focus_title="",
                passages=[],
                skills_summary=set(),
                parsing_status="review_needed",
                parsing_error="Document contains zero readable text"
            )

        return self._process_paragraphs(paragraphs, resume_id, file_path, file_hash)

    def parse_resume_bytes(self, docx_bytes: bytes, resume_id: str = "tailored_resume") -> StructuredResume:
        """Parse an in-memory DOCX byte stream into StructuredResume without writing to disk."""
        paragraphs = []
        try:
            with zipfile.ZipFile(io.BytesIO(docx_bytes)) as docx_zip:
                xml_content = docx_zip.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                for p in tree.iterfind(".//w:p", ns):
                    texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                    if texts:
                        p_clean = "".join(texts).strip()
                        if p_clean:
                            paragraphs.append(p_clean)
        except Exception as e:
            return StructuredResume(
                resume_id=resume_id,
                file_path="",
                file_hash="",
                focus_title="",
                passages=[],
                skills_summary=set(),
                parsing_status="review_needed",
                parsing_error=f"DOCX bytes extraction failed: {e}"
            )

        f_hash = hashlib.sha256(docx_bytes).hexdigest()
        return self._process_paragraphs(paragraphs, resume_id, "", f_hash)

    def _process_paragraphs(
        self, paragraphs: List[str], resume_id: str, file_path: str, file_hash: str
    ) -> StructuredResume:
        """Scan extracted paragraphs into structured sections and traceable evidence passages."""
        if not paragraphs:
            return StructuredResume(
                resume_id=resume_id,
                file_path=file_path,
                file_hash=file_hash,
                focus_title="",
                passages=[],
                skills_summary=set(),
                parsing_status="review_needed",
                parsing_error="Document contains zero readable text"
            )

        # Detect Focus Title (usually paragraph 1 or 0)
        focus_title = paragraphs[1] if len(paragraphs) > 1 and len(paragraphs[1]) < 60 else paragraphs[0]

        # Scan paragraphs into sections and passages
        passages: List[EvidencePassage] = []
        skills_summary: Set[str] = set()

        current_section = "header"
        current_employer = ""
        current_role = ""
        current_start = ""
        current_end = ""

        # Identify experience block boundaries
        date_pattern = re.compile(
            r'([A-Za-z0-9\s&,.\'-]+)\s*\|\s*([A-Za-z0-9\s&/.-]+)\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})\s*(\d{4})?\s*-\s*(Present|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})',
            re.IGNORECASE
        )

        for p_idx, text in enumerate(paragraphs):
            text_lower = text.lower()

            # Section detection
            if "professional experience" in text_lower or "employment history" in text_lower or "work experience" in text_lower:
                current_section = "professional_experience"
                continue
            elif "technical skills" in text_lower or "skills:" in text_lower:
                current_section = "technical_skills"
                continue
            elif "education" in text_lower or "certifications" in text_lower:
                current_section = "education"
                continue

            # Check if this paragraph is an Employer header
            m = date_pattern.search(text)
            if m and "|" in text:
                current_section = "professional_experience"
                current_employer = m.group(1).strip()
                current_role = m.group(2).strip()
                current_start = f"{m.group(3)} {m.group(4) or ''}".strip()
                current_end = m.group(5).strip()
                continue

            # Detect technologies in this passage
            passage_techs = self._detect_technologies(text)
            passage_caps = self._detect_capabilities(text)

            if current_section == "technical_skills":
                for t in passage_techs:
                    skills_summary.add(t)
                passages.append(EvidencePassage(
                    resume_id=resume_id,
                    section="technical_skills",
                    text=text,
                    technologies=passage_techs,
                    capabilities=passage_caps,
                    source={"paragraph": p_idx}
                ))

            elif current_section == "professional_experience":
                for t in passage_techs:
                    skills_summary.add(t)

                # Skip header labels like "Selected Contributions:" or "Project: ..."
                if len(text.split()) >= 4:
                    passages.append(EvidencePassage(
                        resume_id=resume_id,
                        section="professional_experience",
                        text=text,
                        employer=current_employer,
                        role=current_role,
                        employment_start=current_start,
                        employment_end=current_end,
                        technologies=passage_techs,
                        capabilities=passage_caps,
                        source={"paragraph": p_idx}
                    ))
            elif current_section == "header" and p_idx > 2:
                # Summary paragraph
                for t in passage_techs:
                    skills_summary.add(t)
                passages.append(EvidencePassage(
                    resume_id=resume_id,
                    section="summary",
                    text=text,
                    technologies=passage_techs,
                    capabilities=passage_caps,
                    source={"paragraph": p_idx}
                ))

        return StructuredResume(
            resume_id=resume_id,
            file_path=file_path,
            file_hash=file_hash,
            focus_title=focus_title,
            passages=passages,
            skills_summary=skills_summary,
            parsing_status="valid"
        )

    def _detect_technologies(self, text: str) -> List[str]:
        """Identify recognized technologies from ontology in text."""
        detected = []
        text_lower = " " + text.lower() + " "
        for alias, canonical in TechOntology.ALIASES.items():
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, text_lower):
                if canonical not in detected:
                    detected.append(canonical)
        return detected

    def _detect_capabilities(self, text: str) -> List[str]:
        """Identify action capabilities from text."""
        detected = []
        text_lower = text.lower()
        for cap_name, patterns in self.COMMON_CAPABILITIES.items():
            if any(re.search(p, text_lower) for p in patterns):
                detected.append(cap_name)
        return detected

    def get_all_resumes(self) -> List[StructuredResume]:
        """Return all valid parsed resumes."""
        return [r for r in self._catalog.values() if r.parsing_status == "valid"]

    def get_resume(self, resume_id: str) -> Optional[StructuredResume]:
        """Get structured resume by ID."""
        return self._catalog.get(resume_id)
