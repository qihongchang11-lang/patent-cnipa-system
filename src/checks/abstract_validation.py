"""
Abstract Validation Checker (Gate E)
Validates abstract format and content according to CNIPA requirements
"""

from typing import List, Dict, Any, Tuple
from core.patent_document import PatentDocument

class AbstractValidationChecker:
    """Validates patent abstract format and content"""

    def __init__(self):
        self.max_length = 300  # CNIPA maximum length in words
        self.min_length = 50   # Minimum reasonable length
        self.required_elements = ['title', 'technical_field', 'summary']

    def check(self, patent_doc: PatentDocument) -> Tuple[bool, float, Dict[str, Any]]:
        """Check abstract validity"""
        details = {
            'length': 0,
            'has_title': False,
            'has_technical_field': False,
            'has_summary': False,
            'missing_elements': [],
            'length_issues': [],
            'recommendations': [],
            'errors': [],
            'warnings': []
        }

        try:
            if not patent_doc.abstract:
                details['errors'].append("Abstract is missing")
                return False, 0.0, details

            abstract = patent_doc.abstract

            # Check required elements
            if abstract.title:
                details['has_title'] = True
            else:
                details['missing_elements'].append('title')

            if abstract.technical_field:
                details['has_technical_field'] = True
            else:
                details['missing_elements'].append('technical_field')

            if abstract.summary:
                details['has_summary'] = True
                details['length'] = len(abstract.summary)
            else:
                details['missing_elements'].append('summary')

            # Check length
            if abstract.summary:
                if len(abstract.summary) > self.max_length:
                    details['length_issues'].append(f"Abstract too long: {len(abstract.summary)} > {self.max_length}")
                elif len(abstract.summary) < self.min_length:
                    details['length_issues'].append(f"Abstract too short: {len(abstract.summary)} < {self.min_length}")

            # Determine pass/fail
            passed = (details['has_title'] and details['has_technical_field'] and
                     details['has_summary'] and len(abstract.summary) <= self.max_length)

            # Calculate score
            score = 0.0
            if details['has_title']:
                score += 0.25
            if details['has_technical_field']:
                score += 0.25
            if details['has_summary']:
                score += 0.25
            if details['length'] > 0 and details['length'] <= self.max_length:
                score += 0.25

            if not passed:
                if details['missing_elements']:
                    details['recommendations'].append(f"Add missing elements: {', '.join(details['missing_elements'])}")
                if details['length_issues']:
                    details['recommendations'].append("Fix abstract length issues")

            return passed, score, details

        except Exception as e:
            details['errors'].append(f"Abstract validation failed: {str(e)}")
            return False, 0.0, details

    def health_check(self) -> bool:
        """Health check for the checker"""
        return True