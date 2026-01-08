"""
Term Consistency Checker (Gate C)
Checks for consistent terminology usage across the patent document
"""

import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from core.patent_document import PatentDocument

class TermConsistencyChecker:
    """Checks terminology consistency across patent sections"""

    def __init__(self):
        self.consistency_threshold = 0.8

    def check(self, patent_doc: PatentDocument) -> Tuple[bool, float, Dict[str, Any]]:
        """Check term consistency across sections"""
        details = {
            'total_terms': 0,
            'consistent_terms': 0,
            'inconsistent_terms': [],
            'term_usage': {},
            'recommendations': [],
            'errors': [],
            'warnings': []
        }

        try:
            # Extract terms from each section
            sections = self._extract_section_terms(patent_doc)

            # Analyze consistency
            consistency_issues = []
            consistent_count = 0
            total_terms = 0

            for term, usage in sections.items():
                total_terms += 1
                if self._is_term_consistent(usage):
                    consistent_count += 1
                else:
                    consistency_issues.append({
                        'term': term,
                        'usage': usage,
                        'issue': self._get_consistency_issue(usage)
                    })

            details['total_terms'] = total_terms
            details['consistent_terms'] = consistent_count
            details['inconsistent_terms'] = consistency_issues
            details['term_usage'] = sections

            # Calculate score
            if total_terms > 0:
                score = consistent_count / total_terms
            else:
                score = 1.0

            passed = score >= self.consistency_threshold

            if not passed:
                details['recommendations'].append("Standardize terminology across all sections")
                details['recommendations'].append("Use consistent terms for the same concepts")

            return passed, score, details

        except Exception as e:
            details['errors'].append(f"Term consistency check failed: {str(e)}")
            return False, 0.0, details

    def _extract_section_terms(self, patent_doc: PatentDocument) -> Dict[str, Dict[str, int]]:
        """Extract key terms from each section"""
        terms = defaultdict(lambda: {'specification': 0, 'claims': 0, 'abstract': 0, 'disclosure': 0})

        # Extract from specification
        if patent_doc.specification:
            spec_terms = self._extract_terms(patent_doc.specification.content)
            for term in spec_terms:
                terms[term]['specification'] += 1

        # Extract from claims
        if patent_doc.claims:
            claims_terms = self._extract_terms(patent_doc.claims.content)
            for term in claims_terms:
                terms[term]['claims'] += 1

        # Extract from abstract
        if patent_doc.abstract:
            abstract_terms = self._extract_terms(patent_doc.abstract.content)
            for term in abstract_terms:
                terms[term]['abstract'] += 1

        # Extract from disclosure
        if patent_doc.disclosure:
            disclosure_terms = self._extract_terms(patent_doc.disclosure.content)
            for term in disclosure_terms:
                terms[term]['disclosure'] += 1

        return dict(terms)

    def _extract_terms(self, text: str) -> List[str]:
        """Extract key technical terms from text"""
        # Simple term extraction - look for technical patterns
        terms = []

        # Look for quoted terms
        quoted_terms = re.findall(r'[""](.+?)[""]', text)
        terms.extend(quoted_terms)

        # Look for terms after "所述"
        suoshu_terms = re.findall(r'所述(.+?)[，。；]', text)
        terms.extend(suoshu_terms)

        # Look for terms after "包括"
        baokuo_terms = re.findall(r'包括(.+?)[，。；]', text)
        terms.extend(baokuo_terms)

        # Clean and filter terms
        cleaned_terms = []
        for term in terms:
            term = term.strip()
            if len(term) > 1 and len(term) < 20:  # Reasonable length
                cleaned_terms.append(term)

        return cleaned_terms

    def _is_term_consistent(self, usage: Dict[str, int]) -> bool:
        """Check if a term is used consistently"""
        # Count sections where term appears
        sections_used = sum(1 for count in usage.values() if count > 0)

        # Term should appear in multiple sections for consistency
        return sections_used >= 2

    def _get_consistency_issue(self, usage: Dict[str, int]) -> str:
        """Get description of consistency issue"""
        sections = [section for section, count in usage.items() if count > 0]
        missing_sections = [section for section, count in usage.items() if count == 0]

        if len(sections) == 1:
            return f"Term only appears in {sections[0]} section"
        elif len(missing_sections) > 2:
            return f"Term missing from {', '.join(missing_sections)} sections"
        else:
            return "Term usage inconsistent"

    def health_check(self) -> bool:
        """Health check for the checker"""
        return True