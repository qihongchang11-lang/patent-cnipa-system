"""
Claim Quality Checker (Phase 1.2)

Diagnostic-only (soft fail): never blocks generation.
Adds structured issues and recommendations for:
- claim structure/dependency validity
- feature coverage / unsupported / redundancy
- CNIPA-oriented language risks
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

from core.patent_document import PatentDocument


class ClaimQualityChecker:
    name = "claim_quality"

    ABSOLUTE_TERMS = [
        "绝对",
        "完全",
        "彻底",
        "始终",
        "永远",
        "必然",
        "必定",
        "一定",
        "肯定",
        "无疑",
        "最优",
        "最好",
        "最先进",
        "唯一",
        "100%",
        "hundred percent",
        "always",
        "forever",
        "undoubtedly",
    ]

    RESULT_ONLY_PATTERNS = [
        r"用于(?:提高|降低|改善|实现|达到).{0,20}(?:效果|目的|性能|效率)",
        r"从而(?:提高|降低|改善|实现|达到).{0,20}(?:效果|目的|性能|效率)",
        r"以便(?:提高|降低|改善|实现|达到).{0,20}(?:效果|目的|性能|效率)",
    ]

    VAGUE_FUNCTIONAL_PATTERNS = [
        r"用于.{0,15}处理",
        r"用于.{0,15}分析",
        r"用于.{0,15}识别",
        r"用于.{0,15}生成",
        r"用于.{0,15}优化",
    ]

    def check(self, patent_doc: PatentDocument) -> Tuple[bool, float, Dict[str, Any]]:
        details: Dict[str, Any] = {
            "issues": [],
            "recommendations": [],
            "summary": {},
            "errors": [],
            "warnings": [],
        }

        if not getattr(patent_doc, "claims", None):
            details["warnings"].append("Claims missing; claim quality checks skipped")
            details["summary"] = self._empty_summary()
            return True, 1.0, details

        indep = getattr(patent_doc.claims, "independent_claims", []) or []
        deps = getattr(patent_doc.claims, "dependent_claims", []) or []

        claim_texts: Dict[int, str] = {}
        for c in indep:
            claim_texts[int(c.claim_number)] = self._normalize_claim_text(self._claim_text_from_model(c))
        for c in deps:
            claim_texts[int(c.claim_number)] = self._normalize_claim_text(self._claim_text_from_model(c))

        issues: List[Dict[str, Any]] = []

        # --- Task 1: Structure & dependency validation ---
        if len(indep) != 1:
            issues.append(
                self._issue(
                    issue_type="structure.independent_claim_count",
                    claim_number=None,
                    snippet="",
                    risk="high",
                    message=f"Expected exactly 1 independent claim, got {len(indep)}",
                )
            )

        claim_numbers = sorted(claim_texts.keys())
        claim_set = set(claim_numbers)
        dep_edges: Dict[int, int] = {}
        for d in deps:
            child = int(d.claim_number)
            parent = int(d.parent_claim)
            dep_edges[child] = parent
            if parent not in claim_set:
                issues.append(
                    self._issue(
                        issue_type="structure.missing_parent",
                        claim_number=child,
                        snippet=self._snippet(claim_texts.get(child, "")),
                        risk="high",
                        message=f"Dependent claim references non-existent parent claim {parent}",
                    )
                )
            if parent >= child:
                issues.append(
                    self._issue(
                        issue_type="structure.invalid_dependency_order",
                        claim_number=child,
                        snippet=self._snippet(claim_texts.get(child, "")),
                        risk="high",
                        message=f"Dependent claim must depend on a lower-numbered claim (parent={parent}, child={child})",
                    )
                )

        # cycle detection (simple since parent is single int per dependent)
        for child in dep_edges:
            seen = set()
            cur = child
            while cur in dep_edges:
                if cur in seen:
                    issues.append(
                        self._issue(
                            issue_type="structure.dependency_cycle",
                            claim_number=child,
                            snippet=self._snippet(claim_texts.get(child, "")),
                            risk="high",
                            message="Dependency cycle detected in dependent claims",
                        )
                    )
                    break
                seen.add(cur)
                cur = dep_edges[cur]

        # --- Task 2: Feature coverage & over-restriction ---
        ktf_index = self._get_ktf_index(patent_doc)
        core_ktf_refs = list(ktf_index.keys())[:3]

        feature_refs_by_claim = self._get_feature_refs_by_claim(patent_doc)
        indep_num = int(indep[0].claim_number) if indep else 1
        indep_text = claim_texts.get(indep_num, "")

        indep_refs = feature_refs_by_claim.get(str(indep_num), [])
        unsupported_refs = [r for r in indep_refs if r not in ktf_index]

        if core_ktf_refs and indep_refs and not any(r in indep_refs for r in core_ktf_refs):
            issues.append(
                self._issue(
                    issue_type="missing_core_features",
                    claim_number=indep_num,
                    snippet=self._snippet(indep_text),
                    risk="medium",
                    message=f"Independent claim does not reference core KTF features: expected one of {core_ktf_refs}",
                )
            )

        # text-based coverage heuristic (works for rules mode where feature_refs are empty)
        if ktf_index and self._match_ktf_names_in_text(indep_text, list(ktf_index.values())) < 1:
            issues.append(
                self._issue(
                    issue_type="missing_core_features",
                    claim_number=indep_num,
                    snippet=self._snippet(indep_text),
                    risk="medium",
                    message="Independent claim text appears to miss core KTF feature names; consider adding key structures/modules",
                )
            )

        if unsupported_refs:
            issues.append(
                self._issue(
                    issue_type="unsupported_features",
                    claim_number=indep_num,
                    snippet=self._snippet(indep_text),
                    risk="medium",
                    message=f"Independent claim references unknown features not grounded in KTF: {unsupported_refs}",
                )
            )

        # over-restriction: hard-coded constants in independent claim
        if self._has_hard_constants(indep_text):
            issues.append(
                self._issue(
                    issue_type="over_specific_constants",
                    claim_number=indep_num,
                    snippet=self._snippet(indep_text),
                    risk="medium",
                    message="Independent claim contains hard-coded numeric constants; consider moving specifics to dependent claims",
                )
            )

        # redundant dependent claims
        dep_numbers = sorted([int(d.claim_number) for d in deps])
        redundant_deps: List[int] = []
        redundant_pairs: List[Dict[str, Any]] = []
        dep_text_list = [(n, claim_texts.get(n, "")) for n in dep_numbers]
        for i in range(len(dep_text_list)):
            for j in range(i + 1, len(dep_text_list)):
                a_n, a_t = dep_text_list[i]
                b_n, b_t = dep_text_list[j]
                if not a_t or not b_t:
                    continue
                sim = SequenceMatcher(None, a_t, b_t).ratio()
                if sim >= 0.92:
                    redundant_deps.extend([a_n, b_n])
                    redundant_pairs.append({"a": a_n, "b": b_n, "similarity": sim})

        redundant_deps = sorted(set(redundant_deps))
        if redundant_deps:
            issues.append(
                self._issue(
                    issue_type="redundant_dependent_claims",
                    claim_number=None,
                    snippet="",
                    risk="low",
                    message=f"Near-duplicate dependent claims detected: {redundant_deps}",
                )
            )
            details["recommendations"].append("Merge or differentiate redundant dependent claims to improve layering and patentability")

        # unsupported feature refs in dependent claims
        unsupported_feature_refs_total = 0
        total_feature_refs = 0
        for n in dep_numbers:
            refs = feature_refs_by_claim.get(str(n), [])
            total_feature_refs += len(refs)
            bad = [r for r in refs if r not in ktf_index]
            unsupported_feature_refs_total += len(bad)
            if bad:
                issues.append(
                    self._issue(
                        issue_type="unsupported_features",
                        claim_number=n,
                        snippet=self._snippet(claim_texts.get(n, "")),
                        risk="low",
                        message=f"Dependent claim references unknown features not grounded in KTF: {bad}",
                    )
                )

        # --- Task 3: Language risk scan (claims-specific) ---
        for n in claim_numbers:
            t = claim_texts.get(n, "")
            for term in self.ABSOLUTE_TERMS:
                if term and term in t:
                    issues.append(
                        self._issue(
                            issue_type="language.absolute_term",
                            claim_number=n,
                            snippet=self._snippet(t, highlight=term),
                            risk="high",
                            message=f"Absolute term detected in claim: {term}",
                        )
                    )

            for pat in self.RESULT_ONLY_PATTERNS:
                if re.search(pat, t):
                    issues.append(
                        self._issue(
                            issue_type="language.result_only_limitation",
                            claim_number=n,
                            snippet=self._snippet(t),
                            risk="medium",
                            message="Result-only limitation pattern detected; add structural/technical features supporting the result",
                        )
                    )

            if not self._has_structural_markers(t):
                for pat in self.VAGUE_FUNCTIONAL_PATTERNS:
                    if re.search(pat, t):
                        issues.append(
                            self._issue(
                                issue_type="language.vague_functional",
                                claim_number=n,
                                snippet=self._snippet(t),
                                risk="medium",
                                message="Vague functional language detected without clear structure; consider adding concrete components/steps",
                            )
                        )
                        break

        details["issues"] = issues

        # score/pass (diagnostic)
        high = [i for i in issues if i.get("risk") == "high"]
        penalty = 0.0
        penalty += 0.2 * len(high)
        penalty += 0.05 * len([i for i in issues if i.get("risk") == "medium"])
        score = max(0.4, 1.0 - penalty)
        passed = len(high) == 0

        details["summary"] = {
            "claims_count": len(claim_numbers),
            "independent_claims_count": len(indep),
            "dependent_claims_count": len(deps),
            "independent_feature_count": len(indep_refs) if indep_refs else self._match_ktf_names_in_text(indep_text, list(ktf_index.values())),
            "total_feature_refs": (len(indep_refs) + total_feature_refs),
            "unsupported_feature_refs": (len(unsupported_refs) + unsupported_feature_refs_total),
            "redundant_dependent_claims_count": len(redundant_deps),
            "redundant_pairs": redundant_pairs,
        }

        # recommendations
        if any(i["type"].startswith("structure.") for i in issues):
            details["recommendations"].append("Fix claim numbering/dependency: ensure dependent claims reference existing lower-numbered claims without cycles")
        if any(i["type"] == "missing_core_features" for i in issues):
            details["recommendations"].append("Strengthen independent claim: include core technical features (modules/steps) grounded in the KTF list")
        if any(i["type"] == "unsupported_features" for i in issues):
            details["recommendations"].append("Align claim features with KTF: map feature references to extracted key technical features or update PSE/KTF extraction")

        return passed, score, details

    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "claims_count": 0,
            "independent_claims_count": 0,
            "dependent_claims_count": 0,
            "independent_feature_count": 0,
            "total_feature_refs": 0,
            "unsupported_feature_refs": 0,
            "redundant_dependent_claims_count": 0,
            "redundant_pairs": [],
        }

    def _get_ktf_index(self, patent_doc: PatentDocument) -> Dict[str, str]:
        pse = getattr(patent_doc, "pse_matrix", None)
        if pse and getattr(pse, "audit", None):
            idx = (pse.audit or {}).get("ktf_index") or {}
            if isinstance(idx, dict) and idx:
                return {str(k): str(v) for k, v in idx.items()}
        # fallback: build from kt_features list order
        out: Dict[str, str] = {}
        if pse and getattr(pse, "kt_features", None):
            for i, f in enumerate(pse.kt_features, 1):
                name = getattr(f, "name", "") or ""
                if name.strip():
                    out[f"F{i}"] = name.strip()
        return out

    def _get_feature_refs_by_claim(self, patent_doc: PatentDocument) -> Dict[str, List[str]]:
        audit = getattr(patent_doc, "audit", {}) or {}
        gen = (audit.get("generation") or {}) if isinstance(audit, dict) else {}
        claims_a = (gen.get("claims") or {}) if isinstance(gen, dict) else {}
        fr = claims_a.get("feature_refs_by_claim") or {}
        if isinstance(fr, dict):
            return {str(k): [str(x) for x in (v or [])] for k, v in fr.items() if isinstance(v, list)}
        return {}

    def _claim_text_from_model(self, claim_model) -> str:
        if hasattr(claim_model, "preamble") and hasattr(claim_model, "body"):
            pre = (getattr(claim_model, "preamble", "") or "").strip()
            trans = (getattr(claim_model, "transition", "") or "").strip()
            body = (getattr(claim_model, "body", "") or "").strip()
            return " ".join([p for p in [pre, trans, body] if p]).strip()
        if hasattr(claim_model, "additional_features"):
            return (getattr(claim_model, "additional_features", "") or "").strip()
        return str(claim_model)

    def _normalize_claim_text(self, text: str) -> str:
        t = (text or "").strip()
        t = re.sub(r"\s+", " ", t)
        return t

    def _snippet(self, text: str, highlight: str = "", max_len: int = 80) -> str:
        t = (text or "").strip()
        if not t:
            return ""
        if highlight and highlight in t:
            pos = t.find(highlight)
            start = max(0, pos - 20)
            end = min(len(t), pos + 20 + len(highlight))
            return t[start:end]
        return t[:max_len]

    def _issue(self, issue_type: str, claim_number: int | None, snippet: str, risk: str, message: str) -> Dict[str, Any]:
        return {
            "type": issue_type,
            "claim_number": claim_number,
            "snippet": snippet,
            "risk": risk,
            "message": message,
        }

    def _has_hard_constants(self, text: str) -> bool:
        if re.search(r"\b\d+(\.\d+)?\b", text):
            return True
        if re.search(r"(毫米|厘米|米|kg|g|ms|s|分钟|小时)", text):
            return True
        return False

    def _has_structural_markers(self, text: str) -> bool:
        markers = ["包括", "包含", "由", "连接", "设置", "用于", "步骤", "模块", "单元"]
        return any(m in (text or "") for m in markers)

    def _match_ktf_names_in_text(self, text: str, ktf_names: List[str]) -> int:
        t = text or ""
        count = 0
        for name in ktf_names[:10]:
            if name and name in t:
                count += 1
        return count

