"""
Four-Piece Document Generator
Generates the four main patent documents: specification, claims, abstract, and disclosure
"""

from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

from core.patent_document import (
    PatentDocument, MetaData, Specification, Claims, Abstract, Disclosure,
    IndependentClaim, DependentClaim, TechnicalFeature, PSEMatrix, DocumentType
)
from utils.llm_client import LLMClient
from pydantic import BaseModel, Field


class _LLMIndependentClaimContract(BaseModel):
    number: str = Field(default="1")
    text: str = Field(..., min_length=10)
    feature_refs: List[str] = Field(default_factory=list)


class _LLMDependentClaimContract(BaseModel):
    number: str
    depends_on: str = Field(default="1")
    text: str = Field(..., min_length=10)
    feature_refs: List[str] = Field(default_factory=list)


class _LLMTermInfoContract(BaseModel):
    definition: str = Field(default="")
    occurrences: List[str] = Field(default_factory=list)


class _LLMClaimsContract(BaseModel):
    independent_claim: _LLMIndependentClaimContract
    dependent_claims: List[_LLMDependentClaimContract] = Field(default_factory=list)
    term_map: Dict[str, _LLMTermInfoContract] = Field(default_factory=dict)


class _LLMAbstractContract(BaseModel):
    summary: str = Field(..., min_length=30, max_length=500)
    main_figure_description: Optional[str] = None

