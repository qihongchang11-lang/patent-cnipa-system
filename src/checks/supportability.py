"""
Supportability Checker (Gate B)
Checks if claims are properly supported by specification
"""

from typing import List, Dict, Any, Tuple
from core.patent_document import PatentDocument

class SupportabilityChecker:
    """Checks supportability between claims and specification"""

    def __init__(self):
        self.min_support_threshold = 0.6  # Minimum 60% support required

    def check(self, patent_doc: PatentDocument) -> Tuple[bool, float, Dict[str, Any]]:
        """Check if claims are supported by specification"""
        details = {
            'claims_count': 0,
            'supported_claims': 0,
            'unsupported_claims': [],
            'support_scores': {},
            'missing_elements': [],
            'recommendations': [],
            'errors': [],
            'warnings': []
        }

        try:
            if not patent_doc.claims or not patent_doc.specification:
                details['errors'].append("Claims or specification missing")
                return False, 0.0, details

            claims = patent_doc.claims
            specification = patent_doc.specification
            spec_text = specification.content.lower()

            # Check each claim
            total_claims = 0
            supported_claims = 0

            if claims.independent_claims:
                for claim in claims.independent_claims:
                    total_claims += 1
                    support_score = self._calculate_support_score(claim, spec_text)
                    details['support_scores'][f"claim_{claim.claim_number}"] = support_score

                    if support_score >= self.min_support_threshold:
                        supported_claims += 1
                    else:
                        details['unsupported_claims'].append(claim.claim_number)

            if claims.dependent_claims:
                for claim in claims.dependent_claims:
                    total_claims += 1
                    support_score = self._calculate_support_score(claim, spec_text)
                    details['support_scores'][f"claim_{claim.claim_number}"] = support_score

                    if support_score >= self.min_support_threshold:
                        supported_claims += 1
                    else:
                        details['unsupported_claims'].append(claim.claim_number)

            details['claims_count'] = total_claims
            details['supported_claims'] = supported_claims

            # Calculate overall score
            if total_claims > 0:
                overall_score = supported_claims / total_claims
            else:
                overall_score = 0.0

            # Determine pass/fail
            passed = overall_score >= self.min_support_threshold

            if not passed:
                details['recommendations'].append("Ensure all claims are adequately supported by specification")
                details['recommendations'].append("Add missing technical details to specification")

            return passed, overall_score, details

        except Exception as e:
            details['errors'].append(f"Supportability check failed: {str(e)}")
            return False, 0.0, details

    def _calculate_support_score(self, claim, spec_text: str) -> float:
        """Calculate support score for a claim"""
        claim_text = self._get_claim_text(claim).lower()
        claim_words = set(claim_text.split())
        spec_words = set(spec_text.split())

        if not claim_words:
            return 0.0

        # Calculate word overlap
        supported_words = claim_words.intersection(spec_words)
        support_ratio = len(supported_words) / len(claim_words)

        return support_ratio

    def _get_claim_text(self, claim) -> str:
        """Get text representation of a claim"""
        if hasattr(claim, 'preamble') and hasattr(claim, 'body'):
            return f"{claim.preamble} {claim.body}"
        elif hasattr(claim, 'additional_features'):
            return claim.additional_features
        else:
            return str(claim)

    def health_check(self) -> bool:
        """Health check for the checker"""
        return True