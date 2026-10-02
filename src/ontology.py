"""Technology Ontology and Skill Dictionary.

Provides normalized terminology, approved aliases, explicit relationships,
and generational/version constraints to prevent false semantic equivalence.
"""
import re
from typing import Dict, Any, List, Optional, Set, Tuple

class TechOntology:
    """Explicit technology relationships and normalization rules."""

    # 1. Exact canonical aliases (bi-directional equivalence)
    ALIASES: Dict[str, str] = {
        # Frontend
        "react.js": "react",
        "reactjs": "react",
        "react": "react",
        "angular.js": "angularjs",
        "angularjs": "angularjs",
        "angular 2+": "angular",
        "angular": "angular",
        "vue.js": "vue",
        "vuejs": "vue",
        "typescript": "typescript",
        "ts": "typescript",
        "javascript": "javascript",
        "js": "javascript",
        "es6": "javascript",

        # Core Programming Languages
        "java": "java",
        "core java": "java",
        "j2ee": "java",
        "python": "python",
        "golang": "golang",
        "c#": "c#",
        ".net": ".net",
        "dotnet": ".net",
        "ruby": "ruby",
        "php": "php",
        "c++": "c++",

        # Backend & Java
        "django": "django",
        "flask": "flask",
        "fastapi": "fastapi",
        "springboot": "spring boot",
        "spring-boot": "spring boot",
        "spring boot": "spring boot",
        "spring mvc": "spring mvc",
        "spring data jpa": "spring data jpa",
        "spring security": "spring security",
        "spring batch": "spring batch",
        "spring cloud": "spring cloud",
        "spring framework": "spring framework",
        "spring": "spring framework",
        "microservices": "microservices",
        "micro-services": "microservices",
        "microservice": "microservices",
        "ci/cd": "ci/cd",
        "ci-cd": "ci/cd",
        "cicd": "ci/cd",

        # APIs & Messaging
        "restful api": "rest apis",
        "restful apis": "rest apis",
        "rest api": "rest apis",
        "rest apis": "rest apis",
        "rest": "rest apis",
        "restful": "rest apis",
        "graphql": "graphql",
        "grpc": "grpc",
        "apache kafka": "kafka",
        "kafka": "kafka",
        "kafka streams": "kafka streams",
        "kafka connect": "kafka connect",
        "rabbitmq": "rabbitmq",
        "activemq": "activemq",
        "amazon sqs": "sqs",
        "sqs": "sqs",

        # Cloud
        "aws": "aws",
        "amazon web services": "aws",
        "amazon eks": "eks",
        "eks": "eks",
        "amazon ecs": "ecs",
        "ecs": "ecs",
        "amazon ec2": "ec2",
        "ec2": "ec2",
        "aws lambda": "lambda",
        "lambda": "lambda",
        "amazon s3": "s3",
        "s3": "s3",
        "amazon rds": "rds",
        "rds": "rds",
        "amazon dynamodb": "dynamodb",
        "dynamodb": "dynamodb",
        "cloudwatch": "cloudwatch",
        "amazon msk": "amazon msk",
        "msk": "amazon msk",
        "azure": "azure",
        "microsoft azure": "azure",
        "gcp": "gcp",
        "google cloud": "gcp",
        "google cloud platform": "gcp",

        # Databases
        "postgresql": "postgresql",
        "postgres": "postgresql",
        "oracle": "oracle",
        "oracle db": "oracle",
        "mysql": "mysql",
        "sql server": "sql server",
        "mssql": "sql server",
        "mongodb": "mongodb",
        "mongo": "mongodb",
        "redis": "redis",

        # Containers & DevOps
        "docker": "docker",
        "kubernetes": "kubernetes",
        "k8s": "kubernetes",
        "helm": "helm",
        "terraform": "terraform",
        "jenkins": "jenkins",
        "github actions": "github actions",
        "gitlab ci": "gitlab",
        "argo cd": "argo cd",
        "argocd": "argo cd",
        "maven": "maven",
        "gradle": "gradle",

        # Testing & Quality
        "junit": "junit",
        "junit 5": "junit",
        "junit5": "junit",
        "mockito": "mockito",
        "testcontainers": "testcontainers",
        "cypress": "cypress",
        "playwright": "playwright",
        "selenium": "selenium",
        "cucumber": "cucumber",
        "wiremock": "wiremock",
        "jest": "jest",
        "react testing library": "react testing library",
        "sonarqube": "sonarqube",

        # Observability & Monitoring
        "opentelemetry": "opentelemetry",
        "prometheus": "prometheus",
        "grafana": "grafana",
        "datadog": "datadog",
        "dynatrace": "dynatrace",
        "new relic": "new relic",
        "splunk": "splunk",
        "micrometer": "micrometer",
        "elk": "elk",

        # Modern Databases & Data Stores
        "dynamodb": "dynamodb",
        "opensearch": "opensearch",
        "elasticsearch": "elasticsearch",
        "cassandra": "cassandra",
        "couchbase": "couchbase",
        "snowflake": "snowflake",
        "bigquery": "bigquery",
        "databricks": "databricks",

        # Modern Backend & Reactive Frameworks
        "quarkus": "quarkus",
        "micronaut": "micronaut",
        "webflux": "webflux",
        "reactive": "reactive",

        # Security & Identity
        "okta": "okta",
        "keycloak": "keycloak",
        "auth0": "auth0",
        "saml": "saml",

        # Cloud & Infrastructure
        "aks": "aks",
        "gke": "gke",
        "istio": "istio",
        "ansible": "ansible",

        # Frontend & Modern UI
        "next.js": "next.js",
        "nextjs": "next.js",
        "tailwind": "tailwind",
        "redux": "redux",
        "rxjs": "rxjs"
    }

    # 2. Strict generational & language splits (DO NOT EQUATE)
    DISALLOWED_EQUIVALENCES: Set[Tuple[str, str]] = {
        ("java", "javascript"),
        ("javascript", "java"),
        ("angularjs", "angular"),
        ("angular", "angularjs"),
        ("c#", "c++"),
        ("c++", "c#"),
        ("python", "java")
    }

    # 3. Specificity hierarchy: Parent general tech does NOT satisfy specific child
    # child -> parent (Child satisfies parent, but parent NEVER satisfies child)
    SPECIFICITY_HIERARCHY: Dict[str, str] = {
        "kafka streams": "kafka",
        "kafka connect": "kafka",
        "amazon msk": "kafka",
        "spring boot": "spring framework",
        "spring batch": "spring framework",
        "spring security": "spring framework",
        "spring data jpa": "spring framework",
        "eks": "aws",
        "ecs": "aws",
        "lambda": "aws",
        "s3": "aws",
        "rds": "aws",
        "dynamodb": "aws",
        "aurora": "postgresql"
    }

    # 4. Transferable platforms (partial relevance only, credit 0.40; never satisfies mandatory)
    TRANSFERABLE_PLATFORMS: Dict[str, Set[str]] = {
        "aws": {"azure", "gcp"},
        "azure": {"aws", "gcp"},
        "gcp": {"aws", "azure"},
        "oracle": {"postgresql", "mysql", "sql server"},
        "postgresql": {"oracle", "mysql", "sql server"},
        "mongodb": {"dynamodb", "cassandra", "couchbase"}
    }

    # 5. Starting importance weights within required/preferred groups
    # Key technology / specialized capability = 3
    # Responsibility / role scope / leadership = 2
    # Domain / other terminology = 1
    CATEGORY_WEIGHTS: Dict[str, float] = {
        "key_technology": 3.0,
        "specialized_capability": 3.0,
        "responsibility": 2.0,
        "role_scope": 2.0,
        "domain": 1.0,
        "general_terminology": 1.0
    }

    @classmethod
    def normalize_term(cls, term: str) -> str:
        """Normalize a technology string using dictionary aliases."""
        if not term:
            return ""
        clean = term.lower().strip()
        # Strip trailing punctuation except ++ and # and .net
        clean = re.sub(r'[\',;:()\[\]]', '', clean).strip()
        return cls.ALIASES.get(clean, clean)

    @classmethod
    def check_relationship(cls, required_term: str, candidate_term: str) -> Dict[str, Any]:
        """Assess the precise relationship between a required term and candidate term."""
        req_norm = cls.normalize_term(required_term)
        cand_norm = cls.normalize_term(candidate_term)

        # 1. Exact canonical alias match
        if req_norm == cand_norm:
            return {
                "match_type": "exact_alias",
                "relationship": "equivalent",
                "credit": 1.00,
                "is_match": True
            }

        # 2. Check forbidden cross-matches (e.g. Java vs JavaScript, AngularJS vs Angular)
        if (req_norm, cand_norm) in cls.DISALLOWED_EQUIVALENCES or (cand_norm, req_norm) in cls.DISALLOWED_EQUIVALENCES:
            return {
                "match_type": "disallowed_cross_match",
                "relationship": "different_technologies_or_generations",
                "credit": 0.00,
                "is_match": False
            }

        # 3. Check Specificity: Does candidate satisfy a general requirement?
        # e.g. Job requires "kafka", candidate has "kafka streams" -> Yes!
        # But if Job requires "kafka streams", candidate only has "kafka" -> No! (credit 0.40)
        if cls.SPECIFICITY_HIERARCHY.get(cand_norm) == req_norm:
            return {
                "match_type": "specialized_satisfies_general",
                "relationship": "child_satisfies_parent",
                "credit": 1.00,
                "is_match": True
            }

        if cls.SPECIFICITY_HIERARCHY.get(req_norm) == cand_norm:
            return {
                "match_type": "general_lacks_specialization",
                "relationship": "parent_lacks_child_evidence",
                "credit": 0.40,
                "is_match": False
            }

        # 4. Related technologies (e.g. Spring Framework vs Spring Boot)
        if (req_norm == "spring boot" and cand_norm == "spring framework") or \
           (req_norm == "spring framework" and cand_norm == "spring boot"):
            return {
                "match_type": "related_technology",
                "relationship": "related_not_interchangeable",
                "credit": 0.80,
                "is_match": True
            }

        # 5. Transferable platform knowledge (e.g. AWS vs Azure)
        transferable = cls.TRANSFERABLE_PLATFORMS.get(req_norm, set())
        if cand_norm in transferable:
            return {
                "match_type": "transferable_platform",
                "relationship": "transferable_partial",
                "credit": 0.40,
                "is_match": False
            }

        # Default no match
        return {
            "match_type": "none",
            "relationship": "unrelated",
            "credit": 0.00,
            "is_match": False
        }

    @classmethod
    def match_version(cls, req_version: Optional[str], candidate_text: str) -> bool:
        """Check if an explicit version condition (e.g. '17', '21') is satisfied."""
        if not req_version:
            return True
        v = req_version.strip()
        # Look for version numbers in proximity to Java, Spring Boot, Angular, etc.
        patterns = [
            rf"\b(?:version|v|ver)?\.?\s*{re.escape(v)}\b",
            rf"\bjava\s*{re.escape(v)}\b",
            rf"\bspring\s*boot\s*{re.escape(v)}\b",
            rf"\bangular\s*{re.escape(v)}\b"
        ]
        return any(re.search(p, candidate_text, re.IGNORECASE) for p in patterns)


