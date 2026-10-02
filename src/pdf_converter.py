"""Resume Attachment Engine and Dynamic Attachment Namer.

Preserves 100% of the candidate's original document structure, formatting, tables,
margins, and font styling without any alterations or layout changes.
Guarantees ZERO permanent disk storage on the laptop and directly attaches
the best-fit resume with clean, human-like dynamic naming (e.g. Nithin_Chiguru_Lead_AWS_Java_Developer_Resume.docx).
Eliminates Apple Pages errors and Microsoft Word permission popups completely.
"""
import os
import re
from typing import Tuple, Optional


class InMemoryPdfConverter:
    """Direct resume attachment manager and professional dynamic namer."""

    @staticmethod
    def get_dynamic_attachment_name(
        candidate_name: str,
        clean_job_title: str,
        extension: str = "docx"
    ) -> str:
        """Generate a clean, professional, human-like resume attachment filename.
        Example: 'Nithin Chiguru', 'Lead AWS Java Developer', 'docx'
                 -> 'Nithin_Chiguru_Lead_AWS_Java_Developer_Resume.docx'
        """
        cand = re.sub(r'[^a-zA-Z0-9\s]', '', candidate_name).strip()
        cand_part = "_".join(cand.split()) if cand else "Nithin_Chiguru"

        role = re.sub(r'[^a-zA-Z0-9\s]', '', clean_job_title).strip()
        role_part = "_".join(role.split()) if role else "Java_Developer"

        ext = extension.lstrip(".").lower()
        filename = f"{cand_part}_{role_part}_Resume.{ext}"

        # Prevent excessively long filenames (> 75 chars)
        if len(filename) > 75:
            truncated_role = "_".join(role_part.split("_")[:4])
            filename = f"{cand_part}_{truncated_role}_Resume.{ext}"

        return filename

    @classmethod
    def convert_resume_to_memory_pdf(
        cls,
        resume_path: str,
        candidate_name: str = "Nithin Chiguru",
        clean_job_title: str = "Java Full Stack Developer"
    ) -> Tuple[bytes, str]:
        """Attach resume directly in-memory with professional dynamic naming.
        
        Guarantees:
        1. NO Word permission popups and NO Apple Pages automation.
        2. 100% exact original resume document structure, styling, and formatting preserved.
        3. Dynamic professional naming (e.g. Nithin_Chiguru_<Clean_Role>_Resume.docx).
        4. Zero permanent disk storage on laptop.
        """
        if not resume_path or not os.path.exists(resume_path):
            clean_name = cls.get_dynamic_attachment_name(candidate_name, clean_job_title, "docx")
            return b"", clean_name

        # Detect extension (.docx, .pdf, etc.)
        ext = os.path.splitext(resume_path)[1].lstrip(".").lower() or "docx"
        clean_name = cls.get_dynamic_attachment_name(candidate_name, clean_job_title, ext)

        # Read file bytes directly into RAM (zero permanent disk footprint)
        try:
            with open(resume_path, "rb") as f:
                raw_bytes = f.read()
            return raw_bytes, clean_name
        except Exception as e:
            print(f"[Attachment Engine] Error reading resume {resume_path}: {e}")
            return b"", clean_name


# Backwards compatibility alias
ResumeAttachmentManager = InMemoryPdfConverter

