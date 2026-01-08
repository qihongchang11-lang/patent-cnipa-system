"""
Background Leakage Checker (Gate F)
Checks for information leakage from background section to other sections
"""

from typing import List, Dict, Any, Tuple
from core.patent_document import PatentDocument

class BackgroundLeakageChecker:
    """Checks for background information leakage into invention sections"""

    def __init__(self):
        self.leakage_threshold = 0.3  # Maximum 30% overlap allowed

    def check(self, patent_doc: PatentDocument) -> Tuple[bool, float, Dict[str, Any]]:
        """Check for background information leakage"""
        details = {
            'background_length': 0,
            'leakage_issues': [],
            'overlap_scores': {},
            'leaked_content': [],
            'recommendations': [],
            'errors': [],
            'warnings': []
        }

        try:
            if not patent_doc.specification:
                details['errors'].append("Specification is missing")
                return False, 0.0, details

            spec = patent_doc.specification
            background_text = spec.background_art.lower() if spec.background_art else ""

            if not background_text:
                details['warnings'].append("Background section is empty")
                return True, 1.0, details

            details['background_length'] = len(background_text)

            # Check leakage into other sections
            sections_to_check = []

            if spec.invention_content:
                sections_to_check.append(('invention_content', spec.invention_content))

            if spec.embodiments:
                sections_to_check.append(('embodiments', spec.embodiments))

            if patent_doc.claims and patent_doc.claims.content:
                sections_to_check.append(('claims', patent_doc.claims.content))

            total_leakage = 0
            checked_sections = 0

            for section_name, section_text in sections_to_check:
                overlap_score = self._calculate_overlap(background_text, section_text.lower())
                details['overlap_scores'][section_name] = overlap_score

                if overlap_score > self.leakage_threshold:
                    details['leakage_issues'].append({
                        'section': section_name,
                        'overlap_score': overlap_score,
                        'severity': 'high' if overlap_score > 0.5 else 'medium'
                    })
                    total_leakage += overlap_score
                    checked_sections += 1

            # Calculate overall score
            if checked_sections > 0:
                average_leakage = total_leakage / checked_sections
                score = max(0.0, 1.0 - average_leakage)
            else:
                score = 1.0

            passed = len(details['leakage_issues']) == 0

            if not passed:
                details['recommendations'].append("Reduce background information in invention sections")
                details['recommendations'].append("Focus invention content on novel aspects")

            return passed, score, details

        except Exception as e:
            details['errors'].append(f"Background leakage check failed: {str(e)}")
            return False, 0.0, details

    def _calculate_overlap(self, background: str, section: str) -> float:
        """Calculate overlap between background and section text"""
        if not background or not section:
            return 0.0

        # Simple word-based overlap
        background_words = set(background.split())
        section_words = set(section.split())

        if not background_words:
            return 0.0

        overlap = len(background_words.intersection(section_words))
        return overlap / len(background_words)

    def health_check(self) -> bool:
        """Health check for the checker"""
        return True