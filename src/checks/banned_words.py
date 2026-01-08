"""
Banned Words Checker (Gate D)
Checks for prohibited words and phrases in patent documents
"""

import re
from typing import List, Dict, Any, Tuple, Set
from core.patent_document import PatentDocument

class BannedWordsChecker:
    """Checks for banned/prohibited words in patent documents"""

    def __init__(self):
        # Initialize banned word categories
        self.banned_categories = {
            'absolute_terms': {
                'words': [
                    '绝对', '完全', '彻底', '始终', '永远', '必然', '必定',
                    '一定', '肯定', '无疑', '毋庸置疑', '百分之百', '百分百',
                    'absolute', 'completely', 'totally', 'always', 'forever',
                    'certainly', 'definitely', 'undoubtedly', '100%', 'hundred percent'
                ],
                'severity': 'high',
                'reason': 'Absolute terms are generally not allowed in patents as they imply unlimited scope'
            },
            'vague_terms': {
                'words': [
                    '大约', '大概', '左右', '差不多', '基本', '主要', '大致',
                    '近似', '接近', '相当', '比较', '较为', '相对',
                    'approximately', 'about', 'roughly', 'basically', 'mainly',
                    'generally', 'relatively', 'comparatively'
                ],
                'severity': 'medium',
                'reason': 'Vague terms can lead to unclear claim scope'
            },
            'subjective_terms': {
                'words': [
                    '美观', '漂亮', '好看', '舒适', '方便', '简单', '容易',
                    '显然', '明显', '众所周知', '容易理解', '显而易见',
                    'beautiful', 'pretty', 'comfortable', 'convenient', 'simple',
                    'obvious', 'apparently', 'well-known', 'easy to understand'
                ],
                'severity': 'medium',
                'reason': 'Subjective terms are not objectively measurable'
            },
            'commercial_terms': {
                'words': [
                    '便宜', '昂贵', '经济', '实惠', '划算', '性价比高',
                    '低成本', '高利润', '畅销', '市场', '销售', '盈利',
                    'cheap', 'expensive', 'economic', 'affordable', 'cost-effective',
                    'low cost', 'high profit', 'best-selling', 'market', 'sales'
                ],
                'severity': 'low',
                'reason': 'Commercial terms are generally discouraged in technical patents'
            },
            'discriminatory_terms': {
                'words': [
                    '最佳', '最优', '最好', '最强', '最高', '最低', '最小',
                    '最大', '最先进', '最新', '首创', '第一', '唯一',
                    'best', 'optimal', 'superior', 'strongest', 'highest',
                    'lowest', 'smallest', 'largest', 'most advanced', 'latest',
                    'first', 'only', 'unique'
                ],
                'severity': 'high',
                'reason': 'Discriminatory terms imply superiority and should be avoided'
            }
        }

        # Compile regex patterns for efficient matching
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for banned words"""
        self.patterns = {}
        for category, data in self.banned_categories.items():
            # Create word boundary patterns for exact matching
            patterns = []
            for word in data['words']:
                # For Chinese characters, use different approach
                if any('\u4e00' <= c <= '\u9fff' for c in word):
                    patterns.append(re.escape(word))
                else:
                    # For English/alphabetic words, use word boundaries
                    patterns.append(r'\b' + re.escape(word) + r'\b')

            # Combine patterns with OR
            self.patterns[category] = re.compile('|'.join(patterns), re.IGNORECASE)

    def check(self, patent_doc: PatentDocument) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Check for banned words in patent document
        Returns: (passed, score, details)
        """
        details = {
            'total_violations': 0,
            'violations_by_category': {},
            'violations_by_severity': {'high': 0, 'medium': 0, 'low': 0},
            'critical_violations': [],
            'all_violations': [],
            'recommendations': [],
            'errors': [],
            'warnings': []
        }

        try:
            # Extract text from all sections
            all_text = self._extract_all_text(patent_doc)

            if not all_text:
                details['errors'].append("No text content found in patent document")
                return False, 0.0, details

            # Check each category
            total_violations = 0
            for category, data in self.banned_categories.items():
                violations = self._check_category(all_text, category, data)
                if violations:
                    details['violations_by_category'][category] = violations
                    details['violations_by_severity'][data['severity']] += len(violations)
                    details['all_violations'].extend(violations)
                    total_violations += len(violations)

                    # Identify critical violations
                    if data['severity'] == 'high':
                        details['critical_violations'].extend(violations)

            details['total_violations'] = total_violations

            # Determine pass/fail and score
            if details['violations_by_severity']['high'] > 0:
                passed = False
                base_score = 0.0
                details['recommendations'].append("Remove all high-severity banned words before submission")
            elif details['violations_by_severity']['medium'] > 5:
                passed = False
                base_score = 0.3
                details['recommendations'].append("Reduce the number of medium-severity banned words")
            elif total_violations > 0:
                passed = True
                # Score based on number of violations
                if total_violations <= 3:
                    base_score = 0.8
                elif total_violations <= 10:
                    base_score = 0.6
                else:
                    base_score = 0.4
                details['recommendations'].append("Consider revising to remove banned words for better quality")
            else:
                passed = True
                base_score = 1.0
                details['recommendations'].append("Excellent: No banned words detected")

            # Adjust score based on severity mix
            score = self._calculate_final_score(base_score, details)

            return passed, score, details

        except Exception as e:
            details['errors'].append(f"Banned words check failed: {str(e)}")
            return False, 0.0, details

    def _extract_all_text(self, patent_doc: PatentDocument) -> str:
        """Extract text from all sections of the patent document"""
        text_parts = []

        # Add title
        if patent_doc.metadata.title:
            text_parts.append(patent_doc.metadata.title)

        # Add specification content
        if patent_doc.specification:
            if patent_doc.specification.technical_field:
                text_parts.append(patent_doc.specification.technical_field)
            if patent_doc.specification.background_art:
                text_parts.append(patent_doc.specification.background_art)
            if patent_doc.specification.invention_content:
                text_parts.append(patent_doc.specification.invention_content)
            if patent_doc.specification.embodiments:
                text_parts.append(patent_doc.specification.embodiments)
            if patent_doc.specification.description_of_drawings:
                text_parts.append(patent_doc.specification.description_of_drawings)

        # Add claims content
        if patent_doc.claims and patent_doc.claims.content:
            text_parts.append(patent_doc.claims.content)

        # Add abstract content
        if patent_doc.abstract:
            if patent_doc.abstract.title:
                text_parts.append(patent_doc.abstract.title)
            if patent_doc.abstract.technical_field:
                text_parts.append(patent_doc.abstract.technical_field)
            if patent_doc.abstract.summary:
                text_parts.append(patent_doc.abstract.summary)

        # Add disclosure content
        if patent_doc.disclosure:
            if patent_doc.disclosure.detailed_description:
                text_parts.append(patent_doc.disclosure.detailed_description)
            for example in patent_doc.disclosure.examples:
                text_parts.append(example)
            for drawing in patent_doc.disclosure.drawings:
                text_parts.append(drawing)

        return ' '.join(text_parts)

    def _check_category(self, text: str, category: str, category_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for banned words in a specific category"""
        violations = []

        try:
            pattern = self.patterns.get(category)
            if not pattern:
                return violations

            # Find all matches
            for match in pattern.finditer(text):
                violation = {
                    'word': match.group(0),
                    'position': match.start(),
                    'context': self._get_context(text, match.start(), match.end()),
                    'category': category,
                    'severity': category_data['severity'],
                    'reason': category_data['reason']
                }
                violations.append(violation)

        except Exception as e:
            # Log error but continue checking other categories
            violations.append({
                'error': f"Error checking category {category}: {str(e)}"
            })

        return violations

    def _get_context(self, text: str, start: int, end: int, context_size: int = 30) -> str:
        """Get context around a matched banned word"""
        context_start = max(0, start - context_size)
        context_end = min(len(text), end + context_size)

        context = text[context_start:context_end]

        # Highlight the banned word
        relative_start = start - context_start
        relative_end = end - context_start

        highlighted = (context[:relative_start] +
                      f"[{context[relative_start:relative_end]}]" +
                      context[relative_end:])

        return highlighted.strip()

    def _calculate_final_score(self, base_score: float, details: Dict[str, Any]) -> float:
        """Calculate final score based on violation details"""
        score = base_score

        # Penalize based on severity
        high_severity = details['violations_by_severity']['high']
        medium_severity = details['violations_by_severity']['medium']
        low_severity = details['violations_by_severity']['low']

        # High severity violations have maximum impact
        score -= high_severity * 0.3

        # Medium severity violations have moderate impact
        score -= medium_severity * 0.1

        # Low severity violations have minimal impact
        score -= low_severity * 0.05

        # Ensure score doesn't go below 0
        return max(0.0, score)

    def get_banned_words_by_category(self, category: str) -> List[str]:
        """Get banned words for a specific category"""
        if category in self.banned_categories:
            return self.banned_categories[category]['words']
        return []

    def add_custom_banned_words(self, words: List[str], category: str = 'custom',
                               severity: str = 'medium', reason: str = 'Custom banned words'):
        """Add custom banned words"""
        if category not in self.banned_categories:
            self.banned_categories[category] = {
                'words': [],
                'severity': severity,
                'reason': reason
            }

        self.banned_categories[category]['words'].extend(words)

        # Recompile patterns
        self._compile_patterns()

    def remove_banned_words(self, text: str) -> str:
        """Remove banned words from text (for suggestions)"""
        cleaned_text = text

        for category, data in self.banned_categories.items():
            pattern = self.patterns.get(category)
            if pattern:
                # Replace with placeholder or remove
                cleaned_text = pattern.sub('[REDACTED]', cleaned_text)

        return cleaned_text

    def suggest_alternatives(self, banned_word: str) -> List[str]:
        """Suggest alternatives for banned words"""
        alternatives = {
            '绝对': ['相对', '基本上', '在大多数情况下'],
            '完全': ['基本上', '在很大程度上', '显著地'],
            '最佳': ['优选', '合适的', '适当的'],
            '最优': ['较优', '合适的', '令人满意的'],
            '大约': ['约', '大致', '左右'],
            '美观': ['符合审美要求', '视觉上令人愉悦', '具有吸引力'],
            '便宜': ['成本较低', '经济实用', '具有成本效益']
        }

        return alternatives.get(banned_word, ['[请使用更准确的术语]'])

    def health_check(self) -> bool:
        """Health check for the checker"""
        try:
            # Test with simple text
            test_text = "这是一个测试文本，包含一些最佳和绝对的术语。"
            test_doc = PatentDocument(
                metadata={'title': 'Test Patent', 'technical_field': 'Test Field'}
            )

            # Mock specification
            from ..core.patent_document import Specification
            test_doc.specification = Specification(
                technical_field="测试技术领域",
                background_art="测试背景技术",
                invention_content="测试发明内容",
                embodiments="测试具体实施方式",
                content=test_text
            )

            passed, score, details = self.check(test_doc)
            return True  # If we can run the check, it's healthy
        except Exception:
            return False

    def get_statistics(self, violations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about violations"""
        stats = {
            'total_violations': len(violations),
            'by_category': {},
            'by_severity': {'high': 0, 'medium': 0, 'low': 0},
            'most_common_words': {}
        }

        word_count = {}
        for violation in violations:
            category = violation.get('category', 'unknown')
            severity = violation.get('severity', 'unknown')
            word = violation.get('word', 'unknown')

            # Count by category
            if category not in stats['by_category']:
                stats['by_category'][category] = 0
            stats['by_category'][category] += 1

            # Count by severity
            if severity in stats['by_severity']:
                stats['by_severity'][severity] += 1

            # Count word frequency
            if word not in word_count:
                word_count[word] = 0
            word_count[word] += 1

        # Get most common words
        sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
        stats['most_common_words'] = dict(sorted_words[:10])

        return stats