class FourPieceGenerator:
    """Generates the four main patent documents"""

    def __init__(self, llm_client: Optional[LLMClient] = None, force_rules: bool = False):
        # Initialize with standard templates and formatting rules
        self.llm_client = llm_client or LLMClient()
        self.force_rules = force_rules
        self.templates = {
            'specification': self._get_specification_template(),
            'claims': self._get_claims_template(),
            'abstract': self._get_abstract_template(),
            'disclosure': self._get_disclosure_template()
        }

    def _get_specification_template(self):
        """Get specification template"""
        return """说明书

技术领域
{technical_field}

背景技术
{background}

发明内容
{invention_content}

具体实施方式
{embodiments}
"""

    def _get_claims_template(self):
        """Get claims template"""
        return """权利要求书

权利要求1：
{preamble} {transition} {body}
"""

    def _get_abstract_template(self):
        """Get abstract template"""
        return """摘要

发明名称：{title}
技术领域：{technical_field}

{summary}
"""

    def _get_disclosure_template(self):
        """Get disclosure template"""
        return """具体实施方式

{detailed_description}
"""

    def generate_all(
        self,
        title: str,
        technical_field: str,
        background: str,
        invention_content: str,
        embodiments: str,
        pse_matrix: Optional[PSEMatrix] = None,
        drawings_description: Optional[str] = None,
        llm_temperature: float = 0.2,
    ) -> PatentDocument:
        """Generate all four patent documents"""

        # Create metadata
        metadata = MetaData(
            title=title,
            technical_field=technical_field,
            document_type=DocumentType.INVENTION
        )

        # Generate specification
        specification = self.generate_specification(
            title=title,
            technical_field=technical_field,
            background=background,
            invention_content=invention_content,
            embodiments=embodiments,
            drawings_description=drawings_description
        )

        # Generate claims (Phase 1: LLM-first + fallback)
        claims, claims_audit = self._generate_claims_with_audit(
            title=title,
            technical_field=technical_field,
            invention_content=invention_content,
            pse_matrix=pse_matrix,
            llm_temperature=llm_temperature,
        )

        # Generate abstract (Phase 1: LLM-first + fallback)
        abstract, abstract_audit = self._generate_abstract_with_audit(
            title=title,
            technical_field=technical_field,
            invention_content=invention_content,
            pse_matrix=pse_matrix,
            llm_temperature=llm_temperature,
        )

        # Generate disclosure
        disclosure = self.generate_disclosure(
            embodiments=embodiments,
            pse_matrix=pse_matrix
        )

        # Create complete patent document
        patent_doc = PatentDocument(
            metadata=metadata,
            specification=specification,
            claims=claims,
            abstract=abstract,
            disclosure=disclosure,
            pse_matrix=pse_matrix
        )

        patent_doc.audit = {
            "generation": {
                "claims": claims_audit,
                "abstract": abstract_audit,
            }
        }

        return patent_doc

    def generate_specification(self, title: str, technical_field: str,
                             background: str, invention_content: str,
                             embodiments: str, drawings_description: Optional[str] = None) -> Specification:
        """Generate patent specification document"""

        # Format technical field section
        technical_field_section = self._format_technical_field(technical_field)

        # Format background section
        background_section = self._format_background(background)

        # Format invention content section
        invention_content_section = self._format_invention_content(invention_content)

        # Format drawings description
        drawings_section = self._format_drawings_description(drawings_description)

        # Format embodiments section
        embodiments_section = self._format_embodiments(embodiments)

        # Combine all sections
        full_specification = f"""说明书

技术领域
{technical_field_section}

背景技术
{background_section}

发明内容
{invention_content_section}
"""

        if drawings_section:
            full_specification += f"""
附图说明
{drawings_section}
"""

        full_specification += f"""
具体实施方式
{embodiments_section}
"""

        return Specification(
            technical_field=technical_field_section,
            background_art=background_section,
            invention_content=invention_content_section,
            description_of_drawings=drawings_section,
            embodiments=embodiments_section,
            content=full_specification
        )

    def generate_claims(
        self,
        title: str,
        technical_field: str,
        invention_content: str,
        pse_matrix: Optional[PSEMatrix] = None,
        llm_temperature: float = 0.2,
    ) -> Claims:
        """Generate patent claims"""
        claims, _audit = self._generate_claims_with_audit(
            title=title,
            technical_field=technical_field,
            invention_content=invention_content,
            pse_matrix=pse_matrix,
            llm_temperature=llm_temperature,
        )
        return claims

    def _generate_claims_with_audit(
        self,
        title: str,
        technical_field: str,
        invention_content: str,
        pse_matrix: Optional[PSEMatrix],
        llm_temperature: float = 0.2,
    ) -> Tuple[Claims, Dict]:
        # 1) Try LLM (structured JSON)
        if (not self.force_rules) and self.llm_client.is_configured():
            kt_names = []
            if pse_matrix and getattr(pse_matrix, "kt_features", None):
                kt_names = [f.name for f in pse_matrix.kt_features if getattr(f, "name", None)]
            system_prompt = (
                "You are a strict Patent Examiner. "
                "You verify that every claim is fully supported by the description. "
                "Do not introduce any technical term that is not present in the provided invention content."
            )
            prompt = (
                "任务：撰写中文权利要求书草稿（JSON），并进行一致性自检。\n\n"
                "强制顺序（在你内部完成，不要输出过程文本）：\n"
                "1) 提取你即将在权利要求中使用的所有技术术语/部件名称（包括缩写/模块名/关键特征）。\n"
                "2) 对每个术语进行校验：必须能在【发明内容】或【关键技术特征】中找到原词或等价表述；"
                "如果找不到，就不得引入该术语，必须改用已存在的表述。\n"
                "3) 通过校验后再生成权利要求，并完整填写 term_map："
                "每个术语必须有 definition，occurrences 至少包含 claim:1；如能对应到说明书内容，请尽量填写 spec:pN。\n\n"
                "输出要求：\n"
                "- 输出必须为 JSON，结构严格符合给定 JSON Schema（字段名不得变更）\n"
                "- 语言使用中文法言法语，避免绝对化/夸大/主观/商业用语\n"
                "- independent_claim.text / dependent_claims[].text 均为完整权利要求句子（不包含前置编号）\n"
                "- number/depends_on 均使用字符串（例如：\"1\"）\n"
                "- feature_refs 使用如 F1/F2 的引用（可为空），尽量只引用【关键技术特征】中的要点\n"
                "- 从属权利要求：0~8 项，均从属于权利要求1\n\n"
                f"发明名称：{title}\n"
                f"技术领域：{technical_field}\n"
                f"发明内容：{invention_content}\n"
                f"关键技术特征（可用）：{kt_names}\n"
            )

            contract = self.llm_client.generate_structured_data(
                prompt,
                _LLMClaimsContract,
                retries=2,
                system_prompt=system_prompt,
                temperature=float(llm_temperature),
            )
            if contract is not None:
                meta = self.llm_client.get_last_meta()
                indep_num = _safe_int(contract.independent_claim.number, default=1)
                indep_text = contract.independent_claim.text.strip()
                indep = IndependentClaim(
                    claim_number=indep_num,
                    preamble=indep_text,
                    transition="",
                    body="",
                    technical_features=[],
                )
                deps: List[DependentClaim] = []
                for d in contract.dependent_claims[:8]:
                    dep_num = _safe_int(d.number, default=(len(deps) + 2))
                    parent = _safe_int(d.depends_on, default=1)
                    dep_text = d.text.strip()
                    normalized = _strip_dep_prefix(dep_text, parent)
                    deps.append(
                        DependentClaim(
                            claim_number=dep_num,
                            parent_claim=parent,
                            additional_features=normalized,
                            technical_features=[],
                        )
                    )

                claims_text = render_claims_markdown(indep_text, contract.dependent_claims)
                feature_refs_by_claim = {
                    str(indep_num): [str(x) for x in (contract.independent_claim.feature_refs or [])],
                }
                for d in contract.dependent_claims[:8]:
                    feature_refs_by_claim[str(d.number).strip()] = [str(x) for x in (d.feature_refs or [])]

                return (
                    Claims(independent_claims=[indep], dependent_claims=deps, content=claims_text),
                    {
                        "source": "llm",
                        "trace_id": getattr(meta, "trace_id", None),
                        "llm": self.llm_client.get_config_meta(),
                        "term_map": _term_map_to_json(contract.term_map),
                        "feature_refs_by_claim": feature_refs_by_claim,
                        "fallback_reason": None,
                    },
                )

        # 2) Fallback to existing rules/template logic
        technical_features = self._extract_technical_features(invention_content, pse_matrix)
        independent_claim = self._generate_independent_claim(
            title=title,
            technical_field=technical_field,
            technical_features=technical_features
        )
        dependent_claims = self._generate_dependent_claims(
            independent_claim=1,
            technical_features=technical_features
        )
        claims_text = self._format_claims_text([independent_claim], dependent_claims)
        last = self.llm_client.get_last_meta()
        return (
            Claims(
                independent_claims=[independent_claim],
                dependent_claims=dependent_claims,
                content=claims_text
            ),
            {
                "source": "rules",
                "trace_id": getattr(last, "trace_id", None) or _new_trace_id(),
                "llm": self.llm_client.get_config_meta(),
                "fallback_reason": "forced_rules" if self.force_rules else "llm_unavailable_or_invalid",
            },
        )

        # Extract technical features from invention content and PSE matrix
        technical_features = self._extract_technical_features(invention_content, pse_matrix)

        # Generate independent claim
        independent_claim = self._generate_independent_claim(
            title=title,
            technical_field=technical_field,
            technical_features=technical_features
        )

        # Generate dependent claims
        dependent_claims = self._generate_dependent_claims(
            independent_claim=1,
            technical_features=technical_features
        )

        # Format complete claims text
        claims_text = self._format_claims_text([independent_claim], dependent_claims)

        return Claims(
            independent_claims=[independent_claim],
            dependent_claims=dependent_claims,
            content=claims_text
        )

    def generate_abstract(
        self,
        title: str,
        technical_field: str,
        invention_content: str,
        llm_temperature: float = 0.2,
    ) -> Abstract:
        """Generate patent abstract"""
        abstract, _audit = self._generate_abstract_with_audit(
            title=title,
            technical_field=technical_field,
            invention_content=invention_content,
            pse_matrix=None,
            llm_temperature=llm_temperature,
        )
        return abstract

    def _generate_abstract_with_audit(
        self,
        title: str,
        technical_field: str,
        invention_content: str,
        pse_matrix: Optional[PSEMatrix],
        llm_temperature: float = 0.2,
    ) -> Tuple[Abstract, Dict]:
        if (not self.force_rules) and self.llm_client.is_configured():
            system_prompt = (
                "You are a strict Patent Examiner. "
                "You verify that every technical term in the abstract is supported by the description."
            )
            prompt = (
                "任务：撰写中文专利摘要（JSON），并进行一致性自检。\n\n"
                "强制顺序（在你内部完成，不要输出过程文本）：\n"
                "1) 列出你将用于摘要的全部技术术语。\n"
                "2) 校验每个术语：必须能在【发明内容】中找到原词或等价表述；否则不得引入。\n"
                "3) 通过校验后再生成 summary。\n\n"
                "要求：\n"
                "- 输出必须为 JSON，结构严格符合给定 JSON Schema（字段名不得变更）\n"
                "- summary 为中文摘要正文，<= 500 字，客观表述，不含绝对化/夸大/主观用语\n"
                "- 内容应包含：技术领域、要解决的技术问题、技术方案要点、技术效果（客观）\n\n"
                f"发明名称：{title}\n"
                f"技术领域：{technical_field}\n"
                f"发明内容：{invention_content}\n"
            )
            contract = self.llm_client.generate_structured_data(
                prompt,
                _LLMAbstractContract,
                retries=1,
                system_prompt=system_prompt,
                temperature=float(llm_temperature),
            )
            if contract is not None:
                meta = self.llm_client.get_last_meta()
                abstract_content = f"""摘要

发明名称：{title}
技术领域：{technical_field}

{contract.summary.strip()}
"""
                return (
                    Abstract(
                        title=title,
                        technical_field=technical_field,
                        summary=contract.summary.strip(),
                        main_figure_description=(contract.main_figure_description.strip() if contract.main_figure_description else None),
                        content=abstract_content,
                    ),
                    {
                        "source": "llm",
                        "trace_id": getattr(meta, "trace_id", None),
                        "llm": self.llm_client.get_config_meta(),
                        "fallback_reason": None,
                    },
                )

        # Generate summary from invention content
        summary = self._generate_summary(invention_content)

        # Create abstract content
        abstract_content = f"""摘要

发明名称：{title}
技术领域：{technical_field}

{summary}
"""

        return Abstract(
            title=title,
            technical_field=technical_field,
            summary=summary,
            content=abstract_content
        ), {
            "source": "rules",
            "trace_id": getattr(self.llm_client.get_last_meta(), "trace_id", None) or _new_trace_id(),
            "llm": self.llm_client.get_config_meta(),
            "fallback_reason": "forced_rules" if self.force_rules else "llm_unavailable_or_invalid",
        }

    def generate_disclosure(self, embodiments: str, pse_matrix: Optional[PSEMatrix] = None) -> Disclosure:
        """Generate patent disclosure (detailed implementation)"""

        # Extract examples from embodiments
        examples = self._extract_examples(embodiments)

        # Generate detailed description
        detailed_description = self._generate_detailed_description(embodiments, pse_matrix)

        # Extract drawing descriptions
        drawings = self._extract_drawings(embodiments)

        # Create disclosure content
        disclosure_content = f"""具体实施方式

{detailed_description}
"""

        if examples:
            disclosure_content += "\n实施例\n"
            for i, example in enumerate(examples, 1):
                disclosure_content += f"\n实施例 {i}：\n{example}\n"

        if drawings:
            disclosure_content += "\n附图说明\n"
            for drawing in drawings:
                disclosure_content += f"\n- {drawing}"

        return Disclosure(
            detailed_description=detailed_description,
            examples=examples,
            drawings=drawings,
            content=disclosure_content
        )

    def _format_technical_field(self, technical_field: str) -> str:
        """Format technical field section"""
        return f"本发明涉及{technical_field}，特别是关于{technical_field}中的改进技术。"

    def _format_background(self, background: str) -> str:
        """Format background section"""
        # Add standard background structure
        formatted = f"在{background}领域中，现有技术存在以下问题：\n\n"

        # Add the provided background content
        formatted += background

        formatted += "\n\n因此，需要一种新的技术方案来解决上述问题。"

        return formatted

    def _format_invention_content(self, invention_content: str) -> str:
        """Format invention content section"""
        # Add standard invention content structure
        formatted = "本发明的目的在于提供一种技术方案，能够解决现有技术中的问题。\n\n"

        formatted += "本发明的技术方案如下：\n\n"
        formatted += invention_content

        formatted += "\n\n本发明的有益效果包括："
        formatted += "\n1. 提高了技术性能"
        formatted += "\n2. 降低了成本"
        formatted += "\n3. 简化了操作流程"

        return formatted

    def _format_drawings_description(self, drawings_description: Optional[str]) -> Optional[str]:
        """Format drawings description section"""
        if not drawings_description:
            return None

        return f"图1是{drawings_description}的结构示意图。\n图2是图1的局部放大图。"

    def _format_embodiments(self, embodiments: str) -> str:
        """Format embodiments section"""
        # Add standard embodiments structure
        formatted = "以下结合具体实施例对本发明进行详细说明。\n\n"
        formatted += embodiments
        formatted += "\n\n本领域技术人员应当理解，上述实施例仅用于说明本发明，而不应视为限制本发明的范围。"

        return formatted

    def _extract_technical_features(self, invention_content: str, pse_matrix: Optional[PSEMatrix]) -> List[TechnicalFeature]:
        """Extract technical features from invention content and PSE matrix"""
        features = []

        # Extract from PSE matrix if available
        if pse_matrix and pse_matrix.kt_features:
            features.extend(pse_matrix.kt_features)

        # Extract key phrases from invention content
        key_phrases = self._extract_key_phrases(invention_content)
        for phrase in key_phrases:
            feature = TechnicalFeature(
                name=phrase,
                description=f"技术特征：{phrase}",
                category="invention_feature",
                is_essential=True
            )
            features.append(feature)

        # Remove duplicates
        unique_features = []
        seen_names = set()
        for feature in features:
            if feature.name not in seen_names:
                unique_features.append(feature)
                seen_names.add(feature.name)

        return unique_features

    def _extract_key_phrases(self, text: str) -> List[str]:
        """Extract key technical phrases from text"""
        # Look for patterns that indicate technical features
        patterns = [
            r'包括(.+?)[，。；]',  # 包括...，
            r'所述(.+?)[，。；]',   # 所述...，
            r'其特征在于(.+?)[，。；]',  # 其特征在于...，
            r'采用(.+?)[，。；]',  # 采用...，
            r'通过(.+?)[，。；]',  # 通过...，
        ]

        key_phrases = []
        import re
        for pattern in patterns:
            matches = re.findall(pattern, text)
            key_phrases.extend(matches)

        # Clean and filter
        cleaned_phrases = []
        for phrase in key_phrases:
            phrase = phrase.strip()
            if len(phrase) > 2 and len(phrase) < 50:  # Reasonable length
                cleaned_phrases.append(phrase)

        return cleaned_phrases[:10]  # Return top 10

    def _generate_independent_claim(self, title: str, technical_field: str,
                                   technical_features: List[TechnicalFeature]) -> IndependentClaim:
        """Generate independent claim"""

        # Build preamble
        preamble = f"一种{technical_field}技术，"

        # Build claim body from technical features
        essential_features = [f for f in technical_features if f.is_essential]

        if essential_features:
            body_parts = []
            for feature in essential_features[:3]:  # Use top 3 essential features
                body_parts.append(f"包括{feature.name}")

            body = "，".join(body_parts) + "。"
        else:
            body = "包括必要的技术特征。"

        return IndependentClaim(
            claim_number=1,
            preamble=preamble,
            transition="其特征在于",
            body=body,
            technical_features=essential_features
        )

    def _generate_dependent_claims(self, independent_claim: int,
                                  technical_features: List[TechnicalFeature]) -> List[DependentClaim]:
        """Generate dependent claims"""
        dependent_claims = []

        # Get non-essential features for dependent claims
        non_essential_features = [f for f in technical_features if not f.is_essential]

        # Generate up to 5 dependent claims
        for i, feature in enumerate(non_essential_features[:5]):
            claim = DependentClaim(
                claim_number=i + 2,
                parent_claim=1,  # 独立权利要求编号为1
                additional_features=f"所述技术还包括{feature.name}",
                technical_features=[feature]
            )
            dependent_claims.append(claim)

        return dependent_claims

    def _format_claims_text(self, independent_claims: List[IndependentClaim],
                           dependent_claims: List[DependentClaim]) -> str:
        """Format complete claims text"""
        text = "权利要求书\n\n"

        # Add independent claims
        for claim in independent_claims:
            text += f"权利要求{claim.claim_number}：\n"
            text += f"{claim.preamble}{claim.transition}{claim.body}\n\n"

        # Add dependent claims
        for claim in dependent_claims:
            text += f"权利要求{claim.claim_number}：\n"
            text += f"根据权利要求{claim.parent_claim}所述的{claim.additional_features}。\n\n"

        return text

    def _generate_summary(self, invention_content: str) -> str:
        """Generate abstract summary from invention content"""
        # Take first 200 characters or first paragraph
        summary = invention_content[:200]

        # Ensure it ends with a complete sentence
        if len(invention_content) > 200:
            # Find last sentence ending
            last_period = summary.rfind('。')
            last_comma = summary.rfind('，')

            if last_period > 150:  # If there's a period near the end
                summary = summary[:last_period + 1]
            elif last_comma > 150:  # If there's a comma near the end
                summary = summary[:last_comma + 1]
            else:
                summary += "..."

        return summary

    def _extract_examples(self, embodiments: str) -> List[str]:
        """Extract implementation examples from embodiments"""
        examples = []

        # Look for numbered examples or paragraphs starting with "实施例"
        import re

        # Pattern for numbered examples
        pattern1 = r'实施例\s*(\d+)[：:](.+?)(?=实施例|\n\n|$)'
        matches1 = re.findall(pattern1, embodiments, re.DOTALL)

        for match in matches1:
            examples.append(match[1].strip())

        # If no numbered examples found, split by paragraphs
        if not examples:
            paragraphs = embodiments.split('\n\n')
            for para in paragraphs:
                para = para.strip()
                if len(para) > 50:  # Reasonable length for an example
                    examples.append(para)

        return examples[:3]  # Return up to 3 examples

    def _generate_detailed_description(self, embodiments: str, pse_matrix: Optional[PSEMatrix]) -> str:
        """Generate detailed description for disclosure"""
        description = "以下对本发明的具体实施方式进行详细描述。\n\n"
        description += embodiments

        if pse_matrix:
            description += "\n\n本发明的技术方案基于以下分析：\n"
            if pse_matrix.problems:
                description += "\n需要解决的技术问题：\n"
                for problem in pse_matrix.problems:
                    description += f"- {problem}\n"

            if pse_matrix.solutions:
                description += "\n提出的技术解决方案：\n"
                for solution in pse_matrix.solutions:
                    description += f"- {solution}\n"

            if pse_matrix.effects:
                description += "\n达到的技术效果：\n"
                for effect in pse_matrix.effects:
                    description += f"- {effect}\n"

        return description

    def _extract_drawings(self, embodiments: str) -> List[str]:
        """Extract drawing descriptions from embodiments"""
        drawings = []

        import re

        # Look for drawing references
        patterns = [
            r'图\s*(\d+)\s*是(.+?)(?=[，。；])',
            r'附图\s*(\d+)\s*显示(.+?)(?=[，。；])',
            r'如图\s*(\d+)\s*所示(.+?)(?=[，。；])'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, embodiments)
            for match in matches:
                drawings.append(f"图{match[0]}：{match[1].strip()}")

        # If no specific drawing descriptions found, create generic ones
        if not drawings:
            drawings.append("图1：本发明的整体结构示意图")
            drawings.append("图2：关键部件的详细结构图")

        return drawings


