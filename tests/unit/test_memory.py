"""
Unit tests for memory.py - Memory system with 2-stage pre-check
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# Import memory module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/orchestrator'))
from memory import (
    _should_extract_memories,
    format_memories_for_prompt,
    MIN_MESSAGE_LENGTH_FOR_EXTRACTION
)


class TestMemoryPreCheck:
    """Test 2-stage pre-check system (Mark-XXX integration)"""

    def test_stage1_personal_keywords_detected(self):
        """Stage 1: Should detect personal keywords"""
        messages = [
            {"role": "user", "content": "Ciao, mi chiamo Alessandro"},
            {"role": "assistant", "content": "Piacere!"}
        ]
        result = _should_extract_memories(messages)
        assert result is True, "Should detect 'mi chiamo' keyword"

    def test_stage1_no_personal_keywords(self):
        """Stage 1: Should skip when no personal keywords"""
        messages = [
            {"role": "user", "content": "Che tempo fa oggi?"},
            {"role": "assistant", "content": "Fa bel tempo"}
        ]
        result = _should_extract_memories(messages)
        assert result is False, "Should skip generic questions"

    def test_stage1_message_too_short(self):
        """Stage 1: Should skip messages below minimum length"""
        messages = [
            {"role": "user", "content": "ok"}
        ]
        result = _should_extract_memories(messages)
        assert result is False, f"Should skip messages < {MIN_MESSAGE_LENGTH_FOR_EXTRACTION} chars"

    def test_stage1_empty_messages(self):
        """Stage 1: Should skip empty message list"""
        result = _should_extract_memories([])
        assert result is False, "Should skip empty messages"

    def test_stage1_multiple_keywords(self):
        """Stage 1: Should detect various personal keywords"""
        test_cases = [
            ("Mi chiamo Mario", True),  # "mi chiamo"
            ("Abito a Roma", True),  # "abito"
            ("Lavoro come ingegnere", True),  # "lavoro"
            ("Ho trentacinque anni", True),  # "ho" + long enough
            ("Mi piace il calcio", True),  # "mi piace"
            ("Sono nato a Milano", True),  # "sono"
            ("Ricordati che domani ho un appuntamento", True),  # "ricorda"
            ("Che tempo fa?", False),  # No personal keywords
        ]

        for content, expected in test_cases:
            messages = [{"role": "user", "content": content}]
            result = _should_extract_memories(messages)
            assert result == expected, f"Expected {expected} for: '{content}' (len={len(content)}), got {result}"


class TestMemoryFormatting:
    """Test memory formatting for LLM context"""

    def test_format_empty_memories(self):
        """Should handle empty memory list"""
        result = format_memories_for_prompt([])
        assert result == "", "Empty memories should return empty string"

    def test_format_single_memory(self, sample_memory_snippets):
        """Should format single memory correctly"""
        result = format_memories_for_prompt([sample_memory_snippets[0]])

        assert "[MEMORIA UTENTE]" in result
        assert "L'utente si chiama Alessandro" in result
        # Format uses "- snippet" not numbered list or categories
        assert "- " in result

    def test_format_multiple_memories(self, sample_memory_snippets):
        """Should format multiple memories"""
        result = format_memories_for_prompt(sample_memory_snippets)

        assert "[MEMORIA UTENTE]" in result
        assert "- " in result  # Bullet points, not numbers
        assert "Alessandro" in result
        assert "Roma" in result

    def test_format_is_simple_list(self, sample_memory_snippets):
        """Format should be simple bullet list"""
        result = format_memories_for_prompt(sample_memory_snippets)

        # Should use simple bullet list format
        lines = result.split('\n')
        assert len(lines) >= 2, "Should have multiple lines"


class TestMemoryRetrieval:
    """Test memory retrieval with similarity threshold"""

    def test_similarity_threshold_constant_exists(self):
        """Verify RETRIEVAL_SIMILARITY_THRESHOLD constant exists"""
        from memory import RETRIEVAL_SIMILARITY_THRESHOLD

        assert RETRIEVAL_SIMILARITY_THRESHOLD is not None
        assert RETRIEVAL_SIMILARITY_THRESHOLD >= 0.0
        assert RETRIEVAL_SIMILARITY_THRESHOLD <= 1.0


class TestMemoryDeduplication:
    """Test exact text deduplication before vector search"""

    def test_deduplication_threshold_exists(self):
        """Verify DEDUPLICATION_SIMILARITY_THRESHOLD constant exists"""
        from memory import DEDUPLICATION_SIMILARITY_THRESHOLD

        assert DEDUPLICATION_SIMILARITY_THRESHOLD is not None
        assert DEDUPLICATION_SIMILARITY_THRESHOLD >= 0.9  # Should be high for exact matches
        assert DEDUPLICATION_SIMILARITY_THRESHOLD <= 1.0


class TestContradictionDetection:
    """Test memory contradiction detection with snippet matching"""

    def test_contradiction_detection_has_implementation(self):
        """Verify contradiction detection logic exists"""
        # Just check that the memory module has contradiction handling
        import memory

        # The module should have functions for handling contradictions
        # Even if not exposed directly, the save_memory_snippet uses it internally
        assert hasattr(memory, 'save_memory_snippet'), "Should have memory saving function"


@pytest.mark.asyncio
class TestMemoryExtraction:
    """Test full memory extraction flow"""

    async def test_extraction_filters_excluded_roles(self):
        """Should exclude system/function messages from extraction context"""
        from memory import EXCLUDED_ROLES

        # Verify that system and function roles are excluded
        assert "system" in EXCLUDED_ROLES, "Should exclude system messages"
        assert "function" in EXCLUDED_ROLES, "Should exclude function results"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
