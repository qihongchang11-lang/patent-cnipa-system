"""
Problem-Solution-Effect (PSE) Matrix Extractor
Extracts technical problems, solutions, and effects from patent drafts
"""

import logging
import re
import jieba
import jieba.posseg as pseg
import uuid
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from core.patent_document import PSEMatrix, TechnicalFeature
from utils.llm_client import LLMClient
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class _LLMTechnicalFeature(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    category: str = Field(default="technical_feature")
    is_essential: bool = Field(default=True)


class _LLMPSEDraft(BaseModel):
    problems: List[str] = Field(default_factory=list)
    solutions: List[str] = Field(default_factory=list)
    effects: List[str] = Field(default_factory=list)
    kt_features: List[_LLMTechnicalFeature] = Field(default_factory=list)

class PSEExtractor:
    """Extracts Problem-Solution-Effect matrix from patent text"""

    def __init__(self, llm_client: Optional[LLMClient] = None, force_rules: bool = False):
        # Initialize jieba
        jieba.initialize()
        self.llm_client = llm_client or LLMClient()
        self.force_rules = force_rules

        # Define keyword patterns for problem identification
        self.problem_keywords = [
            '问题', '缺陷', '不足', '缺点', '弊端', '困难', '障碍', '挑战',
            '难以', '无法', '不能', '限制', '局限', '瓶颈', '痛点',
            'problem', 'issue', 'defect', 'drawback', 'limitation'
        ]

        # Define keyword patterns for solution identification
        self.solution_keywords = [
            '解决', '克服', '改进', '优化', '提升', '提高', '增强',
            '方法', '技术方案', '措施', '手段', '途径', '策略',
            'solve', 'resolve', 'improve', 'enhance', 'method', 'solution'
        ]

        # Define keyword patterns for effect identification
        self.effect_keywords = [
            '效果', '效益', '优点', '优势', '改进', '提升', '提高',
            '增强', '降低', '减少', '避免', '防止', '实现',
            'effect', 'benefit', 'advantage', 'improvement'
        ]

        # Technical feature patterns
        self.feature_patterns = [
            r'包括(.+?)[，。；]',  # 包括...，
            r'所述(.+?)[，。；]',   # 所述...，
            r'其特征在于(.+?)[，。；]',  # 其特征在于...，
            r'采用(.+?)[，。；]',  # 采用...，
            r'通过(.+?)[，。；]',  # 通过...，
            r'设置有(.+?)[，。；]',  # 设置有...，
        ]

    def extract_from_text(self, text: str) -> PSEMatrix:
        """
        Hybrid extraction:
        1) Try LLM structured extraction
        2) Soft-fail to rules

        Always returns a PSEMatrix with an audit trail in `audit`.
        """
        clean_text = self._preprocess_text(text or "")

        if not clean_text.strip():
            matrix = self._extract_with_rules(clean_text)
            matrix.audit = {
                "extraction_source": "rules",
                "fallback_reason": "empty_text",
                "llm": self.llm_client.get_config_meta(),
                "trace_id": str(uuid.uuid4()),
            }
            return matrix

        if not self.force_rules:
            llm_matrix = self._extract_with_llm(clean_text)
            if llm_matrix is not None:
                return llm_matrix

        matrix = self._extract_with_rules(clean_text)
        # keep the last_meta if we attempted llm
        last = self.llm_client.get_last_meta()
        matrix.audit = {
            "extraction_source": "rules",
            "fallback_reason": "forced_rules" if self.force_rules else "llm_unavailable_or_invalid",
            "llm": self.llm_client.get_config_meta(),
            "trace_id": getattr(last, "trace_id", None) or str(uuid.uuid4()),
        }
        return matrix

    def _extract_with_llm(self, text: str) -> Optional[PSEMatrix]:
        if not self.llm_client.is_configured():
            return None

        prompt = (
            "从给定专利草稿文本中抽取 PSE（Problem/Solution/Effect）并识别关键技术特征。\n"
            "要求：\n"
            "- 使用中文输出\n"
            "- problems/solutions/effects 各给出 1~5 条，尽量短且可复用\n"
            "- kt_features 为关键技术特征列表（对象），name 为名词短语\n"
            "- 仅输出 JSON\n\n"
            f"专利草稿文本：\n{text}"
        )

        draft = self.llm_client.generate_structured_data(prompt, _LLMPSEDraft, retries=2)
        if draft is None:
            return None

        meta = self.llm_client.get_last_meta()
        features = []
        for f in draft.kt_features:
            features.append(
                TechnicalFeature(
                    name=f.name.strip(),
                    description=(f.description or f"技术特征：{f.name}").strip(),
                    category=f.category or "technical_feature",
                    is_essential=bool(f.is_essential),
                )
            )

        matrix = PSEMatrix(
            problems=[p.strip() for p in draft.problems if p.strip()][:5],
            solutions=[s.strip() for s in draft.solutions if s.strip()][:5],
            effects=[e.strip() for e in draft.effects if e.strip()][:5],
            kt_features=features[:20],
        )
        ktf_index = {}
        for i, feat in enumerate(matrix.kt_features, 1):
            if getattr(feat, "name", None):
                ktf_index[f"F{i}"] = feat.name
        matrix.audit = {
            "extraction_source": "llm",
            "fallback_reason": None,
            "llm": self.llm_client.get_config_meta(),
            "trace_id": getattr(meta, "trace_id", None),
            "ktf_index": ktf_index,
        }
        return matrix

    def _extract_with_rules(self, text: str) -> PSEMatrix:
        """Existing rule-based extraction (preserved)."""
        # Extract problems
        problems = self._extract_problems(text)
        # Extract solutions
        solutions = self._extract_solutions(text)
        # Extract effects
        effects = self._extract_effects(text)
        # Extract key technical features
        kt_features = self._extract_technical_features(text)

        matrix = PSEMatrix(
            problems=problems,
            solutions=solutions,
            effects=effects,
            kt_features=kt_features,
        )
        ktf_index = {}
        for i, feat in enumerate(matrix.kt_features, 1):
            if getattr(feat, "name", None):
                ktf_index[f"F{i}"] = feat.name
        matrix.audit = matrix.audit or {}
        matrix.audit["ktf_index"] = ktf_index
        return matrix

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for better extraction"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())

        # Remove special characters but keep Chinese punctuation
        text = re.sub(r'[^\u4e00-\u9fff\w\s，。；：！？（）【】]', '', text)

        return text

    def _extract_problems(self, text: str) -> List[str]:
        """Extract technical problems from text"""
        problems = []

        # Split text into sentences
        sentences = self._split_sentences(text)

        for sentence in sentences:
            # Check if sentence contains problem keywords
            if any(keyword in sentence for keyword in self.problem_keywords):
                # Extract the problem description
                problem_desc = self._extract_problem_sentence(sentence)
                if problem_desc and len(problem_desc) > 10:  # Filter short descriptions
                    problems.append(problem_desc)

        # Remove duplicates and similar problems
        problems = self._remove_similar(problems, threshold=0.7)

        return problems[:5]  # Return top 5 problems

    def _extract_solutions(self, text: str) -> List[str]:
        """Extract technical solutions from text"""
        solutions = []

        # Split text into sentences
        sentences = self._split_sentences(text)

        for sentence in sentences:
            # Check if sentence contains solution keywords
            if any(keyword in sentence for keyword in self.solution_keywords):
                # Extract the solution description
                solution_desc = self._extract_solution_sentence(sentence)
                if solution_desc and len(solution_desc) > 10:
                    solutions.append(solution_desc)

        # Remove duplicates and similar solutions
        solutions = self._remove_similar(solutions, threshold=0.7)

        return solutions[:5]  # Return top 5 solutions

    def _extract_effects(self, text: str) -> List[str]:
        """Extract technical effects from text"""
        effects = []

        # Split text into sentences
        sentences = self._split_sentences(text)

        for sentence in sentences:
            # Check if sentence contains effect keywords
            if any(keyword in sentence for keyword in self.effect_keywords):
                # Extract the effect description
                effect_desc = self._extract_effect_sentence(sentence)
                if effect_desc and len(effect_desc) > 10:
                    effects.append(effect_desc)

        # Remove duplicates and similar effects
        effects = self._remove_similar(effects, threshold=0.7)

        return effects[:5]  # Return top 5 effects

    def _extract_technical_features(self, text: str) -> List[TechnicalFeature]:
        """Extract key technical features from text"""
        features = []

        # Use regex patterns to find technical features
        for pattern in self.feature_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match.strip()) > 2:  # Filter very short matches
                    feature = TechnicalFeature(
                        name=match.strip(),
                        description=f"技术特征：{match.strip()}",
                        category="technical_feature",
                        is_essential=True
                    )
                    features.append(feature)

        # Use jieba to identify technical terms
        words = pseg.cut(text)
        for word, flag in words:
            # Focus on nouns and technical terms
            if flag in ['n', 'nz', 'nw'] and len(word) > 1:
                if self._is_technical_term(word, text):
                    feature = TechnicalFeature(
                        name=word,
                        description=f"技术术语：{word}",
                        category="technical_term",
                        is_essential=False
                    )
                    # Avoid duplicates
                    if not any(f.name == word for f in features):
                        features.append(feature)

        return features[:20]  # Return top 20 features

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences using Chinese punctuation"""
        # Split by Chinese sentence endings
        sentences = re.split(r'[。！？；]', text)
        # Clean and filter
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]
        return sentences

    def _extract_problem_sentence(self, sentence: str) -> str:
        """Extract problem description from sentence"""
        # Look for patterns like "存在的问题是..." or "缺点是..."
        patterns = [
            r'(.{2,}?)的?问题[是：](.+?)(?=[，。；])',
            r'(.{2,}?)的?缺点[是：](.+?)(?=[，。；])',
            r'(.{2,}?)的?不足[是：](.+?)(?=[，。；])',
            r'存在(.+?)(?=[，。；])',
        ]

        for pattern in patterns:
            match = re.search(pattern, sentence)
            if match:
                return match.group(0)

        # Return the whole sentence if no specific pattern found
        return sentence

    def _extract_solution_sentence(self, sentence: str) -> str:
        """Extract solution description from sentence"""
        # Look for patterns like "解决方法是..." or "采用...技术方案"
        patterns = [
            r'(.{2,}?)解决(.+?)(?=[，。；])',
            r'(.{2,}?)采用(.+?)(?=[，。；])',
            r'(.{2,}?)通过(.+?)(?=[，。；])',
            r'技术方案[是：](.+?)(?=[，。；])',
        ]

        for pattern in patterns:
            match = re.search(pattern, sentence)
            if match:
                return match.group(0)

        return sentence

    def _extract_effect_sentence(self, sentence: str) -> str:
        """Extract effect description from sentence"""
        # Look for patterns like "效果是..." or "能够..."
        patterns = [
            r'(.{2,}?)效果[是：](.+?)(?=[，。；])',
            r'(.{2,}?)优点[是：](.+?)(?=[，。；])',
            r'(.{2,}?)能够(.+?)(?=[，。；])',
            r'(.{2,}?)实现(.+?)(?=[，。；])',
        ]

        for pattern in patterns:
            match = re.search(pattern, sentence)
            if match:
                return match.group(0)

        return sentence

    def _is_technical_term(self, word: str, context: str) -> bool:
        """Determine if a word is likely a technical term"""
        # Filter out common words
        common_words = {
            '的', '了', '在', '是', '有', '和', '与', '或', '但', '而', '为',
            '可以', '能够', '进行', '使用', '采用', '通过', '设置', '安装',
            'the', 'and', 'or', 'but', 'with', 'for', 'of', 'in', 'on', 'at'
        }

        if word in common_words:
            return False

        # Check if word appears in technical contexts
        technical_indicators = ['技术', '装置', '设备', '系统', '方法', '工艺', '结构', '组件']
        if any(indicator in context[max(0, context.find(word)-50):context.find(word)+len(word)+50]
               for indicator in technical_indicators):
            return True

        # Check word length (technical terms are usually 2-8 characters)
        if len(word) < 2 or len(word) > 8:
            return False

        return True

    def _remove_similar(self, items: List[str], threshold: float = 0.7) -> List[str]:
        """Remove similar/duplicate items"""
        unique_items = []

        for item in items:
            is_similar = False
            for existing in unique_items:
                similarity = self._calculate_similarity(item, existing)
                if similarity > threshold:
                    is_similar = True
                    break

            if not is_similar:
                unique_items.append(item)

        return unique_items

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings using Jaccard similarity"""
        # Simple Jaccard similarity on character level
        set1 = set(str1)
        set2 = set(str2)

        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))

        if union == 0:
            return 0.0

        return intersection / union

    def build_ktf_dag(self, pse_matrix: PSEMatrix) -> Dict[str, List[str]]:
        """Build Key Technical Features Directed Acyclic Graph"""
        dag = defaultdict(list)

        # Create nodes for each technical feature
        features = pse_matrix.kt_features

        # Simple dependency analysis based on feature names
        for i, feature1 in enumerate(features):
            for j, feature2 in enumerate(features):
                if i != j:
                    # If feature1 name appears in feature2 description, there's a dependency
                    if feature1.name in feature2.description:
                        dag[feature1.name].append(feature2.name)

        return dict(dag)

    def analyze_pse_coherence(self, pse_matrix: PSEMatrix) -> Dict[str, float]:
        """Analyze coherence between problems, solutions, and effects"""
        coherence_scores = {}

        # Problem-solution coherence
        if pse_matrix.problems and pse_matrix.solutions:
            coherence_scores['problem_solution'] = self._calculate_semantic_coherence(
                ' '.join(pse_matrix.problems),
                ' '.join(pse_matrix.solutions)
            )

        # Solution-effect coherence
        if pse_matrix.solutions and pse_matrix.effects:
            coherence_scores['solution_effect'] = self._calculate_semantic_coherence(
                ' '.join(pse_matrix.solutions),
                ' '.join(pse_matrix.effects)
            )

        return coherence_scores

    def _calculate_semantic_coherence(self, text1: str, text2: str) -> float:
        """Calculate semantic coherence between two texts (simplified)"""
        # Simple word overlap measure
        words1 = set(jieba.lcut(text1))
        words2 = set(jieba.lcut(text2))

        if not words1 or not words2:
            return 0.0

        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        if union == 0:
            return 0.0

        return intersection / union
