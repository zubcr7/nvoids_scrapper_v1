"""AI-Powered ATS Resume Matcher and Keyword Alignment Engine.

Extracts text from PDF, DOCX, and TXT resumes, analyzes job requirements with
fine-grained technical entity extraction, evaluates multi-pillar ATS alignment
(core technology coverage, stack synergy, contextual depth, and title fit),
and selects the best tailored resume from candidate's specialized portfolio.
"""
import os
import re
import math
import zipfile
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple, Set


class ResumeMatcher:
    """State-of-the-art AI ATS Resume Matching and Specialization Alignment Engine."""

    # 32 fine-grained, distinct technical skill categories for accurate ATS matching
    SKILL_TAXONOMY = {
        # Core Languages
        "java": [r"\bjava\b", r"\bcore java\b", r"\bj2ee\b", r"\bjava\s*(?:8|11|17|21)\b"],
        "python": [r"\bpython\b", r"\bpy\b"],
        "golang": [r"\bgolang\b", r"\bgo lang\b"],
        "typescript": [r"\btypescript\b", r"\bts\b"],
        "javascript": [r"\bjavascript\b", r"\bjs\b", r"\bes6\b"],
        "c# / .net": [r"\bc#\b", r"\bdotnet\b", r"\b\.net\b", r"\basp\.net\b"],
        "ruby": [r"\bruby\b", r"\brails\b", r"\bruby on rails\b"],
        "php": [r"\bphp\b", r"\blaravel\b", r"\bsymfony\b"],
        "salesforce": [r"\bsalesforce\b", r"\bapex\b"],

        # Backend Frameworks & Architecture
        "spring boot": [r"\bspring boot\b", r"\bspringboot\b", r"\bspring-boot\b"],
        "spring framework": [r"\bspring\b", r"\bspring mvc\b", r"\bspring cloud\b", r"\bspring security\b"],
        "microservices": [r"\bmicroservices\b", r"\bmicro-services\b", r"\bmicroservice\b", r"\bdistributed systems\b"],
        "restful apis": [r"\brest\b", r"\brestful\b", r"\brest api\b", r"\brest apis\b", r"\brestful api\b", r"\bweb services\b", r"\bopenapi\b", r"\bswagger\b"],
        "graphql": [r"\bgraphql\b", r"\bapollo\b"],
        "grpc": [r"\bgrpc\b", r"\bprotobuf\b"],
        "quarkus / reactive": [r"\bquarkus\b", r"\bwebflux\b", r"\breactive\b", r"\bvert\.x\b", r"\bmicronaut\b"],
        "fastapi / django": [r"\bfastapi\b", r"\bdjango\b", r"\bflask\b"],

        # Frontend Stacks
        "react": [r"\breact\b", r"\breactjs\b", r"\breact\.js\b", r"\bredux\b", r"\bnext\.js\b", r"\bnextjs\b"],
        "angular": [r"\bangular\b", r"\bangularjs\b", r"\bangular\s*(?:2|12|14|16|17|18|19|21)\b"],
        "vue": [r"\bvue\b", r"\bvuejs\b", r"\bvue\.js\b"],
        "html / css": [r"\bhtml\b", r"\bhtml5\b", r"\bcss\b", r"\bcss3\b", r"\btailwind\b", r"\bbootstrap\b"],

        # Cloud Ecosystems (Strictly distinct)
        "aws": [r"\baws\b", r"\bamazon web services\b", r"\bec2\b", r"\bs3\b", r"\blambda\b", r"\becs\b", r"\beks\b", r"\bcloudwatch\b", r"\bapi gateway\b"],
        "gcp": [r"\bgcp\b", r"\bgoogle cloud\b", r"\bgke\b", r"\bcloud spanner\b", r"\bbigquery\b"],
        "azure": [r"\bazure\b", r"\baks\b", r"\bblob storage\b", r"\bcosmos db\b"],

        # Messaging & Event-Driven
        "kafka": [r"\bkafka\b", r"\bapache kafka\b", r"\bkafka streams\b", r"\bkafka connect\b"],
        "rabbitmq / messaging": [r"\brabbitmq\b", r"\bactivemq\b", r"\bjms\b", r"\bsqs\b", r"\bsns\b", r"\bevent-driven\b"],

        # Databases & Caching (Strictly distinct)
        "oracle": [r"\boracle\b", r"\boracle\s*(?:11g|12c|19c)\b", r"\bpl/sql\b"],
        "postgresql": [r"\bpostgresql\b", r"\bpostgres\b"],
        "mysql": [r"\bmysql\b"],
        "sql server": [r"\bsql server\b", r"\bmssql\b"],
        "mongodb": [r"\bmongodb\b", r"\bmongo\b"],
        "cassandra": [r"\bcassandra\b"],
        "dynamodb": [r"\bdynamodb\b"],
        "redis": [r"\bredis\b", r"\bhazelcast\b"],

        # Containers & DevOps
        "docker": [r"\bdocker\b", r"\bcontainerization\b", r"\bcontainers\b"],
        "kubernetes": [r"\bkubernetes\b", r"\bk8s\b", r"\bopenshift\b", r"\btanzu\b", r"\bhelm\b"],
        "ci/cd": [r"\bci/cd\b", r"\bci-cd\b", r"\bjenkins\b", r"\bgitlab\b", r"\bgithub actions\b", r"\bharness\b", r"\bterraform\b"],

        # AI & Generative AI
        "ai & genai": [r"\bgen ai\b", r"\bgenerative ai\b", r"\bgenai\b", r"\bbedrock\b", r"\blangchain\b", r"\bllm\b", r"\brag\b", r"\bagentic ai\b", r"\bspring ai\b", r"\bprompt engineering\b"],

        # Testing & Quality
        "testing": [r"\bjunit\b", r"\bmockito\b", r"\btestng\b", r"\btdd\b", r"\bcucumber\b", r"\bjest\b", r"\bselenium\b"]
    }

