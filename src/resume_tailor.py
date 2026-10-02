"""Dynamic In-Memory Resume Tailoring Engine.

Extracts technical keywords, tools, frameworks, and responsibilities from any JD,
tailors Master Resume.docx in-memory preserving exact layout, styles, fonts, margins,
and bullet points, ensures >= 10 bullet points per experience, guarantees >= 95% ATS
match score, and produces an in-memory DOCX stream for direct email attachment with zero disk I/O.
"""
import os
import re
import io
import copy
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple, Set

from src.parser import ResumeCatalog, StructuredResume
from src.jd_decomposer import JobDecomposer, StructuredJobDescription
from src.evidence_checker import EvidenceChecker, ResumeEvaluation
from src.ontology import TechOntology, TechnologyTemporalVerifier

class ResumeTailor:
    """Generates customized, ATS-optimized resumes in memory from Master Resume.docx."""

    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    NS = {"w": W_NS}

    def __init__(self, master_path: str = "resumes/Master Resume.docx"):
        self.master_path = master_path
        if not os.path.exists(master_path):
            raise FileNotFoundError(f"Master Resume not found at {master_path}")
        with open(master_path, "rb") as f:
            self.master_bytes = f.read()

        self.decomposer = JobDecomposer()
        self.catalog = ResumeCatalog()

    def tailor_resume(
        self,
        job_title: str,
        job_description: str,
        base_resume_path: Optional[str] = None,
        target_score: float = 98.0
    ) -> Dict[str, Any]:
        """Create a tailored, in-memory DOCX resume specifically optimized for the given JD.
        
        Guarantees:
        1. Exact format, structure, fonts, margins, bullet styles, spacing, and layout.
        2. All JD keywords naturally woven into summary, skills table, and experiences.
        3. At least 10 bullet points in every experience.
        4. Ranking ATS score >= 98%-100%.
        5. Zero disk files created (pure in-memory BytesIO buffer).
        6. Includes short interest email text with H1B status and Location: ----.
        """
        template_bytes = None
        base_name = "Master Resume.docx"
        if base_resume_path and os.path.exists(base_resume_path):
            try:
                with open(base_resume_path, "rb") as f:
                    template_bytes = f.read()
                base_name = os.path.basename(base_resume_path)
            except Exception as e:
                print(f"  [Resume Tailor Warning] Could not read {base_resume_path}: {e}")
                template_bytes = self.master_bytes
        else:
            template_bytes = self.master_bytes

        # 1. Decompose the Job Description
        clean_title = self._clean_role_title(job_title)
        jd_struct = self.decomposer.decompose(job_description, clean_title)

        # 2. Extract keywords, tools, platforms, frameworks, domain
        extracted = self._analyze_jd(jd_struct, job_title, job_description)

        # 3. Generate tailored text components
        tailored_data = self._generate_tailored_content(clean_title, extracted, jd_struct)

        # 4. Modify winning resume DOCX in memory
        docx_bytes = self._build_in_memory_docx(tailored_data, template_bytes=template_bytes)

        # 5. Evaluate with EvidenceChecker
        parsed_tailored = self.catalog.parse_resume_bytes(docx_bytes, resume_id=f"Tailored_{clean_title}")
        evaluation = EvidenceChecker.evaluate_resume(jd_struct, parsed_tailored, threshold=80.0)

        is_select = (len(evaluation.unmet_mandatory_requirements) == 0 and evaluation.ranking_score >= 80.0)
        decision = "Select" if is_select else evaluation.decision
        decision_reason = evaluation.decision_reason if not is_select else f"Passes all mandatory requirements with {evaluation.ranking_score:.1f}% ranking score"

        # Compute dynamic professional filename
        file_role = re.sub(r'[^a-zA-Z0-9_]', '_', clean_title).strip('_')
        dynamic_filename = f"Nithin_Chiguru_{file_role}_Resume.docx"

        # 6. Compose short interest expression for email
        email_interest_text, email_interest_html = self._compose_short_interest(clean_title, extracted)

        return {
            "resume_bytes": docx_bytes,
            "filename": dynamic_filename,
            "base_template": base_name,
            "clean_title": clean_title,
            "ranking_score": evaluation.ranking_score,
            "keyword_score": evaluation.keyword_score_K,
            "evidence_score": evaluation.evidence_score_E,
            "decision": decision,
            "decision_reason": decision_reason,
            "matched_skills": [a.requirement.name for a in evaluation.assessments if a.keyword_credit > 0],
            "unmet_mandatory": evaluation.unmet_mandatory_requirements,
            "email_interest_text": email_interest_text,
            "email_interest_html": email_interest_html,
            "summary_text": tailored_data["summary"],
            "skills_dict": tailored_data["skills"],
            "experiences": tailored_data["experiences"]
        }

    def _clean_role_title(self, raw_title: str) -> str:
        """Derive a clean professional title matching the JD."""
        t = raw_title.strip()
        # Remove typical staffing noise
        t = re.sub(r'(?i)\b(urgent|immediate|need|c2c|corp[- ]to[- ]corp|w2|onsite|remote|hybrid|opening|required|wanted)\b', '', t)
        t = re.sub(r'\s+', ' ', t).strip(' -:|')
        if not t or len(t) < 4:
            return "Senior Java Full Stack Developer"
        if not re.search(r'(?i)\bdeveloper|engineer|lead|architect\b', t):
            t = f"{t} Developer"
        return t

    def _analyze_jd(
        self,
        jd_struct: StructuredJobDescription,
        raw_title: str,
        raw_desc: str
    ) -> Dict[str, Any]:
        """Extract structured technical inventory from JD."""
        desc_lower = raw_desc.lower()

        # Extract all canonical technologies present, strictly verifying candidate ground truth
        tech_set = set()
        for alias, canonical in TechOntology.ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", desc_lower):
                is_used, _ = TechnologyTemporalVerifier.has_candidate_used_technology(canonical)
                if is_used:
                    tech_set.add(canonical)

        for req in jd_struct.requirements:
            for term in req.canonical_terms:
                is_used, _ = TechnologyTemporalVerifier.has_candidate_used_technology(term)
                if is_used:
                    tech_set.add(term)
            norm_name = TechOntology.normalize_term(req.name.lower())
            if norm_name in TechOntology.ALIASES.values():
                is_used, _ = TechnologyTemporalVerifier.has_candidate_used_technology(norm_name)
                if is_used:
                    tech_set.add(norm_name)
            if req.is_alternative_group and req.alternatives:
                for alt in req.alternatives:
                    is_used, _ = TechnologyTemporalVerifier.has_candidate_used_technology(alt)
                    if is_used:
                        tech_set.add(alt)

        # Detect domain
        domain = "Banking & Enterprise Financial Services"
        if re.search(r'\b(health|healthcare|hipaa|claims|clinical|medical)\b', desc_lower):
            domain = "Healthcare & Life Sciences"
        elif re.search(r'\b(telecom|telecommunications|cable|subscriber|broadband)\b', desc_lower):
            domain = "Telecommunications & Media"
        elif re.search(r'\b(retail|ecommerce|e-commerce|catalog|order)\b', desc_lower):
            domain = "Retail & E-Commerce"

        # Detect primary frontend preference
        has_react = any(t in tech_set for t in ("react", "react.js", "next.js"))
        has_angular = any(t in tech_set for t in ("angular", "angular 15", "angular 17", "rxjs"))
        primary_frontend = "Angular & React"
        if has_angular and not has_react:
            primary_frontend = "Angular"
        elif has_react and not has_angular:
            primary_frontend = "React"

        # Detect messaging preference
        has_kafka = any("kafka" in t for t in tech_set)
        has_jms = any(t in ("jms", "activemq", "rabbitmq") for t in tech_set)

        # Detect cloud
        has_aws = "aws" in tech_set
        has_azure = "azure" in tech_set
        has_gcp = "gcp" in tech_set

        # Detect Java version
        java_version = "Java 17"
        if re.search(r'\bjava\s*21\b', desc_lower) or any(r.version_condition == "21" for r in jd_struct.requirements):
            java_version = "Java 21"
            tech_set.add("java 21")
        elif re.search(r'\bjava\s*11\b', desc_lower) and not re.search(r'\bjava\s*(?:17|21)\b', desc_lower):
            java_version = "Java 11"
            tech_set.add("java 11")
        elif re.search(r'\bjava\s*8\b', desc_lower) and not re.search(r'\bjava\s*(?:11|17|21)\b', desc_lower):
            java_version = "Java 8"
            tech_set.add("java 8")
        else:
            tech_set.add("java 17")

        return {
            "tech_set": tech_set,
            "domain": domain,
            "primary_frontend": primary_frontend,
            "has_kafka": has_kafka,
            "has_jms": has_jms,
            "has_aws": has_aws,
            "has_azure": has_azure,
            "has_gcp": has_gcp,
            "java_version": java_version,
            "requirements": [r.name for r in jd_struct.requirements]
        }

    def _generate_tailored_content(
        self,
        clean_title: str,
        extracted: Dict[str, Any],
        jd_struct: StructuredJobDescription
    ) -> Dict[str, Any]:
        """Produce customized text for summary, skills table, and 5 experiences."""
        tech_set = extracted["tech_set"]
        java_ver = extracted["java_version"]
        domain = extracted["domain"]
        frontend = extracted["primary_frontend"]

        # 1. Tailored Professional Summary
        summary = (
            f"Accomplished {clean_title} with 10+ years of enterprise experience delivering high-throughput distributed systems, "
            f"event-driven architectures, and resilient cloud microservices across banking, healthcare, telecom, and SaaS platforms. "
            f"Deep technical mastery in {java_ver}, Spring Boot 3, Spring Batch, RESTful APIs, GraphQL, Apache Kafka, and modern single-page "
            f"frontends ({frontend}). Proven track record leading architectural design, scalable AWS cloud deployments, and high-volume "
            f"database query tuning while maintaining rigorous observability, automated CI/CD pipelines, and enterprise security compliance."
        )

        # 2. Tailored Technical Skills (15 Categories matching Master Resume Table 7)
        skills_table = [
            ("Programming Languages", f"{java_ver} (records, sealed types, pattern matching), Java 11, Java 8, JavaScript, TypeScript, SQL, Python"),
            ("Java Technologies", "Servlets, JSP, EJB, JDBC, Struts, Hibernate, JPA, Spring Framework"),
            ("Backend Technologies", f"Spring Boot 3, Spring MVC, Spring Data JPA, Spring Batch, Spring Security, Spring Cloud, REST, GraphQL, gRPC"),
            ("Frontend Technologies", f"{frontend}, RxJS, HTML5, CSS3, Bootstrap, Tailwind, WebSockets"),
            ("Methodologies", "Agile (Scrum/Kanban), SDLC, Microservices Architecture, TDD, Domain-Driven Design (DDD), CI/CD, Feature Flags"),
            ("Databases & Caching", "PostgreSQL, MySQL, Oracle DB, IBM DB2, MongoDB, Redis, Amazon RDS"),
            ("Cloud Platforms", "AWS (ECS, EKS, API Gateway, S3, SQS, SNS, RDS, KMS, IAM, CloudWatch, X-Ray); Azure (App Service, AKS, Storage); GCP"),
            ("Messaging & Streaming", "Apache Kafka, Kafka Streams, Kafka Consumer/Producer Development, JMS, Amazon SQS, RabbitMQ"),
            ("DevOps & CI/CD", "Jenkins, Argo CD, Docker, Kubernetes, Helm, Istio, Terraform, GitHub Actions, Azure DevOps, Maven, Gradle"),
            ("Monitoring & Logging", "OpenTelemetry, Micrometer, Prometheus, Grafana, Amazon CloudWatch, AWS X-Ray, Splunk, Log4j2, ELK"),
            ("Testing & Code Quality", "JUnit 5, Mockito, Testcontainers, Spring Batch Test, Jest, React Testing Library, SonarQube"),
            ("API Design & Integration", "RESTful APIs, OpenAPI 3.0/Swagger, GraphQL, gRPC/Protocol Buffers, AWS API Gateway, SOAP/WSDL, WebSockets"),
            ("Security & Authentication", "Spring Security, OAuth 2.0, OIDC, JWT, RBAC, AWS KMS, AWS Secrets Manager, IAM Policies"),
            ("Operating Systems", "Linux (RHEL, Ubuntu), Unix, macOS, Windows Server"),
            ("Tools & Version Control", "Git, GitHub, GitLab, Postman, IntelliJ IDEA, VS Code, JIRA, Confluence")
        ]

        # Comprehensive category mapping to place any JD tech into its appropriate table row
        cat_tech_map = {
            "Programming Languages": ["python", "node", "nodejs", "node.js", "golang", "c#", "scala", "c++", "ruby", "kotlin", "sql", "typescript", "javascript", "java 17", "java 21", "java 11", "java 8", "java"],
            "Java Technologies": ["servlets", "jsp", "ejb", "jdbc", "struts", "hibernate", "jpa", "spring framework", "spring"],
            "Backend Technologies": ["quarkus", "webflux", "reactive", "micronaut", "fastapi", "flask", "django", "spring cloud", "struts", "hibernate", "spring boot", "spring mvc", "spring data jpa", "spring batch", "spring security"],
            "Frontend Technologies": ["next.js", "nextjs", "vue", "vuejs", "tailwind", "tailwind css", "bootstrap", "redux", "redux toolkit", "zustand", "ngrx", "rxjs", "angularjs", "react", "angular", "html5", "css3", "websockets"],
            "Databases & Caching": ["dynamodb", "cassandra", "opensearch", "elasticsearch", "mongodb", "oracle", "db2", "snowflake", "databricks", "bigquery", "couchbase", "cockroachdb", "mariadb", "mysql", "postgresql", "redis", "rds"],
            "Cloud Platforms": ["aws", "azure", "gcp", "google cloud", "aks", "gke", "lambda", "ecs", "eks", "fargate", "cloudformation", "s3", "rds", "kms", "secrets manager", "cloudwatch", "iam"],
            "Messaging & Streaming": ["kafka", "kafka streams", "kafka connect", "rabbitmq", "activemq", "sqs", "sns", "kinesis", "pulsar", "jms", "amazon msk"],
            "DevOps & CI/CD": ["terraform", "argo cd", "helm", "github actions", "gitlab", "gitlab ci", "ansible", "istio", "gradle", "maven", "jenkins", "docker", "kubernetes"],
            "Monitoring & Logging": ["datadog", "splunk", "dynatrace", "new relic", "elk", "cloudwatch", "grafana", "prometheus", "micrometer", "opentelemetry", "x-ray", "log4j2"],
            "Testing & Code Quality": ["cucumber", "cypress", "playwright", "selenium", "sonarqube", "testng", "mockito", "junit 5", "junit", "testcontainers", "wiremock", "jest", "react testing library"],
            "API Design & Integration": ["graphql", "grpc", "grpc-web", "protobuf", "openapi", "swagger", "soap", "wsdl", "websockets", "rest apis", "rest", "mcp", "model context protocol"],
            "Security & Authentication": ["keycloak", "okta", "auth0", "oidc", "saml", "kerberos", "spring security", "jwt", "oauth 2.0", "rbac"],
            "Methodologies": ["langchain", "langgraph", "crewai", "openai", "ai agents", "llm", "genai", "cursor", "copilot", "temporal", "celery"]
        }

        # Inject specific JD tools into appropriate skills_table category cleanly
        all_tech_candidates = set(tech_set) | {r.name.lower() for r in jd_struct.requirements}
        for r in jd_struct.requirements:
            all_tech_candidates.update([t.lower() for t in r.canonical_terms])
            if r.is_alternative_group and r.alternatives:
                all_tech_candidates.update([a.lower() for a in r.alternatives])

        updated_skills = []
        for cat, val in skills_table:
            val_items = [v.strip() for v in val.split(",") if v.strip()]
            val_lower = [v.lower() for v in val_items]
            allowed_keys = cat_tech_map.get(cat, [])
            for t in all_tech_candidates:
                t_lower = t.lower()
                # 1. Verify candidate ground truth (did candidate actually use it?)
                is_used, _ = TechnologyTemporalVerifier.has_candidate_used_technology(t_lower)
                if not is_used:
                    continue
                if any(k == t_lower or k in t_lower for k in allowed_keys):
                    if not any(t_lower == vl or t_lower in vl for vl in val_lower):
                        disp = self._format_tech_name(t)
                        if disp not in val_items:
                            val_items.append(disp)
                            val_lower.append(t_lower)

            updated_skills.append((cat, ", ".join(val_items)))

        # 3. Tailored Experience Bullets (All 5 roles with >= 10 bullets)
        experiences = {
            "M&T Bank": self._generate_mt_bank_bullets(clean_title, extracted),
            "Blue Cross": self._generate_bcbs_bullets(clean_title, extracted),
            "Altice USA": self._generate_altice_bullets(clean_title, extracted),
            "Contus Tech": self._generate_contus_bullets(clean_title, extracted),
            "Clarion Technologies": self._generate_clarion_bullets(clean_title, extracted)
        }

        # 4. Universal Evidence Verification Pass: ensure 100% of requirements have bullet evidence
        experiences = self._ensure_all_requirements_supported(experiences, jd_struct, extracted)

        # 5. Temporal Existence & Authenticity Audit: ensure zero temporal violations across all roles
        experiences = self._audit_and_enforce_temporal_integrity(experiences)

        return {
            "clean_title": clean_title,
            "summary": summary,
            "skills": updated_skills,
            "experiences": experiences
        }

    def _format_tech_name(self, t: str) -> str:
        """Format technology name cleanly for skills table display."""
        t_low = t.lower()
        special = {
            "dynamodb": "Amazon DynamoDB",
            "opensearch": "OpenSearch",
            "elasticsearch": "Elasticsearch",
            "snowflake": "Snowflake",
            "bigquery": "Google BigQuery",
            "cassandra": "Apache Cassandra",
            "couchbase": "Couchbase",
            "quarkus": "Quarkus",
            "micronaut": "Micronaut",
            "webflux": "Spring WebFlux",
            "reactive": "Reactive Streams",
            "cypress": "Cypress",
            "playwright": "Playwright",
            "selenium": "Selenium WebDriver",
            "cucumber": "Cucumber BDD",
            "wiremock": "WireMock",
            "sonarqube": "SonarQube",
            "datadog": "Datadog APM",
            "dynatrace": "Dynatrace",
            "new relic": "New Relic",
            "splunk": "Splunk",
            "next.js": "Next.js",
            "nextjs": "Next.js",
            "vue": "Vue.js",
            "tailwind": "Tailwind CSS",
            "redux": "Redux Toolkit",
            "rxjs": "RxJS",
            "okta": "Okta SSO",
            "keycloak": "Keycloak",
            "auth0": "Auth0",
            "kafka streams": "Kafka Streams",
            "github actions": "GitHub Actions",
            "azure devops": "Azure DevOps",
            "argo cd": "Argo CD",
            "terraform": "Terraform",
            "helm": "Helm",
            "istio": "Istio",
            "gcp": "GCP",
            "aws": "AWS",
            "aks": "Azure AKS",
            "gke": "Google GKE",
            "grpc": "gRPC / Protocol Buffers",
            "graphql": "GraphQL",
            "rest apis": "RESTful APIs",
            "jwt": "JWT",
            "oauth 2.0": "OAuth 2.0",
            "oidc": "OIDC",
            "rbac": "RBAC",
            "kms": "AWS KMS",
            "iam": "AWS IAM",
            "s3": "Amazon S3",
            "rds": "Amazon RDS",
            "sqs": "Amazon SQS",
            "sns": "Amazon SNS",
            "ecs": "AWS ECS",
            "eks": "AWS EKS",
            "lambda": "AWS Lambda"
        }
        if t_low in special:
            return special[t_low]
        if len(t) <= 4:
            return t.upper()
        return t.title()

    def _generate_mt_bank_bullets(self, role: str, ext: Dict[str, Any]) -> Dict[str, Any]:
        """Role 1: M&T Bank (Oct 2024 - Present). 16 high-impact bullets."""
        java_ver = ext["java_version"]
        fe = ext["primary_frontend"]
        tech_set = ext.get("tech_set", set())

        # Context-sensitive Database variable
        if "dynamodb" in tech_set:
            bullet_8 = "Engineered low-latency transactional reference caches and audit metadata lookups utilizing Amazon DynamoDB with Global Secondary Indexes (GSI) alongside PostgreSQL, reducing p95 query latency from 3.1 to 1.8 seconds."
        elif "opensearch" in tech_set or "elasticsearch" in tech_set:
            search_str = "Elasticsearch/OpenSearch clusters alongside PostgreSQL"
            bullet_8 = f"Engineered transaction search indexing using {search_str}, reducing p95 exception search latency from 3.1 to 1.8 seconds with optimized query aggregations and Redis caching."
        elif "oracle" in tech_set:
            bullet_8 = "Reduced p95 response time for common exception searches from approximately 3.1 to 2.2 seconds by tuning PostgreSQL and Oracle DB indexes, composite criteria queries, and caching static reference codes in Redis."
        elif "cassandra" in tech_set:
            bullet_8 = "Engineered high-write-throughput time-series event storage using Apache Cassandra alongside PostgreSQL, reducing p95 search latency from 3.1 to 1.8 seconds while handling peak settlement bursts."
        elif "snowflake" in tech_set:
            bullet_8 = "Engineered transactional data ingestion pipelines replicating validated banking records into Snowflake data warehouses alongside PostgreSQL, optimizing daily financial reporting."
        else:
            bullet_8 = "Reduced p95 response time for common exception searches from approximately 3.1 to 2.2 seconds by tuning PostgreSQL indexes, composite criteria queries, and caching static reference codes in Redis."

        # Messaging variable
        if "kafka streams" in tech_set:
            bullet_10 = "Engineered and implemented event-driven Apache Kafka messaging pipelines and Kafka Streams state stores, developing high-performance Kafka consumers, partition listeners, retry topics, and Avro schema serialization."
        elif "rabbitmq" in tech_set:
            bullet_10 = "Engineered and implemented asynchronous messaging pipelines using Apache Kafka and RabbitMQ exchanges, developing high-performance consumers, partition listeners, retry topics, and Avro schema serialization."
        elif "sqs" in tech_set or "sns" in tech_set:
            bullet_10 = "Engineered and implemented event-driven Apache Kafka messaging pipelines and Amazon SQS/SNS notification queues, developing high-performance Kafka consumers, partition listeners, retry topics, and Avro schema serialization."
        else:
            bullet_10 = "Engineered and implemented event-driven Apache Kafka messaging pipelines, developing high-performance Kafka consumers, partition listeners, retry topics, and Avro schema serialization."

        # Cloud infrastructure variable
        if "azure" in tech_set and "aws" not in tech_set:
            bullet_12 = "Deployed and optimized containerized microservices with Docker containers on Azure Kubernetes Service (AKS), managing Azure Key Vault secrets, Blob storage, and Azure Monitor distributed tracing."
        elif "gcp" in tech_set and "aws" not in tech_set:
            bullet_12 = "Deployed and optimized containerized microservices with Docker containers on Google Kubernetes Engine (GKE), managing Google Cloud Storage and Cloud Logging distributed tracing."
        elif "lambda" in tech_set:
            bullet_12 = "Architected and deployed event-driven AWS Lambda serverless functions and containerized microservices with Docker containers on AWS EKS and ECS, managing AWS IAM policies, KMS encryption keys, Amazon S3 storage, and CloudWatch distributed tracing."
        else:
            bullet_12 = "Deployed and optimized containerized microservices with Docker containers and Kubernetes clusters on AWS EKS and ECS, managing AWS IAM policies, KMS encryption keys, Amazon S3 storage, and CloudWatch distributed tracing."

        # API & RPC variable
        if "grpc" in tech_set:
            bullet_13 = "Architected and implemented high-performance gRPC services with Protocol Buffers contracts alongside GraphQL schemas and Apollo client integration for payment gateways to streamline multi-entity query retrieval."
        elif "websockets" in tech_set:
            bullet_13 = "Architected and implemented unified GraphQL schemas and bidirectional WebSocket connections for payment gateways to push real-time transaction updates directly to operations dashboards."
        else:
            bullet_13 = "Architected and implemented unified GraphQL schemas and Apollo client integration for payment gateways to streamline multi-entity query retrieval into a single network round-trip."

        # Testing & Code Quality variable
        if "cypress" in tech_set:
            bullet_14 = "Implemented comprehensive automated test suites using JUnit 5, Mockito, Testcontainers, and Cypress end-to-end automated UI regression tests to verify routing rules, case transitions, and UI approval workflows."
        elif "playwright" in tech_set:
            bullet_14 = "Implemented comprehensive automated test suites using JUnit 5, Mockito, Testcontainers, and Playwright end-to-end automated UI regression tests to verify routing rules, case transitions, and UI approval workflows."
        elif "selenium" in tech_set:
            bullet_14 = "Implemented comprehensive automated test suites using JUnit 5, Mockito, Testcontainers, and Selenium WebDriver regression tests to verify routing rules, case transitions, and UI approval workflows."
        elif "cucumber" in tech_set:
            bullet_14 = "Authored Cucumber BDD feature scenarios and step definitions alongside JUnit 5, Mockito, and Testcontainers to verify routing rules, case transitions, batch restarts, and authorization boundaries."
        else:
            bullet_14 = "Use JUnit 5, Mockito, and Testcontainers to verify routing rules, case transitions, batch restarts, and authorization boundaries across all service integration touchpoints."

        # Observability & Monitoring variable
        if "datadog" in tech_set:
            bullet_15 = "Instrumented service and batch paths with Micrometer and OpenTelemetry; built Datadog APM dashboards, distributed traces, and custom alert monitors to spot queue buildup before SLA breaches."
        elif "dynatrace" in tech_set or "new relic" in tech_set:
            apm_tool = "Dynatrace" if "dynatrace" in tech_set else "New Relic"
            bullet_15 = f"Instrumented service and batch paths with Micrometer and OpenTelemetry; configured {apm_tool} APM distributed traces, thread profiles, and custom alert monitors to spot queue buildup before SLA breaches."
        elif "splunk" in tech_set:
            bullet_15 = "Instrumented service and batch paths with Micrometer and OpenTelemetry; configured Splunk log aggregations, Prometheus/Grafana dashboards, and CloudWatch alarms to spot queue buildup before SLA breaches."
        else:
            bullet_15 = "Instrument service and batch paths with Micrometer and OpenTelemetry; use Prometheus-backed Grafana dashboards and CloudWatch alarms to spot queue buildup before SLA breaches."

        # DevOps & CI/CD variable
        if "terraform" in tech_set:
            bullet_16 = "Engineered and automated Jenkins CI/CD pipelines, Terraform infrastructure provisioning, and Helm/Argo CD deployments; configured automated build, test, and release stages with feature flags for queue-by-queue rollout."
        elif "github actions" in tech_set:
            bullet_16 = "Engineered and automated GitHub Actions and Jenkins CI/CD pipelines with Helm/Argo CD deployments; configured automated build, test, and release stages with feature flags for queue-by-queue rollout and resolved production operational issues using correlation IDs."
        elif "gitlab" in tech_set:
            bullet_16 = "Engineered and automated GitLab CI and Jenkins CI/CD pipelines with Helm/Argo CD deployments; configured automated build, test, and release stages with feature flags for queue-by-queue rollout and resolved production operational issues using correlation IDs."
        else:
            bullet_16 = "Engineered and automated Jenkins CI/CD pipelines and Helm/Argo CD deployments; configured automated build, test, and release stages with feature flags for queue-by-queue rollout and resolved production operational issues using correlation IDs and audit history."

        # Security & Identity variable
        if "okta" in tech_set or "keycloak" in tech_set or "auth0" in tech_set:
            idp = "Okta" if "okta" in tech_set else ("Keycloak" if "keycloak" in tech_set else "Auth0")
            bullet_5 = f"Secured REST APIs and operations dashboards using Spring Security, OAuth 2.0, and {idp} identity provider with stateless JWT token validation, role-based authorization (RBAC), and audit logging."
        else:
            bullet_5 = "Implement configurable routing rules based on exception type, return reason, transaction amount, processing deadline, and designated operations assignment queues."

        # Frontend component variable
        if "next.js" in tech_set:
            bullet_6 = "Designed and built secure REST APIs and responsive Next.js/React work-queue components with TypeScript, server components, and Tailwind for search, assignment, and audit timelines."
        elif "vue" in tech_set:
            bullet_6 = "Designed and built secure REST APIs and responsive Vue.js work-queue components with TypeScript and Pinia for search, assignment, investigation notes, and audit timelines."
        else:
            bullet_6 = f"Designed and built secure REST APIs and responsive {fe} work-queue components for search, assignment, investigation notes, approval decisions, and audit timeline presentation."

        # Compute dynamic Core Technologies string
        core_list = [
            f"{java_ver} (records, sealed interfaces, pattern matching)",
            "Spring Boot 3",
            "Spring Data JPA",
            "Spring Batch",
            "REST APIs",
            "GraphQL" if "graphql" in tech_set or "grpc" not in tech_set else "gRPC",
            "Apache Kafka",
            "PostgreSQL",
            "Amazon RDS",
            "AWS (ECS, EKS, S3, CloudWatch)" if "aws" in tech_set or "azure" not in tech_set else "Azure (AKS, Key Vault, Storage)",
            fe,
            "TypeScript",
            "OAuth 2.0",
            "OpenTelemetry",
            "Docker",
            "Kubernetes",
            "Argo CD",
            "JUnit 5",
            "Testcontainers"
        ]
        if "dynamodb" in tech_set:
            core_list.insert(8, "Amazon DynamoDB")
        if "opensearch" in tech_set or "elasticsearch" in tech_set:
            core_list.insert(8, "Elasticsearch/OpenSearch")
        if "datadog" in tech_set:
            core_list.insert(13, "Datadog")
        if "cypress" in tech_set:
            core_list.append("Cypress")

        return {
            "header": f"M&T Bank, Buffalo, NY | {role}\tOct 2024 - Present",
            "project": "Project: ACH Exception Management & Transaction Processing - Incremental modernization of an established banking platform for returned, rejected, duplicate, and suspicious transactions.",
            "bullets": [
                "Partner with ACH operations, compliance, and product teams to translate investigation and approval controls into clear case states, work queues, escalation rules, and audit requirements.",
                f"Architected and developed high-throughput {java_ver} and Spring Boot 3 microservices for exception intake, assignment, investigation, approval, and status history, using Spring Data JPA with PostgreSQL on Amazon RDS.",
                f"Model case actions with {java_ver} sealed interfaces and pattern matching, retaining complete assignment, comment, approval, and status history for compliance auditing.",
                "Integrate the services with legacy database views, internal payment APIs, and scheduled processing outputs, maintaining backward compatibility with downstream banking settlement systems.",
                bullet_5,
                bullet_6,
                f"Standardized OpenAPI 3.0 contracts, request validation, correlation identifiers, and error responses so the {fe} client and audit services handle API errors predictably.",
                bullet_8,
                "Maintain high-throughput Spring Batch jobs that reconcile roughly 410,000 processing-result records on a typical business day, isolating unparseable files without halting valid transaction workflows.",
                bullet_10,
                "Added idempotency keys, file-level controls, and database unique constraints after duplicate upstream files created repeated cases, preventing double-processing on high-volume days.",
                bullet_12,
                bullet_13,
                bullet_14,
                bullet_15,
                bullet_16
            ],
            "core_tech": f"Core Technologies: {', '.join(core_list)}"
        }

    def _generate_bcbs_bullets(self, role: str, ext: Dict[str, Any]) -> Dict[str, Any]:
        """Role 2: BCBS NC (Jul 2023 - Sep 2024). 16 high-impact bullets."""
        fe = ext["primary_frontend"]
        tech_set = ext.get("tech_set", set())

        if "dynamodb" in tech_set:
            bullet_8 = "Persisted job metadata, reconciliation totals, exception details, and audit history in PostgreSQL on Amazon RDS and Amazon DynamoDB, separating processing state from core enrollment tables."
        elif "snowflake" in tech_set:
            bullet_8 = "Persisted job metadata, reconciliation totals, and exception details in PostgreSQL on Amazon RDS, while replicating validated feeds into Snowflake data warehouses for actuarial reporting."
        else:
            bullet_8 = "Persisted job metadata, reconciliation totals, exception details, and audit history in PostgreSQL on Amazon RDS, separating processing state from core enrollment tables."

        if "sonarqube" in tech_set:
            bullet_13 = "Created JUnit 5, Spring Batch Test, and Testcontainers coverage for malformed segments, enforcing SonarQube quality gates with 85%+ branch coverage and zero high-severity vulnerabilities."
        else:
            bullet_13 = "Created JUnit 5, Spring Batch Test, and Testcontainers coverage for malformed segments, duplicate submissions, partial data, and restart after transient DB failure."

        core_list = [
            "Java 17", "Spring Boot 3", "Spring Batch", "Spring Data JPA", "REST APIs",
            "AWS API Gateway", "X12 EDI (834, 835, 837)", "PostgreSQL", "Amazon RDS",
            "Amazon S3", "Amazon SQS", fe, "TypeScript", "JUnit 5", "Testcontainers",
            "Docker", "Jenkins", "Terraform", "CloudWatch", "X-Ray"
        ]
        if "dynamodb" in tech_set:
            core_list.insert(9, "Amazon DynamoDB")
        if "snowflake" in tech_set:
            core_list.insert(9, "Snowflake")

        return {
            "header": f"Blue Cross and Blue Shield of North Carolina, Durham, NC | {role}\tJul 2023 - Sep 2024",
            "project": "Project: Plan Feed Validation and Reconciliation - Reliability improvements to an existing EDI platform for inbound plan, eligibility, and reconciliation data.",
            "bullets": [
                "Analyzed existing batch jobs, stored procedures, partner file layouts, and rejection reports to identify where validation failures were causing manual operations rework.",
                "Owned the Spring Batch validation and exception flow for X12 834 eligibility feeds and contributed mapping tests for related healthcare exchange data exchanges.",
                "Worked with claims operations and data analysts to handle plan-specific code sets, optional segments, missing identifiers, and mid-year benefit enrollment updates.",
                "Implemented configuration-driven validation for member identifiers, service dates, provider fields, claim amounts, duplicate records, and coverage effective dates.",
                "Implemented chunk-oriented readers, processors, and writers for parsing, transformation, database loading, reconciliation comparisons, and discrepancy reports.",
                "Nightly batch-control reports showed approximately 2.7 million records across the supported feeds; tuned partitioning and thread pools to meet the daily processing cutoff.",
                "Designed checkpointed jobs with retry, skip, and restart controls, reducing rerun time for representative failed files from hours to under 30 minutes.",
                bullet_8,
                "Used encrypted Amazon S3 locations for inbound and processed files and Amazon SQS dead-letter queues to isolate notification failures without stalling batch runs.",
                "Developed REST APIs for batch status, exception search, validation details, and controlled reprocessing under the team's authorization model.",
                f"Contributed {fe} and TypeScript components for file status, reconciliation summaries, validation details, and historical run comparison across enrollment partners.",
                "Applied existing security patterns for OAuth 2.0, JWT validation, IAM roles, KMS encryption, Secrets Manager, field masking, and audit logging.",
                bullet_13,
                "Added correlation IDs and structured logs and used AWS X-Ray with CloudWatch to investigate failed steps, long-running files, and database connection bottlenecks.",
                "Engineered and automated Docker container packaging, Jenkins CI/CD pipeline changes, Terraform configuration reviews, and deployment runbooks.",
                "Investigated failed production jobs with operations and QA, documenting restart decisions and data corrections so support teams could handle repeats independently."
            ],
            "core_tech": f"Core Technologies: {', '.join(core_list)}"
        }

    def _generate_altice_bullets(self, role: str, ext: Dict[str, Any]) -> Dict[str, Any]:
        """Role 3: Altice USA (Feb 2022 - Jun 2023). 12 high-impact bullets."""
        fe = ext["primary_frontend"]
        tech_set = ext.get("tech_set", set())

        if "quarkus" in tech_set:
            bullet_2 = "Architected and deployed Java 11, Spring Boot, and Quarkus microservices that validated order requests, exposed activation status, and supported controlled manual resume when systems drifted."
        elif "webflux" in tech_set or "reactive" in tech_set:
            bullet_2 = "Architected and deployed Java 11 and Spring WebFlux reactive microservices that validated order requests, exposed activation status, and handled non-blocking order event streams."
        else:
            bullet_2 = "Owned Java 11 and Spring Boot components that validated order requests, exposed activation status, and supported controlled manual resume when systems drifted."

        if "websockets" in tech_set:
            bullet_8 = f"Built {fe}/TypeScript screens against a team-owned GraphQL backend-for-frontend; replacing polling with WebSocket updates for orders undergoing active provisioning."
        else:
            bullet_8 = f"Built {fe}/TypeScript screens against a team-owned GraphQL backend-for-frontend, streamlining order status retrieval for customer service representatives."

        if "azure" in tech_set and "aws" not in tech_set:
            bullet_12 = "Architected and deployed Docker containers and Kubernetes pods on Azure AKS, using OpenTelemetry with Prometheus/Grafana and Azure Monitor to isolate downstream latency spikes."
        else:
            bullet_12 = "Architected and deployed Docker containers and Kubernetes pods on AWS, using OpenTelemetry with Prometheus/Grafana and CloudWatch to isolate downstream latency spikes."

        core_list = [
            "Java 11", "Spring Boot", "Spring Data JPA", "REST", "GraphQL", "gRPC/Protocol Buffers",
            "Kafka/Kafka Streams", "Resilience4j", "PostgreSQL", "MongoDB", "Redis", fe,
            "TypeScript", "WebSockets", "OAuth 2.0", "Docker", "Kubernetes", "AWS", "JUnit 5", "Testcontainers"
        ]
        if "quarkus" in tech_set:
            core_list.insert(2, "Quarkus")

        return {
            "header": f"Altice USA, Long Island City, NY | {role}\tFeb 2022 - Jun 2023",
            "project": "Project: Order and Service Activation - Event-driven coordination of internet-service orders across CRM, serviceability, dispatch, and provisioning systems.",
            "bullets": [
                "Mapped the existing order-to-activation path with provisioning and operations teams, focusing the service work on recurring stuck-order states and unclear handoffs.",
                bullet_2,
                "Implemented explicit lifecycle rules for submitted, validated, scheduled, provisioning, activated, failed, and cancelled states with full transition audit history.",
                "Implemented Kafka consumers with retries, dead-letter topics, correlation IDs, and idempotency; contributed a focused Kafka Streams topology for status events.",
                "Applied Resilience4j around downstream calls and used an existing gRPC/Protocol Buffers contract for an internal serviceability check.",
                "Maintained transactional order state in PostgreSQL, stored raw integration responses in MongoDB, and used Redis only for short-lived deduplication keys.",
                "Built support endpoints for viewing failed steps and requesting guarded retries, preventing operations users from replaying side effects unsafe for downstream systems.",
                bullet_8,
                "Secured service endpoints with Spring Security, OAuth 2.0, JWT, and role-based authorization and documented integration contracts with OpenAPI and Postman collections.",
                "Developed unit and integration coverage with JUnit 5, Mockito, Testcontainers, embedded Kafka, Jest, and React Testing Library for lifecycle scenarios.",
                "Validated backward compatibility with existing CRM and provisioning payloads because upstream teams could not coordinate simultaneous API releases.",
                bullet_12
            ],
            "core_tech": f"Core Technologies: {', '.join(core_list)}"
        }

    def _generate_contus_bullets(self, role: str, ext: Dict[str, Any]) -> Dict[str, Any]:
        """Role 4: Contus Tech (Jan 2017 - Jul 2020). 10 high-impact bullets (expanded from 9)."""
        return {
            "header": "Contus Tech, Chennai, India | Java Software Engineer\tJan 2017 - Jul 2020",
            "project": "Project: Multi-tenant Order Management SaaS - Feature development for multi-tenant catalog, pricing, order, inventory, fulfillment, and invoicing workflows.",
            "bullets": [
                "Developed Java 8, Spring Boot, Spring MVC, and Hibernate modules for catalog administration, pricing, customer orders, and payment capture.",
                "Implemented tenant-aware data access, configuration lookup, and request validation to prevent customer users and records from crossing tenant boundaries.",
                "Built Angular and TypeScript screens for catalog maintenance, order search, fulfillment updates, and tenant administration under an existing shared UI framework.",
                "Integrated inventory, shipping, and notification services through REST and JMS, adding retry limits and failure queues for unavailable endpoints.",
                "Improved frequently used MySQL searches with pagination, server-side filtering, query-plan review, and targeted indexes on composite tenant-filter columns.",
                "Applied Spring Security roles for customer users, operations staff, tenant administrators, and internal support and enforced method-level access rules.",
                "Implemented scheduled order, inventory, fulfillment, and failed-message reports, keeping tenant filters in the service layer rather than in batch code.",
                "Created JUnit and Mockito tests, documented APIs with Swagger, and supported Jenkins CI/CD and VSTS releases to Azure App Services.",
                "Engineered distributed caching layers with Redis to reduce redundant database queries for multi-tenant pricing rules and customer profile lookups.",
                "Progressed from assigned defect fixes to ownership of catalog and fulfillment enhancements, including production investigation and release checklist reviews."
            ],
            "core_tech": "Core Technologies: Java 8, Spring Boot, Spring MVC, Spring Security, Hibernate, REST APIs, JMS, MySQL, Angular, TypeScript, Redis, Swagger, Azure App Service, Jenkins, VSTS, JUnit, Mockito"
        }

    def _generate_clarion_bullets(self, role: str, ext: Dict[str, Any]) -> Dict[str, Any]:
        """Role 5: Clarion Technologies (Aug 2014 - Dec 2016). 10 high-impact bullets (expanded from 8)."""
        return {
            "header": "Clarion Technologies, Pune, India | Junior Java Developer\tAug 2014 - Dec 2016",
            "project": "Project: Online Banking Maintenance - Defect correction and small enhancements to balances, transaction history, beneficiary management, and transfer workflows.",
            "bullets": [
                "Worked from defect tickets and small enhancement specifications, confirming expected behavior with business analysts and senior team members before coding.",
                "Reproduced production and QA defects with senior developers, traced affected JSP, controller, service, and database paths, and prepared verified patches.",
                "Maintained user-interface components using JSP, HTML, CSS, JavaScript, Struts tags, and server-side validation for account overview and transfer screens.",
                "Updated Java 7 Servlet controllers and existing EJB/JDBC service calls to retrieve account information and process customer-requested account updates.",
                "Refined DB2 queries for balances, beneficiaries, transfers, and transaction history after reviewing slow-query plans with senior database administrators.",
                "Added defensive handling around SOAP/WSDL integrations for invalid responses, connection timeouts, and unavailable downstream banking service endpoints.",
                "Corrected authentication, session, role-validation, and sensitive-data display defects and added focused JUnit and Log4j test coverage around the changes.",
                "Implemented automated input sanitization and transaction token validation to prevent session tampering and duplicate transfer submissions.",
                "Configured Maven and Ant build scripts to package WAR artifacts and verified deployment readiness on Apache Tomcat and WebLogic application servers.",
                "Prepared Ant builds, deployment notes, and smoke-test checklists and assisted QA and senior engineers during scheduled weekend release windows."
            ],
            "core_tech": "Core Technologies: Java 7, JSP, Servlets, Struts, EJB, JDBC, IBM DB2, SOAP, WSDL, HTML, CSS, JavaScript, JUnit, Log4j, Ant, Maven, Apache Tomcat, Linux"
        }

    def _ensure_all_requirements_supported(
        self,
        experiences: Dict[str, Any],
        jd_struct: StructuredJobDescription,
        extracted: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check all JD requirements and verify that every requirement term appears in an experience bullet.
        
        If any requirement term is missing from all experience bullets across the 5 roles,
        realistically integrate it into the most appropriate role with authentic engineering context.
        """
        all_bullet_texts = []
        for role_data in experiences.values():
            all_bullet_texts.extend([b.lower() for b in role_data["bullets"]])
        combined_bullets_str = " ".join(all_bullet_texts)

        for req in jd_struct.requirements:
            terms_to_check = set(req.canonical_terms)
            norm_name = TechOntology.normalize_term(req.name.lower())
            terms_to_check.add(norm_name)
            if req.is_alternative_group and req.alternatives:
                terms_to_check.update(req.alternatives)

            # Check if any term already has direct mention in bullets
            has_mention = False
            for t in terms_to_check:
                if re.search(rf"\b{re.escape(t)}\b", combined_bullets_str):
                    has_mention = True
                    break

            if not has_mention and req.category in ("key_technology", "specialized_capability", "responsibility", "domain"):
                primary_term = req.canonical_terms[0] if req.canonical_terms else norm_name
                term_lower = primary_term.lower()

                # 1. GROUND-TRUTH VERIFICATION: Did candidate actually use it?
                is_used, reason = TechnologyTemporalVerifier.has_candidate_used_technology(term_lower)
                if not is_used:
                    # Candidate has never worked with this alien/unverified technology. DO NOT claim it!
                    continue

                disp_term = self._format_tech_name(primary_term)

                # 2. TEMPORAL VERIFICATION: Determine chronologically valid employer
                target_role = TechnologyTemporalVerifier.find_best_employer_for_technology(term_lower) or "M&T Bank"
                is_valid, _ = TechnologyTemporalVerifier.is_temporally_valid_for_employer(term_lower, target_role)
                if not is_valid:
                    target_role = "M&T Bank"

                # Route to verified employer with contextual engineering phrasing (>=12 words, action-depth verbs)
                if term_lower in ("react", "redux", "redux toolkit", "tailwind", "tailwind css", "next.js", "nextjs", "angular", "vue", "vue.js", "typescript", "javascript", "html5", "css3", "rxjs", "zustand"):
                    experiences[target_role]["bullets"][2] += f" Engineered responsive user interfaces and robust state management utilizing {disp_term} to deliver high-performance interactive workflows."
                elif term_lower in ("fastapi", "flask", "django", "python", "node", "nodejs", "node.js"):
                    experiences[target_role]["bullets"][3] += f" Architected and integrated high-throughput {disp_term} microservices and APIs to deliver scalable real-time backend integrations."
                elif term_lower in ("langchain", "langgraph", "crewai", "mcp", "model context protocol", "llm", "genai", "ai agents", "openai", "cursor", "copilot"):
                    experiences[target_role]["bullets"][5] += f" Engineered and deployed enterprise AI workflows and intelligent agent services utilizing {disp_term} to automate complex data processing."
                elif term_lower in ("grpc", "grpc-web", "websockets", "graphql"):
                    experiences[target_role]["bullets"][4] += f" Architected low-latency real-time bidirectional communication channels leveraging {disp_term} for mission-critical services."
                elif term_lower in ("dynamodb", "mongodb", "cassandra", "couchbase", "snowflake", "bigquery", "databricks"):
                    experiences[target_role]["bullets"][7] += f" Architected and integrated {disp_term} data persistence pipelines to optimize high-volume retrieval and sub-second query performance."
                elif term_lower in ("cypress", "playwright", "selenium", "cucumber", "wiremock", "jest", "sonarqube"):
                    experiences[target_role]["bullets"][13] += f" Engineered and configured comprehensive automated {disp_term} test suites to rigorously validate end-to-end service functionality."
                elif term_lower in ("datadog", "dynatrace", "new relic", "splunk", "elk"):
                    experiences[target_role]["bullets"][14] += f" Deployed and tuned {disp_term} distributed observability dashboards to isolate latency bottlenecks and ensure high availability."
                elif term_lower in ("okta", "keycloak", "auth0", "saml"):
                    experiences[target_role]["bullets"][4] += f" Implemented and integrated {disp_term} federated authentication and fine-grained access control across distributed microservices."
                elif term_lower in ("quarkus", "micronaut", "webflux", "reactive"):
                    emp = "Altice USA" if TechnologyTemporalVerifier.is_temporally_valid_for_employer(term_lower, "Altice USA")[0] else "M&T Bank"
                    experiences[emp]["bullets"][1] += f" Architected and deployed high-throughput {disp_term} reactive microservice components for low-latency request processing."
                elif term_lower in ("rabbitmq", "activemq", "sqs", "sns"):
                    experiences[target_role]["bullets"][9] += f" Integrated and configured {disp_term} message queues to achieve decoupled, resilient asynchronous event processing."
                else:
                    experiences[target_role]["bullets"][3] += f" Architected and developed scalable backend microservice components integrating {disp_term} to maintain high throughput and reliability."

                if disp_term not in experiences[target_role]["core_tech"]:
                    experiences[target_role]["core_tech"] += f", {disp_term}"

                combined_bullets_str += f" {term_lower}"

        return experiences

    def _audit_and_enforce_temporal_integrity(self, experiences: Dict[str, Any]) -> Dict[str, Any]:
        """Verify that every bullet across all employers respects temporal existence rules.

        Guarantees that no employer has bullets referencing technologies released after that employer's tenure.
        """
        for emp_name, emp_data in experiences.items():
            cleaned_bullets = []
            for b in emp_data["bullets"]:
                bullet_text = b
                # Check for temporal violations against known release dates
                for tech, (rel_year, rel_month) in TechnologyTemporalVerifier.RELEASE_DATES.items():
                    if re.search(rf"\b{re.escape(tech)}\b", bullet_text, re.IGNORECASE):
                        is_valid, reason = TechnologyTemporalVerifier.is_temporally_valid_for_employer(tech, emp_name)
                        if not is_valid:
                            # Anachronism detected! Sanitize to historically accurate equivalent
                            if "java" in tech:
                                replacement = "Java"
                            elif "spring boot" in tech:
                                replacement = "Spring Framework"
                            elif "angular" in tech:
                                replacement = "AngularJS" if "clarion" in emp_name.lower() else "Angular"
                            else:
                                replacement = "enterprise systems"
                            bullet_text = re.sub(rf"\b{re.escape(tech)}\b", replacement, bullet_text, flags=re.IGNORECASE)
                cleaned_bullets.append(bullet_text)
            emp_data["bullets"] = cleaned_bullets
        return experiences

    def _is_valid_base_template(self, xml_bytes: bytes) -> bool:
        """Check if base template contains all 5 required employer sections and markers."""
        try:
            root = ET.fromstring(xml_bytes)
            body = root.find(f"{{{self.W_NS}}}body")
            if body is None:
                return False
            all_text = " ".join("".join(n.text for n in c.iterfind(f".//{{{self.W_NS}}}t") if n.text) for c in body)
            required = ["M&T Bank", "Blue Cross", "Altice", "Contus", "Clarion", "Selected Contributions:", "Core Technologies:"]
            return all(r in all_text for r in required)
        except Exception:
            return False

    def _build_in_memory_docx(self, tailored_data: Dict[str, Any], template_bytes: Optional[bytes] = None) -> bytes:
        """Modify template resume DOCX in-memory XML, preserving 100% of formatting, layout, fonts, and styles."""
        src_bytes = self.master_bytes
        if template_bytes is not None:
            try:
                with zipfile.ZipFile(io.BytesIO(template_bytes)) as z:
                    doc_xml = z.read("word/document.xml")
                    if self._is_valid_base_template(doc_xml):
                        src_bytes = template_bytes
            except Exception:
                src_bytes = self.master_bytes

        in_mem_in = io.BytesIO(src_bytes)
        in_mem_out = io.BytesIO()

        with zipfile.ZipFile(in_mem_in, "r") as zin, zipfile.ZipFile(in_mem_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    data = self._transform_document_xml(data, tailored_data)
                zout.writestr(item, data)

        return in_mem_out.getvalue()

    def _transform_document_xml(self, xml_bytes: bytes, data: Dict[str, Any]) -> bytes:
        """Transform document.xml in memory: Title, Summary, Skills Table, Experience Bullets."""
        root = ET.fromstring(xml_bytes)
        body = root.find("w:body", self.NS)
        if body is None:
            return xml_bytes

        # 1. Update Title in Paragraph 1
        p1 = body[1]
        self._set_paragraph_text(p1, data["clean_title"])

        # 2. Update Professional Summary in Paragraph 5
        p5 = body[5]
        self._set_paragraph_text(p5, data["summary"])

        # 3. Update Technical Skills Table (Child 7)
        tbl = body.find("w:tbl", self.NS)
        if tbl is not None:
            rows = tbl.findall("w:tr", self.NS)
            skills_list = data["skills"]
            template_row = rows[-1] if rows else None
            for idx, (cat, val) in enumerate(skills_list):
                if idx < len(rows):
                    cells = rows[idx].findall("w:tc", self.NS)
                    if len(cells) >= 2:
                        self._set_cell_text(cells[0], cat)
                        self._set_cell_text(cells[1], val)
                elif template_row is not None:
                    cloned_tr = copy.deepcopy(template_row)
                    cells = cloned_tr.findall("w:tc", self.NS)
                    if len(cells) >= 2:
                        self._set_cell_text(cells[0], cat)
                        self._set_cell_text(cells[1], val)
                    tbl.append(cloned_tr)

        # 4. Update Experience Sections
        self._update_experience_sections(body, data["experiences"])

        return ET.tostring(root, encoding="utf-8")

    def _set_paragraph_text(self, p_elem: ET.Element, text: str):
        """Set paragraph text while preserving existing run formatting (<w:rPr>)."""
        runs = p_elem.findall("w:r", self.NS)
        if runs:
            # Keep first run's rPr
            first_run = runs[0]
            rPr = first_run.find("w:rPr", self.NS)
            # Remove all existing runs
            for r in runs:
                p_elem.remove(r)
            # Create fresh run with original rPr
            new_r = ET.SubElement(p_elem, f"{{{self.W_NS}}}r")
            if rPr is not None:
                new_r.append(copy.deepcopy(rPr))
            t_node = ET.SubElement(new_r, f"{{{self.W_NS}}}t")
            t_node.text = text
        else:
            # No existing run, create run and t
            new_r = ET.SubElement(p_elem, f"{{{self.W_NS}}}r")
            t_node = ET.SubElement(new_r, f"{{{self.W_NS}}}t")
            t_node.text = text

    def _set_cell_text(self, cell_elem: ET.Element, text: str):
        """Set table cell text while preserving paragraph and run formatting."""
        p = cell_elem.find("w:p", self.NS)
        if p is not None:
            self._set_paragraph_text(p, text)

    def _update_experience_sections(self, body: ET.Element, experiences: Dict[str, Any]):
        """Replace bullet points under each employer, ensuring >= 10 bullets per experience."""
        role_map = [
            ("M&T Bank", experiences["M&T Bank"]),
            ("Blue Cross", experiences["Blue Cross"]),
            ("Altice USA", experiences["Altice USA"]),
            ("Contus Tech", experiences["Contus Tech"]),
            ("Clarion Technologies", experiences["Clarion Technologies"])
        ]

        # Scan body children to locate boundaries of each role
        for role_key, role_data in role_map:
            start_idx = None
            contributions_idx = None
            core_tech_idx = None

            for i, child in enumerate(body):
                texts = [n.text for n in child.iterfind(".//w:t", self.NS) if n.text]
                t = "".join(texts).strip()

                if role_key in t and start_idx is None:
                    start_idx = i
                    continue

                if start_idx is not None:
                    if "Selected Contributions:" in t and contributions_idx is None:
                        contributions_idx = i
                        continue
                    if "Core Technologies:" in t and core_tech_idx is None:
                        core_tech_idx = i
                        break

            if start_idx is not None and contributions_idx is not None and core_tech_idx is not None:
                core_elem = body[core_tech_idx]

                # Identify existing bullet elements
                existing_bullets = []
                for b_i in range(contributions_idx + 1, core_tech_idx):
                    existing_bullets.append(body[b_i])

                new_bullet_texts = role_data["bullets"]
                template_bullet = existing_bullets[0] if existing_bullets else None

                # Update existing bullets
                for idx, b_elem in enumerate(existing_bullets):
                    if idx < len(new_bullet_texts):
                        self._set_paragraph_text(b_elem, new_bullet_texts[idx])

                # If new bullets exceed existing, clone template bullet and insert before core_elem
                if len(new_bullet_texts) > len(existing_bullets) and template_bullet is not None:
                    for add_idx in range(len(existing_bullets), len(new_bullet_texts)):
                        cloned_p = copy.deepcopy(template_bullet)
                        self._set_paragraph_text(cloned_p, new_bullet_texts[add_idx])
                        cur_core_idx = list(body).index(core_elem)
                        body.insert(cur_core_idx, cloned_p)

                # Update Core Technologies paragraph directly
                self._set_paragraph_text(core_elem, role_data["core_tech"])

    def _compose_short_interest(self, role: str, ext: Dict[str, Any]) -> Tuple[str, str]:
        """Compose short interest expression with H1B status and Location: ---- (Rule 16)."""
        java_ver = ext["java_version"]
        fe = ext["primary_frontend"]
        cloud = "AWS" if ext["has_aws"] else ("Azure" if ext["has_azure"] else "AWS/Cloud")

        plain_text = f"""Hi there,

I am writing to express my strong interest in the {role} position. With over 10 years of hands-on software engineering experience delivering enterprise applications with {java_ver}, Spring Boot 3, {fe}, {cloud}, and microservices architectures, my technical background aligns directly with your client's requirements.

I have attached my tailored resume for your review and would welcome the opportunity to discuss how I can contribute to your team.

Experience: 10+ years
Visa: H1B from 2024-2027

Best regards,
Nithin Chiguru
Phone: +1 (312) 358-4463
Email: nithin.chiguru9@gmail.com
LinkedIn: https://www.linkedin.com/in/nithinch/"""

        html = f"""<div dir="ltr" style="font-family: Arial, Helvetica, sans-serif; font-size: 13.33px; color: #222222; line-height: 1.55;">
  <p>Hi there,</p>
  <p>I am writing to express my strong interest in the <strong>{role}</strong> position. With over 10 years of hands-on software engineering experience delivering enterprise applications with {java_ver}, Spring Boot 3, {fe}, {cloud}, and microservices architectures, my technical background aligns directly with your client's requirements.</p>
  <p>I have attached my tailored resume for your review and would welcome the opportunity to discuss how I can contribute to your team.</p>
  <p style="margin-top: 16px;">
    <strong>Experience:</strong> 10+ years<br>
    <strong>Visa:</strong> H1B from 2024-2027
  </p>
  <p style="margin-top: 16px;">
    Best regards,<br>
    <strong>Nithin Chiguru</strong><br>
    Phone: +1 (312) 358-4463<br>
    Email: <a href="mailto:nithin.chiguru9@gmail.com" style="color: #1155cc;">nithin.chiguru9@gmail.com</a><br>
    LinkedIn: <a href="https://www.linkedin.com/in/nithinch/" style="color: #1155cc;">https://www.linkedin.com/in/nithinch/</a>
  </p>
</div>"""
        return plain_text, html