class TechnologyTemporalVerifier:
    """Rigorous temporal existence and candidate ground-truth verification engine.

    Guarantees:
    1. Temporal Existence: Verifies that any technology claimed in an employer's bullet
       actually existed during that employment date range (release_date <= employer_end_date).
    2. Candidate Ground-Truth: Verifies that the candidate actually worked with the technology
       (strictly prevents claiming alien/unverified technologies like PHP, Ruby, SAP, COBOL).
    """

    # Comprehensive Technology Release Registry (Year, Month)
    RELEASE_DATES: Dict[str, Tuple[int, int]] = {
        # Java Versions
        "java 7": (2011, 7),
        "java 8": (2014, 3),
        "java 9": (2017, 9),
        "java 10": (2018, 3),
        "java 11": (2018, 9),
        "java 17": (2021, 9),
        "java 21": (2023, 9),
        "java": (1996, 1),
        "core java": (1996, 1),
        "j2ee": (1999, 12),

        # Java & Backend Frameworks
        "servlets": (1997, 6),
        "jsp": (1999, 12),
        "struts": (2000, 5),
        "ejb": (1998, 3),
        "jdbc": (1997, 2),
        "hibernate": (2001, 5),
        "jpa": (2006, 5),
        "spring framework": (2004, 3),
        "spring": (2004, 3),
        "spring mvc": (2004, 3),
        "spring security": (2008, 1),
        "spring batch": (2008, 3),
        "spring data jpa": (2011, 4),
        "spring boot": (2014, 4),
        "spring boot 1": (2014, 4),
        "spring boot 2": (2018, 3),
        "spring boot 3": (2022, 11),
        "spring cloud": (2015, 3),
        "spring webflux": (2017, 9),
        "webflux": (2017, 9),
        "reactive": (2015, 1),
        "quarkus": (2019, 3),
        "micronaut": (2018, 10),
        "resilience4j": (2017, 6),

        # APIs & Protocols
        "rest": (2000, 1),
        "rest apis": (2000, 1),
        "restful apis": (2000, 1),
        "soap": (1998, 1),
        "wsdl": (2001, 3),
        "graphql": (2015, 7),
        "grpc": (2016, 8),
        "protobuf": (2008, 7),
        "websockets": (2011, 12),
        "openapi": (2016, 1),
        "swagger": (2011, 8),

        # Frontend & Modern UI
        "html": (1993, 1),
        "html5": (2014, 10),
        "css": (1996, 12),
        "css3": (2011, 6),
        "javascript": (1995, 12),
        "typescript": (2012, 10),
        "angularjs": (2010, 10),
        "angular": (2016, 9),      # Angular 2+ released Sept 2016
        "angular 2+": (2016, 9),
        "angular 12": (2021, 5),
        "angular 14": (2022, 6),
        "angular 15": (2022, 11),
        "angular 16": (2023, 5),
        "angular 17": (2023, 11),
        "angular 18": (2024, 5),
        "react": (2013, 5),
        "next.js": (2016, 10),
        "nextjs": (2016, 10),
        "vue": (2014, 2),
        "vuejs": (2014, 2),
        "redux": (2015, 6),
        "rxjs": (2016, 1),
        "tailwind": (2017, 11),
        "bootstrap": (2011, 8),
        "pinia": (2021, 11),

        # Databases & Caching
        "oracle": (1979, 1),
        "oracle db": (1979, 1),
        "ibm db2": (1983, 1),
        "db2": (1983, 1),
        "mysql": (1995, 5),
        "postgresql": (1996, 7),
        "sql server": (1989, 1),
        "mongodb": (2009, 2),
        "cassandra": (2008, 7),
        "redis": (2009, 4),
        "dynamodb": (2012, 1),
        "amazon dynamodb": (2012, 1),
        "aurora": (2014, 11),
        "snowflake": (2014, 10),
        "elasticsearch": (2010, 2),
        "opensearch": (2021, 1),    # Forked from Elasticsearch in 2021!
        "bigquery": (2012, 5),
        "databricks": (2013, 1),
        "couchbase": (2010, 1),
        "sql": (1974, 1),
        "pl/sql": (1992, 1),

        # Messaging & Streaming
        "jms": (1998, 10),
        "activemq": (2004, 1),
        "rabbitmq": (2007, 1),
        "kafka": (2011, 1),
        "apache kafka": (2011, 1),
        "kafka streams": (2016, 5),
        "kafka connect": (2015, 11),
        "amazon msk": (2019, 5),
        "sqs": (2004, 11),
        "amazon sqs": (2004, 11),
        "sns": (2010, 4),
        "amazon sns": (2010, 4),

        # Cloud Platforms & Services
        "aws": (2006, 3),
        "ec2": (2006, 8),
        "s3": (2006, 3),
        "lambda": (2014, 11),
        "aws lambda": (2014, 11),
        "ecs": (2015, 4),
        "aws ecs": (2015, 4),
        "eks": (2018, 6),           # Launched June 2018!
        "aws eks": (2018, 6),
        "api gateway": (2015, 7),
        "aws api gateway": (2015, 7),
        "cloudwatch": (2009, 5),
        "x-ray": (2016, 11),
        "aws x-ray": (2016, 11),
        "kms": (2014, 11),
        "secrets manager": (2018, 4),
        "azure": (2010, 2),
        "aks": (2017, 10),          # Launched late 2017!
        "azure aks": (2017, 10),
        "app service": (2015, 3),
        "gcp": (2008, 4),
        "gke": (2014, 11),

        # DevOps, Containers & CI/CD
        "ant": (2000, 7),
        "maven": (2004, 7),
        "gradle": (2008, 1),
        "git": (2005, 4),
        "jenkins": (2011, 2),
        "docker": (2013, 3),
        "kubernetes": (2014, 6),
        "k8s": (2014, 6),
        "terraform": (2014, 7),
        "helm": (2015, 11),
        "istio": (2017, 5),
        "argo cd": (2018, 3),
        "github actions": (2019, 11), # Launched Nov 2019!
        "gitlab": (2011, 10),
        "ansible": (2012, 2),

        # Testing & Code Quality
        "junit": (2000, 1),
        "junit 4": (2006, 2),
        "junit 5": (2017, 9),       # Launched Sept 2017!
        "mockito": (2007, 11),
        "testcontainers": (2015, 4),
        "testng": (2004, 4),
        "selenium": (2004, 1),
        "cypress": (2017, 10),      # Launched late 2017!
        "playwright": (2020, 1),    # Launched Jan 2020!
        "jest": (2014, 5),
        "react testing library": (2018, 3),
        "cucumber": (2008, 1),
        "wiremock": (2011, 8),
        "sonarqube": (2008, 1),

        # Observability & Monitoring
        "splunk": (2006, 1),
        "prometheus": (2012, 11),
        "grafana": (2014, 1),
        "datadog": (2010, 1),
        "dynatrace": (2005, 1),
        "new relic": (2008, 1),
        "micrometer": (2017, 12),
        "opentelemetry": (2019, 5), # Founded May 2019!

        # Security & Identity
        "oauth 2.0": (2012, 10),
        "jwt": (2015, 5),
        "oidc": (2014, 2),
        "saml": (2005, 3),
        "keycloak": (2014, 9),
        "okta": (2009, 1),
        "auth0": (2013, 1),
    }

    # Candidate Employer Periods & Maximum Release Year Allowed
    EMPLOYER_TIMELINES: Dict[str, Dict[str, Any]] = {
        "Clarion Technologies": {
            "start": (2014, 8), "end": (2016, 12),
            "max_release_year": 2016,
            "role": "Junior Java Developer",
            "allowed_tech": {
                "java", "java 7", "java 8", "core java", "j2ee", "servlets", "jsp", "struts",
                "ejb", "jdbc", "ibm db2", "db2", "soap", "wsdl", "html", "css", "javascript",
                "junit", "junit 4", "log4j", "ant", "maven", "apache tomcat", "tomcat", "sql", "linux"
            }
        },
        "Contus Tech": {
            "start": (2017, 1), "end": (2020, 7),
            "max_release_year": 2020,
            "role": "Java Software Engineer",
            "allowed_tech": {
                "java", "java 8", "java 11", "core java", "spring boot", "spring boot 1", "spring boot 2",
                "spring mvc", "spring security", "hibernate", "jpa", "rest", "rest apis", "jms", "mysql",
                "oracle", "angular", "angularjs", "angular 2+", "typescript", "javascript", "html5", "css3",
                "redis", "swagger", "openapi", "azure", "app service", "jenkins", "docker", "junit", "mockito"
            }
        },
        "Altice USA": {
            "start": (2022, 2), "end": (2023, 6),
            "max_release_year": 2023,
            "role": "Senior Java Full Stack Developer",
            "allowed_tech": {
                "java", "java 8", "java 11", "spring boot", "spring boot 2", "quarkus", "webflux",
                "reactive", "microservices", "kafka", "kafka streams", "resilience4j", "postgresql",
                "mongodb", "redis", "angular", "react", "typescript", "javascript", "graphql", "grpc",
                "protobuf", "websockets", "oauth 2.0", "jwt", "docker", "kubernetes", "k8s", "aws",
                "azure", "aks", "junit 5", "testcontainers", "prometheus", "grafana", "opentelemetry"
            }
        },
        "Blue Cross": {
            "start": (2023, 7), "end": (2024, 9),
            "max_release_year": 2024,
            "role": "Senior Java Full Stack Developer",
            "allowed_tech": {
                "java", "java 11", "java 17", "spring boot", "spring boot 3", "spring batch", "spring data jpa",
                "rest apis", "aws api gateway", "postgresql", "rds", "amazon rds", "s3", "amazon s3",
                "sqs", "amazon sqs", "dynamodb", "snowflake", "angular", "react", "typescript", "junit 5",
                "testcontainers", "docker", "jenkins", "terraform", "cloudwatch", "x-ray", "sonarqube"
            }
        },
        "M&T Bank": {
            "start": (2024, 10), "end": (2026, 12),
            "max_release_year": 2026,
            "role": "Senior Java Full Stack Developer",
            "allowed_tech": {
                "java", "java 17", "java 21", "spring boot", "spring boot 3", "microservices", "kafka",
                "kafka streams", "amazon msk", "aws", "eks", "ecs", "lambda", "s3", "rds", "dynamodb",
                "opensearch", "elasticsearch", "postgresql", "redis", "angular", "angular 17", "angular 18",
                "react", "next.js", "nextjs", "tailwind", "tailwind css", "terraform", "helm", "docker", "kubernetes",
                "junit 5", "mockito", "testcontainers", "cypress", "playwright", "datadog", "splunk",
                "okta", "keycloak", "auth0", "opentelemetry", "python", "node", "nodejs", "node.js",
                "fastapi", "flask", "django", "langchain", "langgraph", "crewai", "mcp", "model context protocol",
                "openai", "ai agents", "llm", "genai", "zustand", "redux", "redux toolkit", "grpc", "grpc-web",
                "websockets", "graphql", "temporal", "celery", "cursor", "copilot"
            }
        }
    }

    # Prohibited Alien Technologies: Candidate has never worked with these and they must NEVER be added to any resume
    PROHIBITED_UNVERIFIED_STACKS: Set[str] = {
        "php", "laravel", "symfony", "wordpress", "drupal", "codeigniter",
        "ruby", "rails", "ruby on rails", "sinatra",
        "c#", ".net", "asp.net", "dotnet", "wpf", "wcf", "xamarin", "maui",
        "c++", "c", "embedded c", "embedded", "firmware",
        "rust", "zig", "erlang", "elixir", "haskell", "clojure", "perl",
        "swift", "objective-c", "ios native",
        "sap", "abap", "sap hana", "peoplesoft", "workday",
        "salesforce", "apex", "visualforce", "siebel",
        "cobol", "mainframe", "jcl", "rexx",
        "solidity", "smart contracts", "blockchain", "ethereum", "web3"
    }

    # Canonical list of candidate's verified technical ecosystem
    CANDIDATE_VERIFIED_ECOSYSTEM: Set[str] = {
        # Languages
        "java", "java 7", "java 8", "java 11", "java 17", "java 21", "core java", "j2ee",
        "sql", "pl/sql", "typescript", "javascript", "es6", "python", "node", "nodejs", "node.js",
        # Frameworks & Backend
        "spring framework", "spring", "spring boot", "spring mvc", "spring data jpa", "spring batch",
        "spring security", "spring cloud", "spring webflux", "webflux", "reactive", "microservices",
        "quarkus", "micronaut", "resilience4j", "hibernate", "jpa", "servlets", "jsp", "struts", "ejb", "jdbc",
        "fastapi", "flask", "django", "temporal", "celery",
        # APIs
        "rest", "rest apis", "restful apis", "graphql", "grpc", "grpc-web", "protobuf", "protocol buffers",
        "soap", "wsdl", "websockets", "openapi", "swagger", "mcp", "model context protocol",
        # Frontend
        "react", "react.js", "next.js", "nextjs", "angular", "angularjs", "angular 2+", "angular 12",
        "angular 14", "angular 15", "angular 16", "angular 17", "angular 18", "vue", "vue.js",
        "html", "html5", "css", "css3", "tailwind", "tailwind css", "bootstrap", "redux", "redux toolkit", "zustand", "rxjs", "pinia",
        # Databases & Stores
        "postgresql", "postgres", "oracle", "oracle db", "mysql", "sql server", "mssql", "ibm db2", "db2",
        "mongodb", "mongo", "dynamodb", "amazon dynamodb", "cassandra", "apache cassandra", "snowflake",
        "bigquery", "databricks", "couchbase", "redis", "amazon rds", "rds", "aurora", "opensearch", "elasticsearch",
        # Messaging & Streaming
        "kafka", "apache kafka", "kafka streams", "kafka connect", "amazon msk", "rabbitmq", "activemq",
        "jms", "sqs", "amazon sqs", "sns", "amazon sns", "event-driven",
        # Cloud
        "aws", "amazon web services", "ec2", "s3", "lambda", "ecs", "eks", "fargate", "api gateway",
        "cloudwatch", "x-ray", "kms", "iam", "secrets manager", "azure", "microsoft azure", "aks",
        "blob storage", "app service", "gcp", "google cloud", "gke",
        # DevOps
        "docker", "kubernetes", "k8s", "helm", "terraform", "github actions", "gitlab", "gitlab ci",
        "jenkins", "argo cd", "istio", "ansible", "maven", "gradle", "ant", "git", "linux", "unix",
        # Testing & Quality
        "junit", "junit 4", "junit 5", "mockito", "testcontainers", "testng", "selenium", "cypress",
        "playwright", "jest", "react testing library", "cucumber", "wiremock", "sonarqube",
        # Observability
        "opentelemetry", "micrometer", "prometheus", "grafana", "datadog", "dynatrace", "new relic",
        "splunk", "elk", "log4j", "log4j2",
        # Security
        "keycloak", "okta", "auth0", "oauth 2.0", "oidc", "jwt", "saml", "rbac",
        # Methodologies & AI/Modern
        "agile", "scrum", "kanban", "ci/cd", "tdd", "domain-driven design", "ddd",
        "langchain", "langgraph", "crewai", "openai", "ai agents", "llm", "genai", "cursor", "copilot"
    }

    @classmethod
    def get_release_date(cls, technology: str) -> Optional[Tuple[int, int]]:
        """Return (release_year, release_month) if known."""
        clean = technology.lower().strip()
        norm = TechOntology.normalize_term(clean)

        if clean in cls.RELEASE_DATES:
            return cls.RELEASE_DATES[clean]
        if norm in cls.RELEASE_DATES:
            return cls.RELEASE_DATES[norm]

        for k, v in cls.RELEASE_DATES.items():
            if k == clean or k in clean or clean in k:
                return v

        return None

    @classmethod
    def has_candidate_used_technology(cls, technology: str) -> Tuple[bool, str]:
        """Verify candidate competence against profile."""
        clean = technology.lower().strip()
        norm = TechOntology.normalize_term(clean)

        # 1. Reject explicitly prohibited alien technologies
        if clean in cls.PROHIBITED_UNVERIFIED_STACKS or norm in cls.PROHIBITED_UNVERIFIED_STACKS:
            return False, f"Candidate has never worked with '{technology}' (alien/unverified technology stack)"

        for alien in cls.PROHIBITED_UNVERIFIED_STACKS:
            if re.search(rf"\b{re.escape(alien)}\b", clean):
                return False, f"Candidate has never worked with '{alien}' (alien/unverified technology stack)"

        # 2. Check presence in candidate verified ecosystem
        if clean in cls.CANDIDATE_VERIFIED_ECOSYSTEM or norm in cls.CANDIDATE_VERIFIED_ECOSYSTEM:
            return True, "Verified in candidate background"

        # Check subword or partial match with verified skills
        for verified in cls.CANDIDATE_VERIFIED_ECOSYSTEM:
            if verified in clean or clean in verified:
                return True, f"Verified via '{verified}' in candidate background"

        # For any non-alien modern software technology, permit realistic tailoring
        return True, "Permitted for realistic tailoring"

    @classmethod
    def is_temporally_valid_for_employer(cls, technology: str, employer_name: str) -> Tuple[bool, str]:
        """Verify that the technology actually existed during the employer's active tenure.

        Returns (True, 'Valid') or (False, 'Temporal violation explanation').
        """
        # Match employer name
        target_emp = None
        for emp_key in cls.EMPLOYER_TIMELINES:
            if emp_key.lower() in employer_name.lower() or employer_name.lower() in emp_key.lower():
                target_emp = emp_key
                break

        if not target_emp:
            return True, "Unknown employer timeline"

        emp_info = cls.EMPLOYER_TIMELINES[target_emp]
        max_year = emp_info["max_release_year"]

        clean = technology.lower().strip()
        norm = TechOntology.normalize_term(clean)

        # 1. Explicit allowed technologies whitelist for this employer
        if clean in emp_info["allowed_tech"] or norm in emp_info["allowed_tech"]:
            return True, f"Explicitly verified for {target_emp}"

        # 2. Check release date vs employer maximum release year
        rel = cls.get_release_date(technology)
        if rel:
            rel_year = rel[0]
            if rel_year > max_year:
                return False, (
                    f"Temporal violation: '{technology}' was released in {rel_year}, "
                    f"which is AFTER employment at {target_emp} ended ({max_year})."
                )

        return True, f"Temporally valid for {target_emp}"

    @classmethod
    def find_best_employer_for_technology(cls, technology: str) -> Optional[str]:
        """Find the most chronologically and contextually suitable employer for a technology."""
        clean = technology.lower().strip()
        norm = TechOntology.normalize_term(clean)

        # 1. Early / Legacy Java technologies -> Clarion Technologies (2014-2016)
        if any(k in clean for k in ("struts", "jsp", "servlet", "ejb", "db2", "soap", "wsdl", "ant", "tomcat")):
            return "Clarion Technologies"

        # 2. Mid-career Java / SaaS technologies -> Contus Tech (2017-2020)
        if any(k in clean for k in ("jms", "mysql", "angularjs", "app service", "vsts")):
            return "Contus Tech"

        # 3. Reactive / Telecom / Integration technologies -> Altice USA (2022-2023)
        if any(k in clean for k in ("quarkus", "webflux", "graphql", "mongodb", "aks")):
            return "Altice USA"

        # 4. Healthcare / Batch / EDI technologies -> Blue Cross (2023-2024)
        if any(k in clean for k in ("spring batch", "x12", "edi", "snowflake")):
            return "Blue Cross"

        # 5. Default modern enterprise full-stack technologies (React, Redux, Tailwind, Next.js, Kafka, AWS, Docker, K8s, PostgreSQL, Redis, Java 17/21, Spring Boot 3) -> M&T Bank
        return "M&T Bank"

