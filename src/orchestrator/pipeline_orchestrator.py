"""
Pipeline Orchestrator
Coordinates the patent processing pipeline with quality gates
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

from core.patent_document import PatentDocument
from checks.banned_words import BannedWordsChecker
from checks.background_leakage import BackgroundLeakageChecker
from checks.abstract_validation import AbstractValidationChecker
from checks.supportability import SupportabilityChecker
from checks.term_consistency import TermConsistencyChecker
from checks.ktf_completeness import KTFCompletenessChecker
from checks.claim_quality import ClaimQualityChecker

logger = logging.getLogger(__name__)

class ProcessingResult:
    """Result of patent processing"""
    def __init__(self):
        self.success: bool = False
        self.quality_score: float = 0.0
        self.check_results: Dict[str, Dict[str, Any]] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.processing_time: float = 0.0
        self.metadata: Dict[str, Any] = {}

class PipelineOrchestrator:
    """Orchestrates the patent processing pipeline with quality gates"""

    def __init__(self, enable_checks: bool = True):
        self.enable_checks = enable_checks
        self.checkers = {}

        if enable_checks:
            self._initialize_checkers()

    def _initialize_checkers(self):
        """Initialize all quality checkers"""
        self.checkers = {
            'ktf_completeness': KTFCompletenessChecker(),
            'supportability': SupportabilityChecker(),
            'term_consistency': TermConsistencyChecker(),
            'banned_words': BannedWordsChecker(),
            'abstract_validation': AbstractValidationChecker(),
            'background_leakage': BackgroundLeakageChecker(),
            'claim_quality': ClaimQualityChecker(),
        }

    def process_patent(self, patent_doc: PatentDocument,
                           enable_checks: bool = True) -> ProcessingResult:
        """Process patent through the complete pipeline"""
        start_time = datetime.now()
        result = ProcessingResult()

        try:
            logger.info(f"Starting patent processing for: {patent_doc.metadata.title}")

            # Step 1: Basic validation
            if not self._validate_input(patent_doc, result):
                return result

            # KPI metrics (persisted into result.metadata)
            result.metadata = result.metadata or {}
            result.metadata["kpis"] = self._compute_kpis(patent_doc, {})

            # Step 2: Run quality checks if enabled
            if enable_checks and self.enable_checks:
                check_results = self._run_quality_checks(patent_doc)
                result.check_results = check_results

                # Calculate overall quality score
                result.quality_score = self._calculate_quality_score(check_results)

                # Refresh KPIs with check-derived signals (e.g. term_consistency_score)
                result.metadata["kpis"] = self._compute_kpis(patent_doc, check_results)

                # Check if patent passes minimum quality threshold
                if not self._passes_quality_threshold(check_results):
                    result.success = False
                    result.errors.append("Patent failed quality checks")
                    return result

            # Step 3: Generate final documents
            self._finalize_documents(patent_doc, result)

            # Step 4: Post-processing
            self._post_process(patent_doc, result)

            result.success = True
            result.processing_time = (datetime.now() - start_time).total_seconds()

            logger.info(f"Patent processing completed successfully. Quality score: {result.quality_score:.2f}")

        except Exception as e:
            logger.error(f"Patent processing failed: {str(e)}")
            result.success = False
            result.errors.append(f"Processing error: {str(e)}")
            result.processing_time = (datetime.now() - start_time).total_seconds()

        return result

    def check_only(self, patent_doc: PatentDocument) -> ProcessingResult:
        """
        Re-run quality checks only (no regeneration / no finalization formatting).
        Soft-fail: always returns a result object.
        """
        start_time = datetime.now()
        result = ProcessingResult()
        result.metadata = result.metadata or {}

        try:
            if not self._validate_input(patent_doc, result):
                result.success = False
                result.processing_time = (datetime.now() - start_time).total_seconds()
                # still compute KPIs best-effort
                result.metadata["kpis"] = self._compute_kpis(patent_doc, {})
                return result

            check_results = self._run_quality_checks(patent_doc)
            result.check_results = check_results
            result.quality_score = self._calculate_quality_score(check_results)
            result.metadata["kpis"] = self._compute_kpis(patent_doc, check_results)

            # success reflects threshold but never blocks output
            result.success = self._passes_quality_threshold(check_results)
            result.processing_time = (datetime.now() - start_time).total_seconds()
            return result

        except Exception as e:
            result.success = False
            result.errors.append(f"Check-only error: {str(e)}")
            result.processing_time = (datetime.now() - start_time).total_seconds()
            result.metadata["kpis"] = self._compute_kpis(patent_doc, {})
            return result

    def _compute_kpis(self, patent_doc: PatentDocument, check_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        claims_list = patent_doc.get_all_claims() if hasattr(patent_doc, "get_all_claims") else []
        claims_count = len(claims_list)

        independent_claims_count = 0
        if getattr(patent_doc, "claims", None) and getattr(patent_doc.claims, "independent_claims", None):
            independent_claims_count = len(patent_doc.claims.independent_claims)

        avg_claim_length = 0.0
        if claims_count > 0:
            avg_claim_length = sum(len(c) for c in claims_list) / claims_count

        term_consistency_score = 0.0
        try:
            term_consistency_score = float(
                (check_results.get("term_consistency") or {}).get("score", 0.0) or 0.0
            )
        except Exception:
            term_consistency_score = 0.0

        # Quality-oriented KPIs from claim_quality checker if available
        cq_details = ((check_results.get("claim_quality") or {}).get("details") or {}) if check_results else {}
        cq_summary = (cq_details.get("summary") or {}) if isinstance(cq_details, dict) else {}

        dependent_claims_count = 0
        if getattr(patent_doc, "claims", None) and getattr(patent_doc.claims, "dependent_claims", None):
            dependent_claims_count = len(patent_doc.claims.dependent_claims or [])

        independent_claim_feature_count = 0
        total_feature_refs = 0
        unsupported_feature_refs = 0
        redundant_dependent_claims_count = 0
        try:
            independent_claim_feature_count = int(cq_summary.get("independent_feature_count", 0) or 0)
            total_feature_refs = int(cq_summary.get("total_feature_refs", 0) or 0)
            unsupported_feature_refs = int(cq_summary.get("unsupported_feature_refs", 0) or 0)
            redundant_dependent_claims_count = int(cq_summary.get("redundant_dependent_claims_count", 0) or 0)
        except Exception:
            pass

        avg_features_per_claim = 0.0
        if claims_count > 0:
            avg_features_per_claim = float(total_feature_refs) / float(claims_count)

        unsupported_feature_ratio = 0.0
        if total_feature_refs > 0:
            unsupported_feature_ratio = float(unsupported_feature_refs) / float(total_feature_refs)

        redundant_claim_ratio = 0.0
        if dependent_claims_count > 0:
            redundant_claim_ratio = float(redundant_dependent_claims_count) / float(dependent_claims_count)

        return {
            "claims_count": claims_count,
            "independent_claims_count": independent_claims_count,
            "avg_claim_length": avg_claim_length,
            "term_consistency_score": term_consistency_score,
            "independent_claim_feature_count": independent_claim_feature_count,
            "avg_features_per_claim": avg_features_per_claim,
            "unsupported_feature_ratio": unsupported_feature_ratio,
            "redundant_claim_ratio": redundant_claim_ratio,
        }

    def _validate_input(self, patent_doc: PatentDocument, result: ProcessingResult) -> bool:
        """Validate input patent document"""
        try:
            # Check required fields
            if not patent_doc.metadata.title:
                result.errors.append("Patent title is required")
                return False

            if not patent_doc.metadata.technical_field:
                result.errors.append("Technical field is required")
                return False

            # Check document completeness
            if not patent_doc.specification:
                result.warnings.append("Specification is missing")

            if not patent_doc.claims:
                result.warnings.append("Claims are missing")

            if not patent_doc.abstract:
                result.warnings.append("Abstract is missing")

            if not patent_doc.disclosure:
                result.warnings.append("Disclosure is missing")

            return len(result.errors) == 0

        except Exception as e:
            result.errors.append(f"Input validation error: {str(e)}")
            return False

    def _run_quality_checks(self, patent_doc: PatentDocument) -> Dict[str, Dict[str, Any]]:
        """Run all quality checks"""
        check_results = {}

        for check_name, checker in self.checkers.items():
            try:
                logger.info(f"Running {check_name} check...")

                # Run the check
                result = self._run_single_check(checker, patent_doc)
                check_results[check_name] = result

                logger.info(f"{check_name} check completed. Score: {result.get('score', 0):.2f}")

            except Exception as e:
                logger.error(f"Error in {check_name} check: {str(e)}")
                check_results[check_name] = {
                    'passed': False,
                    'score': 0.0,
                    'errors': [f"Check failed: {str(e)}"],
                    'details': {}
                }

        return check_results

    def _run_single_check(self, checker, patent_doc: PatentDocument) -> Dict[str, Any]:
        """Run a single quality check"""
        # Run check based on checker type
        if hasattr(checker, 'check'):
            result = checker.check(patent_doc)
        else:
            # For checkers that might not be async
            result = checker.check(patent_doc)

        # Ensure result has required structure
        if isinstance(result, tuple):
            passed, score, details = result
            return {
                'passed': passed,
                'score': score,
                'details': details,
                'errors': details.get('errors', []),
                'warnings': details.get('warnings', [])
            }
        elif isinstance(result, dict):
            return result
        else:
            return {
                'passed': bool(result),
                'score': 1.0 if result else 0.0,
                'details': {},
                'errors': [],
                'warnings': []
            }

    def _calculate_quality_score(self, check_results: Dict[str, Dict[str, Any]]) -> float:
        """Calculate overall quality score from check results"""
        if not check_results:
            return 0.0

        total_score = 0.0
        total_weight = 0.0

        # Define weights for each check
        weights = {
            'ktf_completeness': 0.25,
            'supportability': 0.20,
            'term_consistency': 0.15,
            'banned_words': 0.15,
            'abstract_validation': 0.15,
            'background_leakage': 0.05,
            'claim_quality': 0.05,
        }

        for check_name, result in check_results.items():
            weight = weights.get(check_name, 0.1)
            score = result.get('score', 0.0)

            total_score += score * weight
            total_weight += weight

        if total_weight > 0:
            return total_score / total_weight
        else:
            return 0.0

    def _passes_quality_threshold(self, check_results: Dict[str, Dict[str, Any]],
                                  min_score: float = 0.7) -> bool:
        """Check if patent passes minimum quality threshold"""
        if not check_results:
            return False

        # Check individual critical checks
        critical_checks = ['ktf_completeness', 'supportability', 'banned_words']

        for check_name in critical_checks:
            if check_name in check_results:
                result = check_results[check_name]
                if not result.get('passed', False) or result.get('score', 0) < min_score:
                    return False

        # Check overall score
        overall_score = self._calculate_quality_score(check_results)
        return overall_score >= min_score

    def _finalize_documents(self, patent_doc: PatentDocument, result: ProcessingResult):
        """Finalize patent documents"""
        try:
            # Ensure all documents have proper formatting
            if patent_doc.specification:
                patent_doc.specification.content = self._format_specification(patent_doc.specification)

            if patent_doc.claims:
                patent_doc.claims.content = self._format_claims(patent_doc.claims)

            if patent_doc.abstract:
                patent_doc.abstract.content = self._format_abstract(patent_doc.abstract)

            if patent_doc.disclosure:
                patent_doc.disclosure.content = self._format_disclosure(patent_doc.disclosure)

            # Update quality report
            if result.check_results:
                patent_doc.quality_report = result.check_results
                patent_doc.quality_score = result.quality_score

        except Exception as e:
            logger.error(f"Error finalizing documents: {str(e)}")
            result.warnings.append(f"Document finalization warning: {str(e)}")

    def _post_process(self, patent_doc: PatentDocument, result: ProcessingResult):
        """Post-processing steps"""
        try:
            # Add metadata
            result.metadata = {
                'title': patent_doc.metadata.title,
                'technical_field': patent_doc.metadata.technical_field,
                'document_type': patent_doc.metadata.document_type,
                'processing_timestamp': datetime.now().isoformat(),
                'quality_score': result.quality_score
            }

            # Generate summary statistics
            if result.check_results:
                result.metadata['check_statistics'] = self._generate_check_statistics(result.check_results)

        except Exception as e:
            logger.error(f"Error in post-processing: {str(e)}")
            result.warnings.append(f"Post-processing warning: {str(e)}")

    def _format_specification(self, specification) -> str:
        """Format specification content"""
        # Add standard formatting
        formatted = specification.content

        # Ensure proper section headers
        if "技术领域" not in formatted:
            formatted = f"技术领域\n{specification.technical_field}\n\n" + formatted

        if "背景技术" not in formatted:
            formatted = f"背景技术\n{specification.background_art}\n\n" + formatted

        if "发明内容" not in formatted:
            formatted = f"发明内容\n{specification.invention_content}\n\n" + formatted

        return formatted

    def _format_claims(self, claims) -> str:
        """Format claims content"""
        formatted = claims.content

        # Ensure proper claim numbering and formatting
        if "权利要求" not in formatted:
            formatted = "权利要求书\n\n" + formatted

        return formatted

    def _format_abstract(self, abstract) -> str:
        """Format abstract content"""
        formatted = abstract.content

        # Ensure proper length (CNIPA limit is 300 words)
        if len(abstract.summary) > 300:
            # Truncate and add ellipsis
            abstract.summary = abstract.summary[:297] + "..."
            formatted = formatted.replace(abstract.content.split('\n\n')[-1], abstract.summary)

        return formatted

    def _format_disclosure(self, disclosure) -> str:
        """Format disclosure content"""
        formatted = disclosure.content

        # Ensure proper section headers
        if "具体实施方式" not in formatted:
            formatted = f"具体实施方式\n\n{formatted}"

        return formatted

    def _generate_check_statistics(self, check_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Generate statistics from check results"""
        statistics = {
            'total_checks': len(check_results),
            'passed_checks': 0,
            'failed_checks': 0,
            'average_score': 0.0,
            'score_distribution': {}
        }

        total_score = 0.0

        for check_name, result in check_results.items():
            if result.get('passed', False):
                statistics['passed_checks'] += 1
            else:
                statistics['failed_checks'] += 1

            score = result.get('score', 0.0)
            total_score += score

            # Score distribution
            score_range = f"{int(score * 10) * 10}-{(int(score * 10) + 1) * 10}"
            if score_range not in statistics['score_distribution']:
                statistics['score_distribution'][score_range] = 0
            statistics['score_distribution'][score_range] += 1

        if check_results:
            statistics['average_score'] = total_score / len(check_results)

        return statistics

    def get_checker_status(self) -> Dict[str, bool]:
        """Get status of all checkers"""
        status = {}
        for name, checker in self.checkers.items():
            try:
                # Simple health check
                if hasattr(checker, 'health_check'):
                    status[name] = checker.health_check()
                else:
                    status[name] = True  # Assume healthy if no health_check method
            except Exception:
                status[name] = False
        return status

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the orchestrator"""
        checker_status = self.get_checker_status()

        return {
            'status': 'healthy' if all(checker_status.values()) else 'degraded',
            'checkers': checker_status,
            'total_checkers': len(checker_status),
            'healthy_checkers': sum(checker_status.values())
        }
