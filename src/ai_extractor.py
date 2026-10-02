"""AI Technical Keyword Extraction Engine.

Extracts all technical skills, programming languages, frameworks, cloud platforms,
databases, developer tools, and architectures from Job Descriptions using AI
(LLM via Google Gemini / OpenAI when configured, or built-in offline NLP engine).
"""
import os
import re
import json
import urllib.request
import urllib.error
from typing import List, Set, Optional

from src.ontology import TechOntology


class AITechnicalKeywordExtractor:
    """Extracts all specific technical keywords from a job posting using AI."""

    # Canonical display mapping for standardizing keywords
    DISPLAY_NAMES = {
        "java": "Java",
        "spring boot": "Spring Boot",
        "spring framework": "Spring Framework",
        "spring mvc": "Spring MVC",
        "spring data jpa": "Spring Data JPA",
        "spring security": "Spring Security",
        "spring batch": "Spring Batch",
        "spring cloud": "Spring Cloud",
        "microservices": "Microservices",
        "microservice": "Microservices",
        "micro-services": "Microservices",
        "rest apis": "REST APIs",
        "rest api": "REST APIs",
        "rest": "REST APIs",
        "restful": "REST APIs",
        "graphql": "GraphQL",
        "grpc": "gRPC",
        "websockets": "WebSockets",
        "websocket": "WebSockets",
        "kafka": "Apache Kafka",
        "apache kafka": "Apache Kafka",
        "kafka streams": "Kafka Streams",
        "rabbitmq": "RabbitMQ",
        "aws": "AWS",
        "amazon web services": "AWS",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "k8s": "Kubernetes",
        "helm": "Helm",
        "terraform": "Terraform",
        "react": "React",
        "react.js": "React",
        "reactjs": "React",
        "angular": "Angular",
        "angularjs": "AngularJS",
        "typescript": "TypeScript",
        "javascript": "JavaScript",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "node": "Node.js",
        "python": "Python",
        "fastapi": "FastAPI",
        "flask": "Flask",
        "django": "Django",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mysql": "MySQL",
        "oracle": "Oracle",
        "mongodb": "MongoDB",
        "redis": "Redis",
        "dynamodb": "DynamoDB",
        "cassandra": "Cassandra",
        "elasticsearch": "Elasticsearch",
        "opensearch": "OpenSearch",
        "snowflake": "Snowflake",
        "ci/cd": "CI/CD",
        "ci-cd": "CI/CD",
        "jenkins": "Jenkins",
        "github actions": "GitHub Actions",
        "gitlab": "GitLab",
        "junit": "JUnit",
        "mockito": "Mockito",
        "testcontainers": "Testcontainers",
        "git": "Git",
        "maven": "Maven",
        "gradle": "Gradle",
        "langchain": "LangChain",
        "langgraph": "LangGraph",
        "crewai": "CrewAI",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "mcp": "MCP (Model Context Protocol)",
        "model context protocol": "MCP (Model Context Protocol)",
        "ai / llm": "AI / LLM",
        "llm": "LLM",
        "genai": "Generative AI",
        "generative ai": "Generative AI",
        "agents": "AI Agents",
        "agentic ai": "Agentic AI",
        "sql": "SQL",
        "nosql": "NoSQL",
        "camunda": "Camunda",
        "camunda 7": "Camunda",
        "camunda 8": "Camunda",
        "bpmn": "BPMN 2.0",
        "guidewire": "Guidewire",
        "claimcenter": "Guidewire ClaimCenter",
        "mulesoft": "MuleSoft",
        "amazon connect": "Amazon Connect",
        "salesforce": "Salesforce",
        "pega": "Pega"
    }

    # High-priority technical patterns to check during offline NLP extraction
    TECH_PATTERNS = [
        # Languages
        (r'\bjava\s*(?:17|21|8|11)?\b', "Java"),
        (r'\bpython\s*(?:3(?:\.\d+)?)?\b', "Python"),
        (r'\btypescript\b|\bts\b', "TypeScript"),
        (r'\bjavascript\b|\bjs\b|\bes6\b', "JavaScript"),
        (r'\bgolang\b|\bgo\s+lang\b', "Golang"),
        (r'\bc#\b|\bdotnet\b|\b\.net\b', ".NET / C#"),
        (r'\bc\+\+\b', "C++"),
        (r'\bruby\b|\brails\b', "Ruby on Rails"),
        (r'\bscala\b', "Scala"),
        (r'\bkotlin\b', "Kotlin"),

        # Backend frameworks
        (r'\bspring\s*boot\s*(?:3|2)?\b', "Spring Boot"),
        (r'\bspring\s+mvc\b', "Spring MVC"),
        (r'\bspring\s+data\s*jpa\b|\bjpa\b|\bhibernate\b', "Spring Data JPA / Hibernate"),
        (r'\bspring\s+batch\b', "Spring Batch"),
        (r'\bspring\s+cloud\b', "Spring Cloud"),
        (r'\bspring\s+security\b', "Spring Security"),
        (r'\bspring\s+framework\b|\bspring\b', "Spring Framework"),
        (r'\bnode\.?js\b|\bnodejs\b', "Node.js"),
        (r'\bexpress\.?js\b|\bexpress\b', "Express.js"),
        (r'\bfastapi\b', "FastAPI"),
        (r'\bflask\b', "Flask"),
        (r'\bdjango\b', "Django"),

        # Architecture & APIs
        (r'\bmicroservices?\b|\bmicro-services?\b', "Microservices"),
        (r'\brestful\b|\brest\s+apis?\b|\brest\b', "REST APIs"),
        (r'\bgraphql\b', "GraphQL"),
        (r'\bgrpc\b', "gRPC"),
        (r'\bwebsockets?\b', "WebSockets"),
        (r'\bevent-driven\b|\bevent\s+driven\b', "Event-Driven Architecture"),

        # Streaming & Messaging
        (r'\bapache\s+kafka\b|\bkafka\b', "Apache Kafka"),
        (r'\bkafka\s+streams\b', "Kafka Streams"),
        (r'\brabbitmq\b', "RabbitMQ"),
        (r'\bactivemq\b', "ActiveMQ"),
        (r'\bamazon\s+msk\b|\bmsk\b', "Amazon MSK"),
        (r'\bsqs\b|\bamazon\s+sqs\b', "AWS SQS"),
        (r'\bsns\b|\bamazon\s+sns\b', "AWS SNS"),

        # Frontend
        (r'\breact(?:\.js|js)?\b', "React"),
        (r'\bangular(?:\.js|js|2\+)?\b', "Angular"),
        (r'\bvue(?:\.js|js)?\b', "Vue.js"),
        (r'\bnext\.?js\b', "Next.js"),
        (r'\bredux(?:\s+toolkit)?\b', "Redux"),
        (r'\bzustand\b', "Zustand"),
        (r'\btailwind(?:\s+css)?\b', "Tailwind CSS"),
        (r'\bhtml5?\b|\bcss3?\b', "HTML5 / CSS3"),

        # Cloud & Containers
        (r'\bamazon\s+web\s+services\b|\baws\b', "AWS"),
        (r'\bgoogle\s+cloud\b|\bgcp\b', "Google Cloud (GCP)"),
        (r'\bmicrosoft\s+azure\b|\bazure\b', "Azure"),
        (r'\bdocker\b', "Docker"),
        (r'\bkubernetes\b|\bk8s\b', "Kubernetes"),
        (r'\beks\b|\bamazon\s+eks\b', "Amazon EKS"),
        (r'\becs\b|\bamazon\s+ecs\b', "Amazon ECS"),
        (r'\baws\s+lambda\b|\blambda\b', "AWS Lambda"),
        (r'\bamazon\s+s3\b|\bs3\b', "Amazon S3"),
        (r'\bamazon\s+rds\b|\brds\b', "Amazon RDS"),
        (r'\bterraform\b', "Terraform"),
        (r'\bhelm\b', "Helm"),

        # Databases
        (r'\bpostgresql\b|\bpostgres\b', "PostgreSQL"),
        (r'\bmysql\b', "MySQL"),
        (r'\boracle\s*(?:db|database)?\b', "Oracle"),
        (r'\bmongodb\b|\bmongo\b', "MongoDB"),
        (r'\bredis\b', "Redis"),
        (r'\bdynamodb\b|\bamazon\s+dynamodb\b', "DynamoDB"),
        (r'\bcassandra\b', "Cassandra"),
        (r'\belasticsearch\b|\belastic\s+search\b', "Elasticsearch"),
        (r'\bopensearch\b', "OpenSearch"),
        (r'\bsnowflake\b', "Snowflake"),
        (r'\bsql\b', "SQL"),
        (r'\bnosql\b', "NoSQL"),

        # AI, LLM & Modern Tech
        (r'\blangchain\b', "LangChain"),
        (r'\blanggraph\b', "LangGraph"),
        (r'\bcrewai\b', "CrewAI"),
        (r'\bopenai\b', "OpenAI"),
        (r'\banthropic\b', "Anthropic"),
        (r'\bmodel\s+context\s+protocol\b|\bmcp\b', "MCP (Model Context Protocol)"),
        (r'\bllms?\b|\blarge\s+language\s+models?\b', "LLM / Large Language Models"),
        (r'\bgenai\b|\bgenerative\s+ai\b', "Generative AI"),
        (r'\bai\s+agents?\b|\bagentic\s+ai\b|\bagents?\b', "AI Agents / Agentic Workflows"),
        (r'\bvector\s+(?:db|database|embeddings?)\b|\bpinecone\b|\bweaviate\b|\bchroma\b', "Vector Databases / Embeddings"),

        # CI/CD & Testing
        (r'\bci/cd\b|\bci-cd\b|\bcontinuous\s+integration\b', "CI/CD Pipeline"),
        (r'\bjenkins\b', "Jenkins"),
        (r'\bgithub\s+actions\b', "GitHub Actions"),
        (r'\bgitlab(?:\s+ci)?\b', "GitLab"),
        (r'\bjunit\s*5?\b', "JUnit"),
        (r'\bmockito\b', "Mockito"),
        (r'\btestcontainers\b', "Testcontainers"),
        (r'\bplaywright\b|\bcypress\b|\bselenium\b', "Automation Testing"),
        (r'\bgit\b', "Git"),
        (r'\bmaven\b', "Maven"),
        (r'\bgradle\b', "Gradle"),

        # Workflow, BPM & Enterprise Platforms
        (r'\bcamunda(?:\s*(?:7|8|bpm))?\b', "Camunda"),
        (r'\bbpmn(?:\s*2\.0)?\b', "BPMN 2.0"),
        (r'\bguidewire\b', "Guidewire"),
        (r'\bclaimcenter\b', "Guidewire ClaimCenter"),
        (r'\bmulesoft\b|\bmule\b', "MuleSoft"),
        (r'\bamazon\s+connect\b', "Amazon Connect"),
        (r'\bsalesforce\b|\bapex\b', "Salesforce"),
        (r'\bpega\b|\bpega\s*prpc\b', "Pega")
    ]

    @classmethod
    def extract_keywords(cls, job_title: str, job_description: str) -> List[str]:
        """Extract all technical keywords using AI (LLM if configured, else offline NLP engine)."""
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        # 1. Real-time LLM extraction if API key is present
        if gemini_key:
            try:
                llm_kws = cls._extract_with_gemini(job_title, job_description, gemini_key)
                if llm_kws and len(llm_kws) >= 3:
                    return llm_kws
            except Exception as e:
                print(f"[AI Extractor] Gemini API notice: {e}. Falling back to NLP extractor.")

        if openai_key:
            try:
                llm_kws = cls._extract_with_openai(job_title, job_description, openai_key)
                if llm_kws and len(llm_kws) >= 3:
                    return llm_kws
            except Exception as e:
                print(f"[AI Extractor] OpenAI API notice: {e}. Falling back to NLP extractor.")

        # 2. Built-in high-precision AI/NLP Technical Entity Extraction engine
        return cls._extract_with_nlp(job_title, job_description)

    @classmethod
    def _extract_with_gemini(cls, job_title: str, job_description: str, api_key: str) -> Optional[List[str]]:
        """Call Google Gemini 1.5 Flash to extract technical keywords."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = (
            f"You are an expert Technical Recruiter and ATS parser.\n"
            f"Extract ALL technical keywords, technologies, programming languages, frameworks, cloud platforms, "
            f"databases, APIs, developer tools, and architectures required or mentioned in this job posting.\n"
            f"Exclude non-technical soft skills (like communication, teamwork, leadership).\n\n"
            f"Target Role: {job_title}\n"
            f"Job Description:\n{job_description}\n\n"
            f"Output ONLY a valid JSON array of strings containing unique canonical technical keywords, e.g.:\n"
            f"[\"Java\", \"Spring Boot\", \"Microservices\", \"Apache Kafka\", \"AWS\", \"Docker\", \"Kubernetes\", \"PostgreSQL\", \"React\", \"TypeScript\", \"CI/CD\"]"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 400}
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r'\[[\s\S]*?\]', text)
            if match:
                raw_list = json.loads(match.group(0))
                return cls._normalize_keyword_list(raw_list)
        return None

    @classmethod
    def _extract_with_openai(cls, job_title: str, job_description: str, api_key: str) -> Optional[List[str]]:
        """Call OpenAI GPT-4o-mini to extract technical keywords."""
        url = "https://api.openai.com/v1/chat/completions"
        prompt = (
            f"Extract ALL technical keywords, technologies, programming languages, frameworks, cloud platforms, "
            f"databases, APIs, developer tools, and architectures required or mentioned in this job posting.\n"
            f"Exclude non-technical soft skills.\n\n"
            f"Target Role: {job_title}\n"
            f"Job Description:\n{job_description}\n\n"
            f"Output ONLY a valid JSON array of strings, e.g.:\n"
            f"[\"Java\", \"Spring Boot\", \"Microservices\", \"Apache Kafka\", \"AWS\", \"Docker\", \"Kubernetes\", \"PostgreSQL\", \"React\", \"TypeScript\", \"CI/CD\"]"
        )
        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 400
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            match = re.search(r'\[[\s\S]*?\]', text)
            if match:
                raw_list = json.loads(match.group(0))
                return cls._normalize_keyword_list(raw_list)
        return None

    @classmethod
    def _extract_with_nlp(cls, job_title: str, job_description: str) -> List[str]:
        """High-accuracy built-in offline NLP Technical Entity Extraction."""
        combined_text = f" {job_title} \n {job_description} "
        found_keywords: List[str] = []
        seen_canonical: Set[str] = set()

        for pattern, display_name in cls.TECH_PATTERNS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                canon = display_name.lower()
                if canon not in seen_canonical:
                    seen_canonical.add(canon)
                    found_keywords.append(display_name)

        # Also cross-check TechOntology categories
        for term, canonical in TechOntology.ALIASES.items():
            if len(term) < 3 and term not in ("ts", "js", "c#", "go", "s3", "ec2", "rds", "sqs", "sns"):
                continue
            escaped = re.escape(term)
            pat = r'(?i)\b' + escaped + r'\b'
            if re.search(pat, combined_text):
                disp = cls.DISPLAY_NAMES.get(canonical, canonical.title())
                c_key = disp.lower()
                if c_key not in seen_canonical:
                    seen_canonical.add(c_key)
                    found_keywords.append(disp)

        # Smart Subsumption: Clean out redundant short tokens if longer specific phrase exists
        subsumed_terms = set()
        lower_map = {k.lower(): k for k in found_keywords}
        
        # S3, RDS, ECS, EC2, Lambda subsumption under AWS services
        if "amazon s3" in lower_map or "aws" in lower_map:
            if "s3" in lower_map and ("amazon s3" in lower_map or "aws" in lower_map):
                subsumed_terms.add("s3")
        if "amazon rds" in lower_map:
            subsumed_terms.add("rds")
        if "amazon ecs" in lower_map:
            subsumed_terms.add("ecs")
        if "aws lambda" in lower_map:
            subsumed_terms.add("lambda")
        if "ci/cd pipeline" in lower_map:
            subsumed_terms.add("ci/cd")
        if "spring boot" in lower_map:
            subsumed_terms.add("spring framework")
        if "apache kafka" in lower_map:
            subsumed_terms.add("kafka")

        filtered = [k for k in found_keywords if k.lower() not in subsumed_terms]
        return filtered

    @classmethod
    def _normalize_keyword_list(cls, raw_list: List[str]) -> List[str]:
        """Clean and canonicalize extracted keyword strings."""
        seen = set()
        clean = []
        for item in raw_list:
            if not isinstance(item, str):
                continue
            k = item.strip().strip("'\"").strip()
            if not k or len(k) < 2:
                continue
            k_lower = k.lower()
            if k_lower in seen:
                continue
            seen.add(k_lower)
            disp = cls.DISPLAY_NAMES.get(k_lower, k)
            clean.append(disp)
        return clean