def _new_trace_id() -> str:
    import uuid

    return str(uuid.uuid4())


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _strip_dep_prefix(text: str, parent_claim: int) -> str:
    import re

    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(r"^\s*\d+\s*[\.、]\s*", "", t)
    t = re.sub(rf"^根据权利要求\s*{parent_claim}\s*所述的", "", t)
    t = re.sub(r"^根据权利要求\s*\d+\s*所述的", "", t)
    return t.strip().lstrip("，").strip()


def _term_map_to_json(term_map: Dict[str, _LLMTermInfoContract]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in (term_map or {}).items():
        if not str(k).strip():
            continue
        out[str(k)] = {"definition": v.definition, "occurrences": v.occurrences}
    return out


def render_claims_markdown(independent_text: str, dependent_claims: List[_LLMDependentClaimContract]) -> str:
    """
    Render claims into Markdown-ish plain text used by this project.
    Keeps numbering stable and avoids the legacy "根据权利要求X所述的..." duplication.
    """
    lines = ["权利要求书", ""]
    lines.append("权利要求1：")
    lines.append(independent_text.strip())
    lines.append("")

    for dep in dependent_claims[:8]:
        num = str(dep.number).strip() or ""
        depends_on = str(dep.depends_on).strip() or "1"
        text = dep.text.strip()
        lines.append(f"权利要求{num}：")
        if text.startswith("根据权利要求") or text.startswith("依照权利要求"):
            lines.append(text)
        else:
            lines.append(f"根据权利要求{depends_on}所述的{text}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
