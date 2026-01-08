"""
KTF Completeness Checker (Gate A)
Verifies that Key Technical Features are completely extracted and documented
"""

import re
from typing import List, Dict, Any, Tuple
from core.patent_document import PatentDocument, TechnicalFeature

class KTFCompletenessChecker:
    """Checks completeness of Key Technical Features extraction"""

    def __init__(self):
        # Minimum requirements for KTF completeness
        self.min_ktf_features = 3
        self.min_problems = 1
        self.min_solutions = 1
        self.min_effects = 1

        # Patterns to identify different types of technical content
        self.problem_patterns = [
            r'问题[是：]\s*(.+?)(?=[，。；])',
            r'缺点[是：]\s*(.+?)(?=[，。；])',
            r'不足[是：]\s*(.+?)(?=[，。；])',
            r'存在(.+?)(?=[，。；])'
        ]

        self.solution_patterns = [
            r'解决[了：]\s*(.+?)(?=[，。；])',
            r'采用(.+?)(?=[，。；])',
            r'通过(.+?)(?=[，。；])',
            r'技术方案[是：]\s*(.+?)(?=[，。；])'
        ]

        self.effect_patterns = [
            r'效果[是：]\s*(.+?)(?=[，。；])',
            r'优点[是：]\s*(.+?)(?=[，。；])',
            r'能够(.+?)(?=[，。；])',
            r'实现(.+?)(?=[，。；])'
        ]

    def check(self, patent_doc: PatentDocument) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Check KTF completeness
        Returns: (passed, score, details)
        """
        details = {
            'ktf_features_count': 0,
            'problems_count': 0,
            'solutions_count': 0,
            'effects_count': 0,
            'missing_elements': [],
            'recommendations': [],
            'errors': [],
            'warnings': []
        }

        try:
            # Check PSE matrix existence
            if not patent_doc.pse_matrix:
                details['errors'].append("PSE matrix is missing")
                details['missing_elements'].append('pse_matrix')
                return False, 0.0, details

            pse_matrix = patent_doc.pse_matrix

            # Count KTF features
            ktf_features = pse_matrix.kt_features if pse_matrix.kt_features else []
            details['ktf_features_count'] = len(ktf_features)

            # Count problems, solutions, effects
            problems = pse_matrix.problems if pse_matrix.problems else []
            solutions = pse_matrix.solutions if pse_matrix.solutions else []
            effects = pse_matrix.effects if pse_matrix.effects else []

            details['problems_count'] = len(problems)
            details['solutions_count'] = len(solutions)
            details['effects_count'] = len(effects)

            # Validate each KTF feature
            valid_features = 0
            for i, feature in enumerate(ktf_features):
                feature_validation = self._validate_ktf_feature(feature, i)
                if feature_validation['valid']:
                    valid_features += 1
                else:
                    details['warnings'].extend(feature_validation['issues'])

            # Check minimum requirements
            passed = True
            score_components = []

            if details['ktf_features_count'] < self.min_ktf_features:
                passed = False
                details['missing_elements'].append('ktf_features')
                details['recommendations'].append(f"Add at least {self.min_ktf_features - details['ktf_features_count']} more key technical features")
            else:
                score_components.append(0.25)

            if details['problems_count'] < self.min_problems:
                passed = False
                details['missing_elements'].append('problems')
                details['recommendations'].append("Document at least one technical problem")
            else:
                score_components.append(0.25)

            if details['solutions_count'] < self.min_solutions:
                passed = False
                details['missing_elements'].append('solutions')
                details['recommendations'].append("Document at least one technical solution")
            else:
                score_components.append(0.25)

            if details['effects_count'] < self.min_effects:
                passed = False
                details['missing_elements'].append('effects')
                details['recommendations'].append("Document at least one technical effect")
            else:
                score_components.append(0.25)

            # Calculate score
            score = sum(score_components) if score_components else 0.0

            # Bonus for exceeding minimums
            if details['ktf_features_count'] >= self.min_ktf_features * 2:
                score = min(1.0, score + 0.1)
                details['recommendations'].append("Good: Rich set of technical features documented")

            # Validate coherence between PSE elements
            coherence_score = self._check_pse_coherence(patent_doc)
            if coherence_score < 0.5:
                passed = False
                details['warnings'].append("Low coherence between problems, solutions, and effects")

            return passed, score, details

        except Exception as e:
            details['errors'].append(f"KTF completeness check failed: {str(e)}")
            return False, 0.0, details

    def _validate_ktf_feature(self, feature: TechnicalFeature, index: int) -> Dict[str, Any]:
        """Validate a single KTF feature"""
        validation = {
            'valid': True,
            'issues': []
        }

        # Check if feature has required fields
        if not feature.name or len(feature.name.strip()) < 2:
            validation['valid'] = False
            validation['issues'].append(f"KTF feature {index + 1}: Name is too short or missing")

        if not feature.description or len(feature.description.strip()) < 10:
            validation['valid'] = False
            validation['issues'].append(f"KTF feature {index + 1}: Description is too short")

        if not feature.category:
            validation['issues'].append(f"KTF feature {index + 1}: Category is not specified")

        return validation

    def _check_pse_coherence(self, patent_doc: PatentDocument) -> float:
        """Check coherence between problems, solutions, and effects"""
        if not patent_doc.pse_matrix:
            return 0.0

        pse = patent_doc.pse_matrix
        problems = pse.problems if pse.problems else []
        solutions = pse.solutions if pse.solutions else []
        effects = pse.effects if pse.effects else []

        if not problems or not solutions:
            return 0.0

        # Simple coherence check - look for overlapping keywords
        problem_text = ' '.join(problems).lower()
        solution_text = ' '.join(solutions).lower()
        effect_text = ' '.join(effects).lower() if effects else ''

        # Calculate problem-solution coherence
        problem_words = set(problem_text.split())
        solution_words = set(solution_text.split())

        if problem_words:
            solution_overlap = len(problem_words.intersection(solution_words)) / len(problem_words)
        else:
            solution_overlap = 0.0

        # Calculate solution-effect coherence
        if effects and solution_words:
            effect_words = set(effect_text.split())
            effect_overlap = len(solution_words.intersection(effect_words)) / len(solution_words)
        else:
            effect_overlap = 0.0

        # Average coherence
        coherence = (solution_overlap + effect_overlap) / 2

        return coherence

    def _extract_additional_problems(self, text: str) -> List[str]:
        """Extract problems from patent text using patterns"""
        problems = []
        for pattern in self.problem_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            problems.extend(matches)
        return problems

    def _extract_additional_solutions(self, text: str) -> List[str]:
        """Extract solutions from patent text using patterns"""
        solutions = []
        for pattern in self.solution_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            solutions.extend(matches)
        return solutions

    def _extract_additional_effects(self, text: str) -> List[str]:
        """Extract effects from patent text using patterns"""
        effects = []
        for pattern in self.effect_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            effects.extend(matches)
        return effects

    def _analyze_ktf_coverage(self, patent_doc: PatentDocument) -> Dict[str, Any]:
        """Analyze KTF coverage across different sections"""
        coverage = {
            'in_specification': 0,
            'in_claims': 0,
            'in_abstract': 0,
            'in_disclosure': 0,
            'total_coverage': 0.0
        }

        if not patent_doc.pse_matrix or not patent_doc.pse_matrix.kt_features:
            return coverage

        ktf_names = [f.name for f in patent_doc.pse_matrix.kt_features]

        # Check coverage in specification
        if patent_doc.specification:
            spec_text = patent_doc.specification.content
            coverage['in_specification'] = sum(1 for name in ktf_names if name in spec_text)

        # Check coverage in claims
        if patent_doc.claims:
            claims_text = patent_doc.claims.content
            coverage['in_claims'] = sum(1 for name in ktf_names if name in claims_text)

        # Check coverage in abstract
        if patent_doc.abstract:
            abstract_text = patent_doc.abstract.content
            coverage['in_abstract'] = sum(1 for name in ktf_names if name in abstract_text)

        # Check coverage in disclosure
        if patent_doc.disclosure:
            disclosure_text = patent_doc.disclosure.content
            coverage['in_disclosure'] = sum(1 for name in ktf_names if name in disclosure_text)

        # Calculate total coverage
        if ktf_names:
            total_mentions = (coverage['in_specification'] + coverage['in_claims'] +
                            coverage['in_abstract'] + coverage['in_disclosure'])
            coverage['total_coverage'] = total_mentions / (len(ktf_names) * 4)  # 4 sections

        return coverage

    def health_check(self) -> bool:
        """Health check for the checker"""
        try:
            # Test with a simple patent document
            test_doc = PatentDocument(
                metadata={'title': 'Test Patent', 'technical_field': 'Test Field'}
            )
            passed, score, details = self.check(test_doc)
            return True  # If we can run the check, it's healthy
        except Exception:
            return False