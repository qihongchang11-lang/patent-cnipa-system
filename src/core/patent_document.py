"""
Core patent document models for CNIPA compliance
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

class DocumentType(str, Enum):
    """Document types for CNIPA patents"""
    INVENTION = "invention"
    UTILITY_MODEL = "utility_model"
    DESIGN = "design"

class ClaimType(str, Enum):
    """Types of patent claims"""
    INDEPENDENT = "independent"
    DEPENDENT = "dependent"

class TechnicalFeature(BaseModel):
    """Technical feature in a patent"""
    name: str = Field(..., description="Feature name")
    description: str = Field(..., description="Feature description")
    category: str = Field(..., description="Feature category")
    is_essential: bool = Field(default=False, description="Whether this is an essential feature")
    references: List[str] = Field(default_factory=list, description="Reference numbers")

class MetaData(BaseModel):
    """Patent document metadata"""
    title: str = Field(..., description="Invention title")
    application_number: Optional[str] = Field(None, description="Application number")
    filing_date: Optional[datetime] = Field(None, description="Filing date")
    priority_date: Optional[datetime] = Field(None, description="Priority date")
    applicant: Optional[str] = Field(None, description="Applicant name")
    inventor: Optional[str] = Field(None, description="Inventor name")
    agent: Optional[str] = Field(None, description="Patent agent")
    technical_field: str = Field(..., description="Technical field")
    document_type: DocumentType = Field(default=DocumentType.INVENTION)
    language: str = Field(default="zh-CN", description="Document language")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class IndependentClaim(BaseModel):
    """Independent patent claim"""
    claim_number: int = Field(..., description="Claim number")
    preamble: str = Field(..., description="Claim preamble")
    transition: str = Field(default="其特征在于", description="Transition phrase")
    body: str = Field(..., description="Claim body")
    technical_features: List[TechnicalFeature] = Field(default_factory=list)

class DependentClaim(BaseModel):
    """Dependent patent claim"""
    claim_number: int = Field(..., description="Claim number")
    parent_claim: int = Field(..., description="Parent claim number")
    additional_features: str = Field(..., description="Additional features")
    technical_features: List[TechnicalFeature] = Field(default_factory=list)

    @property
    def claimnumber(self) -> int:
        """Backward compatibility alias"""
        return self.claim_number

    @property
    def parentclaim(self) -> int:
        """Backward compatibility alias"""
        return self.parent_claim

class Claims(BaseModel):
    """Patent claims section"""
    independent_claims: List[IndependentClaim] = Field(default_factory=list)
    dependent_claims: List[DependentClaim] = Field(default_factory=list)
    content: str = Field(default="", description="Complete claims text")

class Specification(BaseModel):
    """Patent specification (说明书)"""
    technical_field: str = Field(..., description="技术领域")
    background_art: str = Field(..., description="背景技术")
    invention_content: str = Field(..., description="发明内容")
    description_of_drawings: Optional[str] = Field(None, description="附图说明")
    embodiments: str = Field(..., description="具体实施方式")
    content: str = Field(default="", description="Complete specification text")

class Abstract(BaseModel):
    """Patent abstract (摘要)"""
    title: str = Field(..., description="发明名称")
    technical_field: str = Field(..., description="技术领域")
    summary: str = Field(..., description="摘要内容", max_length=500)
    main_figure_description: Optional[str] = Field(None, description="主要附图说明")
    content: str = Field(default="", description="Complete abstract text")

class Disclosure(BaseModel):
    """Patent disclosure (具体实施方式)"""
    detailed_description: str = Field(..., description="详细描述")
    examples: List[str] = Field(default_factory=list, description="实施例")
    drawings: List[str] = Field(default_factory=list, description="附图描述")
    content: str = Field(default="", description="Complete disclosure text")

class PSEMatrix(BaseModel):
    """Problem-Solution-Effect matrix"""
    problems: List[str] = Field(default_factory=list, description="Technical problems")
    solutions: List[str] = Field(default_factory=list, description="Technical solutions")
    effects: List[str] = Field(default_factory=list, description="Technical effects")
    kt_features: List[TechnicalFeature] = Field(default_factory=list, description="Key technical features")
    audit: Dict[str, Any] = Field(default_factory=dict, description="Audit metadata for extraction")

class PatentDocument(BaseModel):
    """Complete patent document"""
    metadata: MetaData
    specification: Optional[Specification] = None
    claims: Optional[Claims] = None
    abstract: Optional[Abstract] = None
    disclosure: Optional[Disclosure] = None
    pse_matrix: Optional[PSEMatrix] = None
    quality_score: Optional[float] = Field(None, description="Overall quality score")
    quality_report: Optional[Dict[str, Any]] = Field(None, description="Quality check results")
    audit: Dict[str, Any] = Field(default_factory=dict, description="Audit metadata for the run (LLM/rules, trace ids)")
    document_version: int = Field(default=1, description="Document version for optimistic locking")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def get_all_claims(self) -> List[str]:
        """Get all claims as text list"""
        claims = []
        if self.claims:
            for claim in self.claims.independent_claims:
                claims.append(f"{claim.claim_number}. {claim.preamble} {claim.transition} {claim.body}")
            for claim in self.claims.dependent_claims:
                claims.append(f"{claim.claim_number}. 根据权利要求{claim.parent_claim}所述的{claim.additional_features}")
        return claims

    def get_technical_features(self) -> List[TechnicalFeature]:
        """Get all technical features from the document"""
        features = []
        if self.pse_matrix and self.pse_matrix.kt_features:
            features.extend(self.pse_matrix.kt_features)
        if self.claims:
            for claim in self.claims.independent_claims:
                features.extend(claim.technical_features)
            for claim in self.claims.dependent_claims:
                features.extend(claim.technical_features)
        return features

    def to_markdown(self) -> str:
        """Convert patent document to markdown format"""
        md_parts = []

        # Title
        md_parts.append(f"# {self.metadata.title}")
        md_parts.append("")

        # Abstract
        if self.abstract:
            md_parts.append("## 摘要")
            md_parts.append(f"**技术领域:** {self.abstract.technical_field}")
            md_parts.append(f"**发明名称:** {self.abstract.title}")
            md_parts.append("")
            md_parts.append(self.abstract.summary)
            if self.abstract.main_figure_description:
                md_parts.append("")
                md_parts.append(f"**主要附图:** {self.abstract.main_figure_description}")
            md_parts.append("")

        # Specification
        if self.specification:
            md_parts.append("## 说明书")
            md_parts.append("")
            md_parts.append("### 技术领域")
            md_parts.append(self.specification.technical_field)
            md_parts.append("")
            md_parts.append("### 背景技术")
            md_parts.append(self.specification.background_art)
            md_parts.append("")
            md_parts.append("### 发明内容")
            md_parts.append(self.specification.invention_content)
            md_parts.append("")
            if self.specification.description_of_drawings:
                md_parts.append("### 附图说明")
                md_parts.append(self.specification.description_of_drawings)
                md_parts.append("")
            md_parts.append("### 具体实施方式")
            md_parts.append(self.specification.embodiments)
            md_parts.append("")

        # Claims
        if self.claims:
            md_parts.append("## 权利要求书")
            md_parts.append("")
            for i, claim in enumerate(self.claims.independent_claims, 1):
                md_parts.append(f"**权利要求 {claim.claim_number}**")
                md_parts.append(f"{claim.preamble} {claim.transition} {claim.body}")
                md_parts.append("")
            for claim in self.claims.dependent_claims:
                md_parts.append(f"**权利要求 {claim.claim_number}**")
                md_parts.append(f"根据权利要求{claim.parent_claim}所述的{claim.additional_features}")
                md_parts.append("")

        # Disclosure
        if self.disclosure:
            md_parts.append("## 具体实施方式")
            md_parts.append(self.disclosure.detailed_description)
            if self.disclosure.examples:
                md_parts.append("")
                md_parts.append("### 实施例")
                for i, example in enumerate(self.disclosure.examples, 1):
                    md_parts.append(f"**实施例 {i}:** {example}")
            if self.disclosure.drawings:
                md_parts.append("")
                md_parts.append("### 附图")
                for drawing in self.disclosure.drawings:
                    md_parts.append(f"- {drawing}")

        return "\n".join(md_parts)