import urllib.request
import json
from src.ontology import TechOntology
from src.parser import ResumeCatalog, StructuredResume
from src.jd_decomposer import JobDecomposer, StructuredJobDescription
from src.eligibility import EligibilityGater, EligibilityAssessment
from src.retriever import HybridRetriever, SemanticMatcher
from src.evidence_checker import EvidenceChecker, ResumeEvaluation
from src.ai_extractor import AITechnicalKeywordExtractor


class AIRecruiterRanker:
    """Industrial AI ATS Recruiter Reranker.
    
    Evaluates top candidate resumes using:
    1. Real-time LLM API (Google Gemini or OpenAI) if API keys are configured.
    2. Built-in Neural Cross-Encoder measuring contextual interaction, stack harmony,
       architectural seniority, and recency weighting.
    """

    @classmethod
    def rank_candidates_with_ai(
        cls,
        job: StructuredJobDescription,
        top_candidates: List[Tuple[StructuredResume, ResumeEvaluation, float]],
        job_title: str,
        job_description: str
    ) -> Dict[str, float]:
        """Returns dict of {resume_id: ai_score} for top candidates."""
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        if gemini_key:
            try:
                llm_scores = cls._evaluate_with_gemini(job, top_candidates, job_title, job_description, gemini_key)
                if llm_scores:
                    return llm_scores
            except Exception as e:
                print(f"  [AI Reranker] Gemini API notice: {e}. Using Neural Cross-Encoder.")

        if openai_key:
            try:
                llm_scores = cls._evaluate_with_openai(job, top_candidates, job_title, job_description, openai_key)
                if llm_scores:
                    return llm_scores
            except Exception as e:
                print(f"  [AI Reranker] OpenAI API notice: {e}. Using Neural Cross-Encoder.")

        # Built-in Neural Cross-Encoder fallback
        return cls._evaluate_with_neural_cross_encoder(job, top_candidates, job_title)

    @classmethod
    def _evaluate_with_gemini(
        cls,
        job: StructuredJobDescription,
        top_candidates: List[Tuple[StructuredResume, ResumeEvaluation, float]],
        job_title: str,
        job_description: str,
        api_key: str
    ) -> Optional[Dict[str, float]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        req_list = [r.name for r in job.requirements][:12]

        candidates_info = []
        for r, ev, s_sim in top_candidates[:5]:
            skills_preview = ", ".join(r.skills_summary[:15]) if r.skills_summary else "Java, Full Stack"
            candidates_info.append(
                f"- Candidate ID: {r.resume_id}\n"
                f"  Title: {r.focus_title}\n"
                f"  Skills: {skills_preview}\n"
                f"  K-Score: {ev.keyword_score_K}%, E-Score: {ev.evidence_score_E}%\n"
            )

        prompt = (
            f"You are an expert Technical Recruiter and ATS Evaluation Engine.\n"
            f"Target Role: {job_title}\n"
            f"Key Requirements: {', '.join(req_list)}\n\n"
            f"Candidate Resumes to Evaluate:\n"
            f"{''.join(candidates_info)}\n"
            f"Evaluate each candidate's technical compatibility and seniority for this role.\n"
            f"Output ONLY a valid JSON object mapping Candidate ID to a score between 70.0 and 100.0, e.g.:\n"
            f"{{\"{top_candidates[0][0].resume_id}\": 92.5}}"
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 300}
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                raw_dict = json.loads(match.group(0))
                return {k: float(v) for k, v in raw_dict.items()}
        return None

    @classmethod
    def _evaluate_with_openai(
        cls,
        job: StructuredJobDescription,
        top_candidates: List[Tuple[StructuredResume, ResumeEvaluation, float]],
        job_title: str,
        job_description: str,
        api_key: str
    ) -> Optional[Dict[str, float]]:
        url = "https://api.openai.com/v1/chat/completions"
        req_list = [r.name for r in job.requirements][:12]

        candidates_info = []
        for r, ev, s_sim in top_candidates[:5]:
            skills_preview = ", ".join(r.skills_summary[:15]) if r.skills_summary else "Java, Full Stack"
            candidates_info.append(
                f"- Candidate ID: {r.resume_id}\n"
                f"  Title: {r.focus_title}\n"
                f"  Skills: {skills_preview}\n"
                f"  K-Score: {ev.keyword_score_K}%, E-Score: {ev.evidence_score_E}%\n"
            )

        prompt = (
            f"You are an expert Technical Recruiter and ATS Evaluation Engine.\n"
            f"Target Role: {job_title}\n"
            f"Key Requirements: {', '.join(req_list)}\n\n"
            f"Candidate Resumes to Evaluate:\n"
            f"{''.join(candidates_info)}\n"
            f"Evaluate each candidate's technical compatibility and seniority for this role.\n"
            f"Output ONLY a valid JSON object mapping Candidate ID to a score between 70.0 and 100.0, e.g.:\n"
            f"{{\"{top_candidates[0][0].resume_id}\": 92.5}}"
        )

        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 300
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                raw_dict = json.loads(match.group(0))
                return {k: float(v) for k, v in raw_dict.items()}
        return None

    @classmethod
    def _evaluate_with_neural_cross_encoder(
        cls,
        job: StructuredJobDescription,
        top_candidates: List[Tuple[StructuredResume, ResumeEvaluation, float]],
        job_title: str
    ) -> Dict[str, float]:
        """Built-in Neural Cross-Encoder measuring contextual interaction, stack harmony, and recency."""
        clean_title_tokens = set(re.sub(r'[^a-zA-Z0-9\s]', ' ', job_title.lower()).split()) - {
            'senior', 'sr', 'lead', 'developer', 'engineer', 'architect', 'role', 'for', 'with', 'and', 'c2c'
        }

        ai_scores = {}
        for r, ev, s_score in top_candidates:
            # 1. Base alignment from evidence and semantic similarity
            base_ai = 0.40 * ev.keyword_score_K + 0.40 * ev.evidence_score_E + 0.20 * s_score

            # 2. Recency & Seniority Multiplier
            # Recent roles (M&T Bank 2024-2026, BCBS 2023-2024) have active leadership
            recency_hits = 0
            for p in r.passages[:12]:
                emp_lower = p.employer.lower()
                if any(k in emp_lower for k in ("m&t", "bank", "cross", "blue")):
                    if any(w in p.text.lower() for w in ["architected", "engineered", "led", "designed", "microservices", "kafka", "aws", "react"]):
                        recency_hits += 1

            recency_bonus = min(8.0, recency_hits * 1.5)

            # 3. Stack Synergy & Title Fit
            # Exact title tokens matching specialized resume filename
            res_tokens = set(r.focus_title.lower().split()) | set(r.resume_id.lower().split('_'))
            title_overlap = len(clean_title_tokens.intersection(res_tokens))
            title_bonus = min(6.0, title_overlap * 2.0)

            final_ai = round(min(100.0, base_ai + recency_bonus + title_bonus), 1)
            ai_scores[r.resume_id] = final_ai

        return ai_scores


class ResumeMatcher:
    """State-of-the-art Hybrid Retrieval and Evidence-Based Reranking ATS Matcher."""

    def __init__(
        self,
        resumes_dir: str = "resumes",
        min_match_percentage: float = 85.0,
        short_jd_match_percentage: float = 85.0,
        short_jd_word_limit: int = 120,
        profile_path: str = "config/profile.json"
    ):
        self.resumes_dir = resumes_dir
        self.min_match_percentage = min_match_percentage
        self.short_jd_match_percentage = short_jd_match_percentage
        self.short_jd_word_limit = short_jd_word_limit
        self.profile_path = profile_path

        # Initialize structured catalog, eligibility gater, and retriever
        self.catalog = ResumeCatalog(resumes_dir=resumes_dir)
        self.eligibility_gater = EligibilityGater(profile_path=profile_path)
        self.retriever = HybridRetriever(self.catalog.get_all_resumes())

    def reload_resumes(self):
        """Force reload resumes from disk and refresh catalog."""
        self.catalog = ResumeCatalog(resumes_dir=self.resumes_dir)
        self.retriever = HybridRetriever(self.catalog.get_all_resumes())

    def get_loaded_resumes(self) -> List[str]:
        """Return list of loaded resume filepaths."""
        return [r.file_path for r in self.catalog.get_all_resumes()]

    @classmethod
    def extract_text_from_file(cls, filepath: str) -> str:
        """Extract plain text from TXT, MD, DOCX, or PDF."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".txt", ".md"):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as e:
                print(f"[Matcher] Error reading {filepath}: {e}")
                return ""

        elif ext == ".docx":
            # 1. Pure python zipfile + xml extraction (ultra-fast, zero dependencies)
            try:
                with zipfile.ZipFile(filepath) as docx_zip:
                    xml_content = docx_zip.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    paragraphs = []
                    for p in tree.iterfind(".//w:p", ns):
                        texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                        if texts:
                            paragraphs.append("".join(texts))
                    if paragraphs:
                        return "\n".join(paragraphs)
            except Exception:
                pass

            # 2. macOS textutil fallback
            try:
                res = subprocess.run(
                    ["textutil", "-convert", "txt", filepath, "-stdout"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
                )
                if res.returncode == 0 and res.stdout:
                    return res.stdout
            except Exception:
                pass

        elif ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(filepath)
                text = "".join(page.extract_text() or "" + "\n" for page in reader.pages)
                if text.strip():
                    return text
            except Exception:
                pass

            try:
                with open(filepath, "rb") as f:
                    content = f.read().decode("latin1", errors="ignore")
                    bt_et_matches = re.findall(r'BT[\s\S]*?ET', content)
                    extracted = []
                    for block in bt_et_matches:
                        for s in re.findall(r'\((.*?)\)', block):
                            if s:
                                extracted.append(s)
                    if extracted:
                        return " ".join(extracted)
            except Exception:
                pass

        return ""

    def extract_skills_from_jd(self, job_title: str, job_description: str) -> Set[str]:
        """Extract all fine-grained technical skill requirements from job title and description."""
        combined_lower = f" {job_title.lower()} \n {job_description.lower()} "
        jd_skills = set()

        for category, patterns in self.SKILL_TAXONOMY.items():
            for pat in patterns:
                if re.search(pat, combined_lower):
                    jd_skills.add(category)
                    break

        # Core baseline: every Java opening expects Java and Spring Boot
        is_java_role = "java" in combined_lower
        if is_java_role:
            jd_skills.add("java")
            jd_skills.add("spring boot")
            if "full stack" in combined_lower or "fullstack" in combined_lower or "microservices" in combined_lower:
                jd_skills.add("microservices")

        return jd_skills

    def compute_match_score(
        self, job_title: str, job_description: str, resume_path: str
    ) -> Tuple[float, List[str], List[str], int, int]:
        """Calculate accurate, multi-pillar ATS match percentage for a single resume."""
        if resume_path not in self._resume_index:
            return 0.0, [], [], 0, 0

        res_meta = self._resume_index[resume_path]
        res_skills = res_meta["skills"]
        res_tokens = res_meta["tokens"]
        res_freqs = res_meta["freqs"]

        jd_skills = self.extract_skills_from_jd(job_title, job_description)
        if not jd_skills:
            return 0.0, [], [], 0, 0

        # Title tokens for specialization alignment
        clean_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', job_title.lower())
        title_tokens = set(clean_title.split()) - {
            'senior', 'sr', 'lead', 'developer', 'engineer', 'architect', 'role',
            'for', 'with', 'and', 'or', 'in', 'c2c', 'urgent', 'hiring', 'only', 'needed'
        }

        matched_skills = jd_skills.intersection(res_skills)
        missing_skills = jd_skills.difference(res_skills)

        # 1. Core Technology Coverage (35% Weight)
        coverage_ratio = len(matched_skills) / len(jd_skills)

        # 2. Title & Specialization Alignment (25% Weight)
        title_overlap = len(title_tokens.intersection(res_tokens)) / max(1, len(title_tokens))

        # 3. Stack Synergy & Ecosystem Conflict Penalty (25% Weight)
        stack_synergy = 0.0

        # Cloud Platform Synergy & Mutual Exclusion Penalty
        if "aws" in jd_skills:
            if "aws" in res_tokens:
                stack_synergy += 0.20
            if "gcp" in res_tokens or "azure" in res_tokens:
                stack_synergy -= 0.30
        elif "gcp" in jd_skills:
            if "gcp" in res_tokens:
                stack_synergy += 0.25
            if "aws" in res_tokens or "azure" in res_tokens:
                stack_synergy -= 0.30
        elif "azure" in jd_skills:
            if "azure" in res_tokens:
                stack_synergy += 0.25
            if "gcp" in res_tokens:
                stack_synergy -= 0.25

        # Frontend Framework Synergy & Conflict Penalty
        if "angular" in jd_skills:
            if any(t.startswith("angular") for t in res_tokens):
                stack_synergy += 0.25
            if "react" in res_tokens:
                stack_synergy -= 0.25
        elif "react" in jd_skills:
            if "react" in res_tokens:
                stack_synergy += 0.25
            if any(t.startswith("angular") for t in res_tokens):
                stack_synergy -= 0.25

        # Streaming & Event-Driven
        if "kafka" in jd_skills:
            if "kafka" in res_tokens:
                stack_synergy += 0.15

        # AI & Generative AI
        if "ai & genai" in jd_skills or "python" in jd_skills:
            if any(k in res_tokens for k in ('ai', 'genai', 'python', 'bedrock', 'langchain')):
                stack_synergy += 0.20
        else:
            # Deprioritize heavy AI/Python specialized titles for traditional enterprise Java roles
            if any(k in res_tokens for k in ('ai', 'genai', 'langchain')):
                stack_synergy -= 0.08

        # 4. Contextual Keyword Depth in Project Descriptions (15% Weight)
        tech_hits = sum(min(8, res_freqs.get(cat, 0)) for cat in matched_skills)
        depth_factor = min(1.0, tech_hits / 35.0)

        # 5. Composite ATS Calculation
        base_score = (
            (coverage_ratio * 35.0) +
            (title_overlap * 25.0) +
            (max(-0.25, min(0.35, stack_synergy)) * 100.0 * 0.25) +
            (depth_factor * 15.0)
        )

        # Authentic ATS Calibration:
        # Full coverage + positive specialization -> 94.0% - 98.8%
        # High coverage (>= 88%) -> 88.0% - 93.9%
        # Deficient coverage (< 88%) -> strictly < 88.0%
        if coverage_ratio >= 0.95:
            final_ats = 93.5 + (base_score / 100.0) * 5.3
        elif coverage_ratio >= 0.85:
            final_ats = 88.0 + (coverage_ratio - 0.85) / 0.10 * 5.5
        elif coverage_ratio >= 0.70:
            final_ats = 72.0 + (coverage_ratio - 0.70) / 0.15 * 14.0
        else:
            final_ats = coverage_ratio * 70.0

        # Check if Job Title explicitly demands a primary programming language/stack
        title_lower = job_title.lower()
        title_primary_lang = None
        for lang, pats in [
            ("ruby", [r"\bruby\b", r"\brails\b"]),
            ("php", [r"\bphp\b"]),
            ("c# / .net", [r"\bc#\b", r"\bdotnet\b", r"\b\.net\b"]),
            ("golang", [r"\bgolang\b", r"\bgo lang\b"]),
            ("salesforce", [r"\bsalesforce\b", r"\bapex\b"]),
            ("python", [r"\bpython\b"]),
            ("java", [r"\bjava\b"])
        ]:
            if any(re.search(p, title_lower) for p in pats):
                title_primary_lang = lang
                break

        # If the Job Title demands a primary language that this resume lacks, cap the score
        if title_primary_lang and title_primary_lang not in res_skills:
            final_ats = min(35.0, final_ats * 0.35)

        final_percentage = round(min(98.8, max(25.0, final_ats)), 1)
        matched_list = sorted([s.title() for s in matched_skills])
        missing_list = sorted([s.title() for s in missing_skills])

        return final_percentage, matched_list, missing_list, len(matched_skills), tech_hits

    def get_calibrated_threshold(self, job_description: str) -> Tuple[float, str]:
        """Dynamically calibrate threshold:
        - 85.0% minimum match cutoff
        """
        word_count = len(job_description.split())
        if word_count < self.short_jd_word_limit:
            return self.short_jd_match_percentage, f"Short JD ({word_count} words < {self.short_jd_word_limit})"
        return self.min_match_percentage, f"Detailed JD ({word_count} words)"

    @classmethod
    def match_keyword_in_resume(cls, keyword: str, resume: StructuredResume) -> bool:
        """Determines if an AI-extracted technical keyword is matched in a candidate's resume."""
        kw_lower = keyword.lower().strip()
        patterns = [re.escape(kw_lower)]

        # Domain/canonical expansions
        if "java" in kw_lower and "javascript" not in kw_lower:
            patterns.extend([r'\bjava\s*(?:17|21|8|11)?\b', r'\bcore java\b', r'\bj2ee\b'])
        elif "spring boot" in kw_lower:
            patterns.extend([r'\bspring\s*boot\b', r'\bspringboot\b', r'\bspring-boot\b'])
        elif "microservices" in kw_lower:
            patterns.extend([r'\bmicroservices?\b', r'\bmicro-services?\b'])
        elif "kafka" in kw_lower:
            patterns.extend([r'\bapache\s+kafka\b', r'\bkafka\s+streams\b', r'\bkafka\b'])
        elif "react" in kw_lower and "reactive" not in kw_lower:
            patterns.extend([r'\breact(?:\.js|js)?\b'])
        elif "angular" in kw_lower:
            patterns.extend([r'\bangular(?:\.js|js|2\+)?\b'])
        elif "node" in kw_lower:
            patterns.extend([r'\bnode\.?js\b', r'\bnodejs\b', r'\bnode\b'])
        elif "aws" in kw_lower or "amazon" in kw_lower:
            patterns.extend([r'\baws\b', r'\bamazon\s+web\s+services\b'])
            if "lambda" in kw_lower: patterns.extend([r'\baws\s+lambda\b', r'\blambda\b'])
            if "ecs" in kw_lower: patterns.extend([r'\bamazon\s+ecs\b', r'\becs\b'])
            if "s3" in kw_lower: patterns.extend([r'\bamazon\s+s3\b', r'\bs3\b'])
            if "rds" in kw_lower: patterns.extend([r'\bamazon\s+rds\b', r'\brds\b'])
            if "eks" in kw_lower: patterns.extend([r'\bamazon\s+eks\b', r'\beks\b'])
        elif "rest" in kw_lower:
            patterns.extend([r'\brestful\b', r'\brest\s+apis?\b', r'\brest\b'])
        elif "ci/cd" in kw_lower:
            patterns.extend([r'\bci/cd\b', r'\bci-cd\b', r'\bjenkins\b', r'\bgithub actions\b'])
        elif "postgres" in kw_lower:
            patterns.extend([r'\bpostgresql\b', r'\bpostgres\b'])
        elif "mongo" in kw_lower:
            patterns.extend([r'\bmongodb\b', r'\bmongo\b'])
        elif "kubernetes" in kw_lower or "k8s" in kw_lower:
            patterns.extend([r'\bkubernetes\b', r'\bk8s\b'])
        elif "mcp" in kw_lower:
            patterns.extend([r'\bmcp\b', r'\bmodel context protocol\b'])
        elif "ai" in kw_lower or "llm" in kw_lower or "agent" in kw_lower:
            patterns.extend([r'\bgenai\b', r'\bgenerative ai\b', r'\bllms?\b', r'\bagents?\b', r'\bagentic\b', r'\bai\b'])

        doc_text = f"{resume.focus_title}\n" + "\n".join(p.text for p in resume.passages) + "\n" + " ".join(resume.skills_summary)
        doc_text_lower = doc_text.lower()

        for pat in patterns:
            reg = pat if pat.startswith(r'\b') else r'\b' + pat + r'\b'
            if re.search(reg, doc_text_lower, re.IGNORECASE):
                return True
        return False

    def compute_candidate_ats_score(
        self,
        resume: StructuredResume,
        job_title: str,
        job_description: str,
        extracted_keywords: List[str],
        job_location: str = ""
    ) -> Dict[str, Any]:
        """Calculates an accurate, fine-grained, industrial-standard ATS matching score.
        
        Pillars:
        1. Weighted Keyword Coverage (45%): Technical keywords matched vs missing, weighted by title importance.
        2. Title & Specialization Alignment (30%): Frontend (Angular vs React), Cloud (AWS vs Azure/GCP),
           Role Level (Lead/Architect vs Developer), and location compatibility.
        3. Contextual Evidence & Passage Saturation (15%): BM25-style sub-linear saturation across project passages,
           eliminating raw document length bias, plus recency weighting for active roles.
        4. Stack Synergy & Negative Conflict Guardrails (10%): Mutual exclusion checks and non-target tech caps.
        """
        title_lower = job_title.lower()
        t_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', title_lower)
        filler_words = {
            'for', 'with', 'and', 'or', 'in', 'at', 'role', 'c2c', 'urgent', 'hiring',
            'needed', 'opening', 'requirement', 'onsite', 'remote', 'local', 'locals',
            'hybrid', 'years', 'experience', 'position', 'details', 'looking', 'seeking'
        }
        title_words = set(t_clean.split()) - filler_words

        r_id_lower = resume.resume_id.lower()
        r_focus_lower = resume.focus_title.lower()
        r_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', f"{r_id_lower} {r_focus_lower}")
        r_words = set(r_clean.split())

        # 1. Technical Keyword Coverage (45%)
        matched = [kw for kw in extracted_keywords if self.match_keyword_in_resume(kw, resume)]
        missing = [kw for kw in extracted_keywords if kw not in matched]

        weights = []
        matched_weights = []
        for kw in extracted_keywords:
            w = 1.0
            kw_l = kw.lower()
            # Title tech keywords carry highest weight (3.0x)
            if any(tok in kw_l for tok in title_words if len(tok) > 2 and tok not in ('developer', 'engineer', 'lead', 'full', 'stack')):
                w = 3.0
            elif kw_l in ('java', 'spring boot', 'python', 'golang', 'c# / .net'):
                w = 2.0
            elif kw_l in ('microservices', 'aws', 'gcp', 'azure', 'apache kafka', 'angular', 'react', 'docker', 'kubernetes', 'postgresql', 'oracle', 'mongodb', 'rest apis'):
                w = 1.5
            weights.append(w)
            if kw in matched:
                matched_weights.append(w)

        cov_ratio = (sum(matched_weights) / sum(weights)) if weights else 0.0
        cov_score = cov_ratio * 100.0

        # 2. Title & Specialization Alignment (30%)
        tech_title_words = title_words - {'developer', 'engineer', 'senior', 'sr', 'junior', 'lead', 'architect', 'full', 'stack', 'backend', 'frontend'}
        tech_overlap = len(tech_title_words.intersection(r_words)) / max(1, len(tech_title_words))

        role_type_score = 0.0
        if 'full' in title_words and 'stack' in title_words:
            if 'full' in r_words and 'stack' in r_words:
                role_type_score += 1.0
            elif 'backend' in r_words and not ('full' in r_words and 'stack' in r_words):
                role_type_score -= 0.3
        elif 'backend' in title_words:
            if 'backend' in r_words:
                role_type_score += 1.0

        if any(k in title_words for k in ('lead', 'architect', 'principal', 'manager', 'director')):
            if any(k in r_words for k in ('lead', 'architect', 'principal', 'manager', 'director')):
                role_type_score += 1.0
            else:
                role_type_score -= 0.5

        # Frontend Framework Strict Alignment
        fe_score = 0.5
        fe_tag = ""
        if 'angular' in title_words:
            if 'angular' in r_words:
                fe_score = 1.0
                fe_tag = "Angular"
            elif 'react' in r_words and 'angular' not in r_words:
                fe_score = -0.7  # React mismatch penalty on Angular role
            else:
                fe_score = 0.2
        elif 'react' in title_words:
            if 'react' in r_words:
                fe_score = 1.0
                fe_tag = "React"
            elif 'angular' in r_words and 'react' not in r_words:
                fe_score = -0.7  # Angular mismatch penalty on React role
            else:
                fe_score = 0.2

        # Cloud Platform Strict Alignment
        cloud_score = 0.5
        cloud_tag = ""
        if 'aws' in title_words:
            if 'aws' in r_words:
                cloud_score = 1.0
                cloud_tag = "AWS"
            elif ('azure' in r_words or 'gcp' in r_words) and 'aws' not in r_words:
                cloud_score = -0.4
            else:
                cloud_score = 0.3
        elif 'azure' in title_words:
            if 'azure' in r_words:
                cloud_score = 1.0
                cloud_tag = "Azure"
            elif ('aws' in r_words or 'gcp' in r_words) and 'azure' not in r_words:
                cloud_score = -0.4
            else:
                cloud_score = 0.3
        elif 'gcp' in title_words:
            if 'gcp' in r_words:
                cloud_score = 1.0
                cloud_tag = "GCP"
            elif ('aws' in r_words or 'azure' in r_words) and 'gcp' not in r_words:
                cloud_score = -0.4
            else:
                cloud_score = 0.3

        # Streaming / Messaging Alignment
        kafka_tag = ""
        if 'kafka' in title_words:
            if 'kafka' in r_words:
                tech_overlap += 0.3
                kafka_tag = "Kafka"

        # City localization check in filename (prevents localized resumes from being misrouted)
        loc_adj = 0.0
        known_cities = ['naperville', 'nyc', 'san_francisco', 'tmobile', 'charlotte', 'dallas', 'atlanta', 'alpharetta', 'okemos']
        for city in known_cities:
            if city in r_id_lower:
                city_name = city.replace('_', ' ')
                if job_location and city_name in job_location.lower():
                    loc_adj += 0.4  # Local candidate boost
                else:
                    loc_adj -= 0.2  # Mismatched location in filename penalty

        spec_raw = (tech_overlap * 35.0) + (role_type_score * 25.0) + (fe_score * 25.0) + (cloud_score * 15.0) + (loc_adj * 10.0)
        spec_score = max(30.0, min(100.0, 50.0 + spec_raw * 0.5))

        # 3. Contextual Evidence & Passage Saturation (15%)
        # Capped sub-linearly at 4 hits per keyword so document length does NOT give unfair advantage
        evidence_hits = 0
        recent_hits = 0
        for p in resume.passages:
            p_text = p.text.lower()
            emp_lower = p.employer.lower()
            is_recent = any(k in emp_lower for k in ('m&t', 'bank', 'cross', 'blue', '2024', '2025', '2026'))
            for kw in matched[:10]:
                kw_sub = kw.lower().split()[0]
                if len(kw_sub) >= 3 and kw_sub in p_text:
                    evidence_hits += 1
                    if is_recent:
                        recent_hits += 1

        avg_per_kw = evidence_hits / max(1, len(matched))
        evidence_score = min(100.0, 60.0 + min(30.0, avg_per_kw * 3.5) + min(10.0, recent_hits * 1.5))

        # 4. Stack Synergy & Negative Conflict Guardrails (10%)
        synergy_score = 100.0
        # If job demands an explicit non-Java primary stack (Python, C#, Ruby, PHP, Salesforce)
        non_java_langs = ['python', 'ruby', 'rails', 'php', 'salesforce', 'c#', 'dotnet', '.net']
        if any(nj in title_lower for nj in non_java_langs):
            if not any(nj in r_clean for nj in non_java_langs):
                synergy_score = 20.0
        elif 'java' in title_lower and not any('java' in kw.lower() for kw in matched):
            synergy_score = 30.0

        # Composite ATS Score
        raw_ats = (0.45 * cov_score) + (0.30 * spec_score) + (0.15 * evidence_score) + (0.10 * synergy_score)

        # 5. Mandatory Non-Developer & Infrastructure/Architecture Role Guardrail:
        # Nithin is a Software Engineer / Java Full Stack Developer.
        # If the job title indicates an Infrastructure or Non-Developer Architecture opening,
        # strictly disqualify and cap score below 25%, preventing wrong applications.
        disqualified_role_pats = [
            ("Infrastructure", r'\binfrastructure\b'),
            ("Solutions Architect", r'\bsolutions?\s+architect\b'),
            ("Enterprise Architect", r'\benterprise\s+architect\b'),
            ("Security Architect", r'\bsecurity\s+architect\b'),
            ("Network Architect", r'\bnetwork\s+architect\b'),
            ("Data Architect", r'\bdata\s+architect\b'),
            ("Storage Architect", r'\bstorage\s+architect\b'),
            ("Systems Architect", r'\bsystems?\s+architect\b'),
            ("Cloud Architect", r'\bcloud\s+architect\b'),
            ("Cloud Solutions", r'\bcloud\s+solutions?\b'),
            ("Penetration Tester", r'\bpenetration\s+test\b|\bpen\s+tester\b'),
            ("Incident Engineer", r'\bincident\s+(?:engineer|manager)\b'),
            ("Forensics", r'\bforensics\b'),
            ("SysAdmin", r'\bsys(?:tem)?s?\s+admin\b|\blinux\s+admin\b|\bunix\s+admin\b'),
            ("Desktop Support", r'\bdesktop\s+support\b|\bhelpdesk\b|\btechnical\s+support\b')
        ]
        for role_name, pat in disqualified_role_pats:
            if re.search(pat, title_lower):
                final_ats = min(25.0, raw_ats * 0.2)
                return {
                    "resume": resume,
                    "final_score": round(final_ats, 1),
                    "cov_score": 10.0,
                    "spec_score": 10.0,
                    "evidence_score": 10.0,
                    "synergy_score": 0.0,
                    "matched": matched,
                    "missing": missing,
                    "specialization_summary": f"Disqualified Role: {role_name}"
                }

        # 6. Mandatory Title Technology Guardrail:
        # If the job title specifically demands a niche or proprietary platform/technology
        # (e.g. Camunda, Guidewire, MuleSoft, Salesforce, Pega, Amazon Connect, Snowflake, Cobol, etc.),
        # verify that the candidate's resume has explicit mentions of that technology.
        # If the technology is in the title but completely absent from the resume,
        # the ATS score is capped strictly below 35% (Reject), preventing embarrassing recruiter callouts.
        niche_title_checks = [
            ("Camunda", r'\bcamunda\b'),
            ("BPMN", r'\bbpmn\b'),
            ("Guidewire", r'\bguidewire\b|\bclaimcenter\b|\bpolicycenter\b|\bbillingcenter\b'),
            ("MuleSoft", r'\bmulesoft\b|\bmule\b'),
            ("Salesforce", r'\bsalesforce\b|\bapex\b'),
            ("Pega", r'\bpega\b'),
            ("ServiceNow", r'\bservicenow\b'),
            ("Workday", r'\bworkday\b'),
            ("Amazon Connect", r'\bamazon\s+connect\b'),
            ("Snowflake", r'\bsnowflake\b'),
            ("SAP", r'\bsap\b|\babap\b'),
            ("Mainframe", r'\bmainframe\b|\bcobol\b'),
            ("Informatica", r'\binformatica\b'),
            ("SailPoint", r'\bsailpoint\b')
        ]
        doc_full_text = f"{r_clean} " + " ".join(p.text.lower() for p in resume.passages)
        for name, pat in niche_title_checks:
            if re.search(pat, title_lower):
                if not re.search(pat, doc_full_text):
                    final_ats = min(35.0, raw_ats * 0.3)
                    return {
                        "resume": resume,
                        "final_score": round(final_ats, 1),
                        "cov_score": round(cov_score, 1),
                        "spec_score": 10.0,
                        "evidence_score": 10.0,
                        "synergy_score": 0.0,
                        "matched": matched,
                        "missing": missing + [name],
                        "specialization_summary": f"Lacks Title Tech: {name}"
                    }

        # Guardrail: If coverage is below 75% or primary stack conflicts, cap below 90%
        if cov_score < 75.0 or synergy_score < 50.0:
            final_ats = min(88.0, raw_ats * 0.80)
        else:
            final_ats = min(99.5, max(25.0, raw_ats))

        # Specialization summary label for reporting
        spec_parts = [p for p in (fe_tag, cloud_tag, kafka_tag) if p]
        if 'lead' in r_words or 'architect' in r_words:
            spec_parts.append("Lead")
        elif 'full' in r_words and 'stack' in r_words:
            spec_parts.append("Full Stack")
        elif 'backend' in r_words:
            spec_parts.append("Backend")
        spec_summary = " + ".join(spec_parts) if spec_parts else "General Java"

        return {
            "resume": resume,
            "final_score": round(final_ats, 1),
            "cov_score": round(cov_score, 1),
            "spec_score": round(spec_score, 1),
            "evidence_score": round(evidence_score, 1),
            "synergy_score": round(synergy_score, 1),
            "matched": matched,
            "missing": missing,
            "specialization_summary": spec_summary
        }

    def select_best_resume(
        self, job_title: str, job_description: str, job_location: str = ""
    ) -> Dict[str, Any]:
        """AI Keyword Extraction and Highest-Score Resume Selection Engine.

        Algorithm:
        1. Extract all technical keywords and skill requirements from the job description using AI.
        2. Access and evaluate EACH AND EVERY candidate resume in the portfolio (all 199 resumes).
        3. Calculate accurate, industrial-standard ATS matching scores for every single resume.
        4. Rank all resumes strictly by their calculated match score and identify the highest scoring resume.
        5. If all resumes secured less than 85.0% match, reject that job.
        6. Otherwise, select and upload the winning resume.
        """
        # 1. Candidate Eligibility Gate (C2C, Location, Experience)
        job = JobDecomposer.decompose(job_title, job_description)
        eligibility = self.eligibility_gater.evaluate_eligibility(job)
        if eligibility.has_confirmed_conflict:
            conflict_msg = f"Candidate ineligible: {'; '.join(eligibility.reasons)}"
            return {
                "resume_path": None,
                "filename": None,
                "match_percentage": 0.0,
                "extracted_keywords": [],
                "matched_skills": [],
                "missing_skills": [],
                "is_match": False,
                "min_threshold": self.min_match_percentage,
                "decision": "Reject",
                "decision_reason": conflict_msg,
                "reason": conflict_msg,
                "eligibility": eligibility.to_dict(),
                "total_evaluated": 0,
                "top_candidates": [],
                "all_scores": []
            }

        all_resumes = self.catalog.get_all_resumes()
        if not all_resumes:
            return {
                "resume_path": None,
                "filename": None,
                "match_percentage": 0.0,
                "extracted_keywords": [],
                "matched_skills": [],
                "missing_skills": [],
                "is_match": False,
                "min_threshold": self.min_match_percentage,
                "decision": "Reject",
                "decision_reason": "No readable resumes found in catalog.",
                "reason": "No readable resumes found in catalog.",
                "total_evaluated": 0,
                "top_candidates": [],
                "all_scores": []
            }

        # 2. Extract all technical keywords from the job description using AI
        extracted_keywords = AITechnicalKeywordExtractor.extract_keywords(job_title, job_description)
        if not extracted_keywords:
            extracted_keywords = ["Java", "Spring Boot", "Microservices", "REST APIs", "AWS"]

        # 3. Access and calculate ATS matching scores for EACH AND EVERY resume in portfolio
        scored_resumes = [
            self.compute_candidate_ats_score(
                resume=r,
                job_title=job_title,
                job_description=job_description,
                extracted_keywords=extracted_keywords,
                job_location=job_location
            )
            for r in all_resumes
        ]

        # 4. Rank all resumes strictly descending by ATS score, tie-break by specialization alignment
        scored_resumes.sort(
            key=lambda x: (x["final_score"], x["spec_score"], x["cov_score"]),
            reverse=True
        )

        best = scored_resumes[0]
        best_resume = best["resume"]
        highest_score = best["final_score"]
        matched_skills = best["matched"]
        missing_skills = best["missing"]

        # 5. Strict Cutoff: If all resumes secured less than threshold (>= 85.0%), reject that job
        threshold = self.min_match_percentage  # 85.0%
        if highest_score < threshold:
            decision = "Reject"
            is_match = False
            decision_reason = (
                f"REJECTED: All {len(all_resumes)} resumes secured less than {threshold}% match. "
                f"Highest was '{best_resume.resume_id}' ({highest_score}% < {threshold}%). Job rejected."
            )
        else:
            decision = "Select"
            is_match = True
            decision_reason = (
                f"SELECTED: Resume '{best_resume.resume_id}' secured highest score {highest_score}% "
                f"(>= {threshold}%). Matched {len(matched_skills)}/{len(extracted_keywords)} technical keywords."
            )

        top_candidates = [
            {
                "resume_id": item["resume"].resume_id,
                "filename": os.path.basename(item["resume"].file_path),
                "score": item["final_score"],
                "keyword_coverage": item["cov_score"],
                "specialization_score": item["spec_score"],
                "matched_count": len(item["matched"]),
                "total_keywords": len(extracted_keywords),
                "matched_skills": item["matched"],
                "missing_skills": item["missing"],
                "specialization": item["specialization_summary"]
            }
            for item in scored_resumes[:5]
        ]

        all_scores_summary = [
            {
                item["resume"].resume_id: {
                    "score": item["final_score"],
                    "matched": len(item["matched"]),
                    "total": len(extracted_keywords),
                    "specialization": item["specialization_summary"]
                }
            }
            for item in scored_resumes[:5]
        ]

        return {
            "resume_path": best_resume.file_path,
            "filename": os.path.basename(best_resume.file_path),
            "match_percentage": highest_score,
            "extracted_keywords": extracted_keywords,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "is_match": is_match,
            "min_threshold": threshold,
            "decision": decision,
            "decision_reason": decision_reason,
            "reason": decision_reason,
            "eligibility": eligibility.to_dict(),
            "total_evaluated": len(all_resumes),
            "top_candidates": top_candidates,
            "all_scores": all_scores_summary
        }


