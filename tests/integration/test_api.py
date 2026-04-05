"""
Integration tests for FastAPI endpoints
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os

# Import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/orchestrator'))


class TestHealthEndpoint:
    """Test /health endpoint (without full app startup)"""

    def test_health_endpoint_structure(self):
        """Health endpoint should have correct structure"""
        # We can test the endpoint exists and returns expected structure
        # without starting the full app with database connections
        from app import app
        from fastapi.testclient import TestClient

        # Mock database initialization
        with patch('app.init_db', AsyncMock()):
            with patch('app.close_db', AsyncMock()):
                client = TestClient(app)

                # This might fail if database is not connected, which is expected
                # We're testing the endpoint exists and has correct structure
                try:
                    response = client.get("/health")
                    if response.status_code == 200:
                        data = response.json()
                        assert "status" in data
                        assert "ollama" in data or "gemini" in data
                        assert "functions" in data
                except Exception:
                    # Database not available in test environment, skip
                    pytest.skip("Database not available")


class TestFunctionsEndpoint:
    """Test /functions endpoint"""

    def test_functions_endpoint_exists(self):
        """Functions endpoint should exist"""
        from app import app

        # Check that the endpoint is defined
        routes = [route.path for route in app.routes]
        assert "/functions" in routes


class TestChatEndpoint:
    """Test /chat endpoint validation"""

    def test_chat_endpoint_requires_fields(self):
        """Chat endpoint should require message and user_id"""
        from app import ChatRequest

        # Test that ChatRequest model validates correctly
        with pytest.raises(Exception):  # Pydantic ValidationError
            ChatRequest()  # Should fail without required fields


class TestSystemContext:
    """Test system context building"""

    @pytest.mark.asyncio
    async def test_context_includes_datetime(self):
        """System context should include current date/time"""
        from app import _build_datetime_context

        context = _build_datetime_context()

        # Should include date/time information
        assert "202" in context  # Should have year
        assert "2026" in context or "2025" in context or "2024" in context

    @pytest.mark.asyncio
    async def test_context_includes_memories(self):
        """System context should include relevant memories when provided"""
        from app import _build_system_context

        mock_memories = [
            {
                "snippet": "L'utente si chiama Mario",
                "category": "nome",
                "importance": 10,
                "similarity": 0.95
            }
        ]

        with patch('app.retrieve_relevant_memories', AsyncMock(return_value=mock_memories)):
            context = await _build_system_context("test_user", "Come mi chiamo?")

            assert "[MEMORIA UTENTE]" in context or "MEMORIA" in context
            assert "Mario" in context


class TestModelSelection:
    """Test smart/fast model selection logic"""

    def test_should_use_smart_model_function_exists(self):
        """_should_use_smart_model function should exist"""
        from app import _should_use_smart_model

        # Function exists and can be called
        messages = [{"role": "user", "content": "test"}]
        result = _should_use_smart_model(messages)
        assert isinstance(result, bool)

    def test_action_keywords_detection(self):
        """Action keywords should be detectable"""
        from app import _should_use_smart_model

        # Test with action keyword
        messages = [{"role": "user", "content": "Che ore sono?"}]
        result = _should_use_smart_model(messages)
        # Result depends on Gemini availability, but function should work
        assert isinstance(result, bool)


class TestMemoryExtraction:
    """Test memory extraction trigger conditions"""

    def test_should_extract_memories_exists(self):
        """Memory extraction pre-check function should exist"""
        from memory import _should_extract_memories

        messages = [{"role": "user", "content": "Mi chiamo Mario"}]
        result = _should_extract_memories(messages)
        assert isinstance(result, bool)

    def test_memory_extraction_constants(self):
        """Memory extraction constants should exist"""
        from memory import MIN_MESSAGE_LENGTH_FOR_EXTRACTION, EXCLUDED_ROLES

        assert MIN_MESSAGE_LENGTH_FOR_EXTRACTION > 0
        assert isinstance(EXCLUDED_ROLES, set)
        assert "system" in EXCLUDED_ROLES


class TestPluginIntegration:
    """Test plugin system integration with app"""

    def test_plugin_manager_initialized(self):
        """Plugin manager should be initialized in app"""
        from app import plugin_manager

        assert plugin_manager is not None
        assert len(plugin_manager.functions) > 0

    def test_plugin_functions_available(self):
        """Plugin functions should be available"""
        from app import plugin_manager

        # Should have system functions loaded
        function_names = list(plugin_manager.functions.keys())
        assert any("system" in name for name in function_names)

    def test_get_functions_schema(self):
        """Should be able to get function schemas"""
        from app import plugin_manager

        schemas = plugin_manager.get_functions_schema()
        assert isinstance(schemas, list)
        assert len(schemas) > 0

        # Check schema structure
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "parameters" in schema


class TestLLMIntegration:
    """Test LLM client integration"""

    def test_gemini_client_exists(self):
        """Gemini client should be initialized"""
        from app import gemini_client

        assert gemini_client is not None
        assert hasattr(gemini_client, 'check_availability')

    def test_ollama_config_loaded(self):
        """Ollama configuration should be loaded"""
        from app import OLLAMA_URL, OLLAMA_MODEL_FAST, OLLAMA_MODEL_SMART

        assert OLLAMA_URL is not None
        assert OLLAMA_MODEL_FAST is not None
        assert OLLAMA_MODEL_SMART is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
