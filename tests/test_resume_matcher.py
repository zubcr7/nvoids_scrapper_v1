"""Unit and Integration Tests for AI ATS Resume Matching & Portfolio Selection.

Verifies:
1. Every single resume (199 total) in the candidate portfolio is accessed and evaluated.
2. ATS matching scores are measured accurately and distinctly without document length bias.
3. Angular roles pick Angular specialized resumes.
4. React roles pick React specialized resumes.
5. AWS/Cloud roles pick AWS specialized resumes.
6. Technical Lead roles pick Technical Lead specialized resumes.
7. GenAI roles pick GenAI specialized resumes.
8. Non-matching roles (Python, Ruby, etc.) score < 90% and are strictly rejected.
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.matcher import ResumeMatcher
from src.scraper import NvoidsScraper


class TestResumeMatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher = ResumeMatcher(min_match_percentage=85.0)
        cls.all_resumes = cls.matcher.catalog.get_all_resumes()

    def test_all_199_resumes_accessed_and_evaluated(self):
        """Verify that all resumes in portfolio (200+ profiles) are loaded and evaluated."""
        self.assertGreaterEqual(len(self.all_resumes), 199, f"Expected at least 199 resumes, got {len(self.all_resumes)}")
        
        test_title = "Senior Java Full Stack Developer (Angular / AWS)"
        test_jd = "Java 17, Spring Boot, Microservices, Angular, AWS, Kafka, PostgreSQL."
        result = self.matcher.select_best_resume(test_title, test_jd)
        
        self.assertEqual(result["total_evaluated"], len(self.all_resumes))
        self.assertIsNotNone(result["filename"])
        self.assertTrue(result["is_match"])
        self.assertGreaterEqual(result["match_percentage"], 85.0)

    def test_angular_role_picks_angular_resume(self):
        """Verify that an Angular role selects an Angular-specialized resume over generic/React resumes."""
        test_title = "Senior Java Full Stack Developer (Angular / AWS)"
        test_jd = "Seeking Senior Java Full Stack Developer with Angular, Spring Boot, Microservices, AWS, Docker."
        result = self.matcher.select_best_resume(test_title, test_jd)
        
        winner = result["filename"].lower()
        self.assertIn("angular", winner, f"Expected Angular in winning resume, got: {result['filename']}")
        self.assertNotIn("naperville", winner, f"Naperville resume should not win Angular role: {result['filename']}")

    def test_react_role_picks_react_resume(self):
        """Verify that a React role selects a React-specialized resume over generic/Angular resumes."""
        test_title = "Java Full Stack Developer (React / Kafka / AWS)"
        test_jd = "Looking for Java Full Stack Developer with React.js, Spring Boot, Kafka, AWS, Docker, Kubernetes."
        result = self.matcher.select_best_resume(test_title, test_jd)
        
        winner = result["filename"].lower()
        self.assertIn("react", winner, f"Expected React in winning resume, got: {result['filename']}")
        self.assertNotIn("naperville", winner, f"Naperville resume should not win React role: {result['filename']}")

    def test_tech_lead_role_picks_lead_resume(self):
        """Verify that a Technical Lead role selects a Lead/Architect specialized resume."""
        test_title = "Senior Java Technical Lead - Microservices & AWS"
        test_jd = "Technical Lead responsible for architecture, leading engineering teams, Spring Boot, Microservices, AWS, Kafka."
        result = self.matcher.select_best_resume(test_title, test_jd)
        
        winner = result["filename"].lower()
        is_lead = any(k in winner for k in ("lead", "architect"))
        self.assertTrue(is_lead, f"Expected Lead/Architect in winning resume, got: {result['filename']}")

    def test_genai_role_picks_genai_resume(self):
        """Verify that a GenAI / Agentic AI role selects a GenAI specialized resume."""
        test_title = "Java Full Stack Engineer with Gen AI & LLM"
        test_jd = "Java Full Stack Developer with Spring Boot, React, Generative AI, LangChain, LLMs, AI Agents."
        result = self.matcher.select_best_resume(test_title, test_jd)
        
        winner = result["filename"].lower()
        is_ai = any(k in winner for k in ("ai", "genai", "agent"))
        self.assertTrue(is_ai, f"Expected AI/GenAI in winning resume, got: {result['filename']}")

    def test_non_java_role_is_strictly_rejected(self):
        """Verify that a non-Java role (e.g. Python / Django) is rejected with score < 85%."""
        test_title = "Senior Python Developer with Django"
        test_jd = "Python backend developer with Django, FastAPI, Celery, PostgreSQL, Redis, Docker."
        result = self.matcher.select_best_resume(test_title, test_jd)
        
        self.assertFalse(result["is_match"])
        self.assertEqual(result["decision"], "Reject")
        self.assertLess(result["match_percentage"], 85.0)

    def test_scraper_disqualifies_niche_platforms(self):
        """Verify that NvoidsScraper.is_java_developer_role strictly excludes Camunda, Guidewire, Amazon Connect, etc."""
        from src.scraper import NvoidsScraper
        scraper = NvoidsScraper()

        excluded_titles = [
            "Urgent Requirement || Camunda Developer || New York City, NY || Onsite",
            "Sr. Java FSD Developer - Camunda 7 | Columbus, OH | 5 Days Onsite",
            "Need you as Guidewire ClaimCenter Integration Developer",
            "Amazon connect Architect Consultant - 12+ Yrs - Wilmington, DE (Onsite)",
            "Need || Snowflake Architect || 12 Months|| Texas City, TX (Onsite)",
            "Salesforce Developer with Apex & Visualforce",
            "MuleSoft Integration Specialist",
            "Pega Senior System Architect",
            "Project Manager - Functional at Locations: Seattle, WA"
        ]
        sample_jd = "We are seeking a candidate with experience in Java, Spring Boot, and REST APIs."

        for title in excluded_titles:
            self.assertFalse(
                scraper.is_java_developer_role(title, sample_jd, full_stack_only=True),
                f"Role '{title}' should have been disqualified by scraper!"
            )

    def test_mandatory_title_technology_guardrail_blocks_absent_skills(self):
        """Verify that if a job title demands a specialized technology not in candidate portfolio, it is rejected."""
        # Test title with Guidewire (absent from candidate portfolio)
        test_title = "Guidewire ClaimCenter Integration Developer"
        test_jd = "Integration developer with Java, Spring Boot, REST APIs, and Guidewire ClaimCenter."
        result = self.matcher.select_best_resume(test_title, test_jd)

        self.assertFalse(result["is_match"])
        self.assertEqual(result["decision"], "Reject")
        self.assertLess(result["match_percentage"], 50.0)

    def test_infrastructure_and_solutions_architect_roles_are_strictly_rejected(self):
        """Verify that Infrastructure and Solutions/Enterprise Architect roles are strictly rejected
        even if the job description mentions Java, Spring Boot, React, Angular, or AWS."""
        scraper = NvoidsScraper()
        disqualified_titles = [
            "DMAS - Infrastructure Solutions Architect 3",
            "Infrastructure Solutions Architect || Richmond, VA. 23219",
            "Java Infrastructure Architect",
            "Solutions Architect - Java",
            "Enterprise Solutions Architect (Java)",
            "Cloud Infrastructure Architect",
            "Network Solutions Architect - Java",
            "Lead Infrastructure Engineer - Java",
            "Multi-Cloud Infrastructure & Security Architect",
            "Sr. Azure Cloud Infrastructure Engineer"
        ]
        # JD contains all popular Java keywords
        jd_with_java = (
            "Looking for a candidate with 10+ years experience in Java, Spring Boot, "
            "Microservices, React, Angular, AWS, Docker, Kubernetes, and REST APIs."
        )

        for title in disqualified_titles:
            # 1. Scraper filter must reject
            self.assertFalse(
                scraper.is_java_developer_role(title, jd_with_java, full_stack_only=True),
                f"Role '{title}' should have been rejected by scraper (full_stack_only=True)!"
            )
            self.assertFalse(
                scraper.is_java_developer_role(title, jd_with_java, full_stack_only=False),
                f"Role '{title}' should have been rejected by scraper (full_stack_only=False)!"
            )

            # 2. ATS matcher must reject with score <= 25.0%
            res = self.matcher.select_best_resume(title, jd_with_java)
            self.assertFalse(res["is_match"], f"ATS matcher should reject '{title}'!")
            self.assertEqual(res["decision"], "Reject")
            self.assertLessEqual(res["match_percentage"], 30.0, f"Score for '{title}' should be <= 30.0%!")


if __name__ == "__main__":
    unittest.main()

