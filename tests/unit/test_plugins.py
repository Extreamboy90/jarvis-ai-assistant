"""
Unit tests for plugin system
"""
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Import plugin system
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/orchestrator'))


class TestPluginDecorator:
    """Test @function decorator"""

    def test_function_decorator_adds_attributes(self):
        """@function decorator should add _is_plugin_function and _function_schema attributes"""
        from plugins import function

        @function(
            name="test_function",
            description="Test function",
            parameters={"type": "object", "properties": {}}
        )
        def test_func():
            return "success"

        # Should have decorator attributes
        assert hasattr(test_func, '_is_plugin_function')
        assert test_func._is_plugin_function is True
        assert hasattr(test_func, '_function_schema')
        assert test_func._function_schema['description'] == "Test function"

    def test_function_decorator_preserves_original_function(self):
        """@function decorator should preserve original function behavior"""
        from plugins import function

        @function(name="add", description="Add numbers", parameters={})
        def add(a, b):
            return a + b

        result = add(2, 3)
        assert result == 5


class TestPluginManager:
    """Test PluginManager class"""

    def test_plugin_manager_initialization(self):
        """PluginManager should initialize with empty plugins and functions"""
        from plugins import PluginManager

        manager = PluginManager()
        assert manager.plugins == {}
        assert manager.functions == {}

    def test_load_plugin_registers_functions(self):
        """Loading a plugin should register its functions"""
        from plugins import PluginManager

        manager = PluginManager()
        manager.load_plugin("system")

        # Should have registered system functions
        assert len(manager.functions) > 0
        assert "system_get_current_time" in manager.functions

    def test_get_functions_schema_returns_schemas(self):
        """get_functions_schema should return function schemas"""
        from plugins import PluginManager

        manager = PluginManager()
        manager.load_plugin("system")

        schemas = manager.get_functions_schema()
        assert isinstance(schemas, list)
        assert len(schemas) > 0

        # Check schema structure
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "parameters" in schema

    def test_call_function_executes_function(self):
        """call_function should execute registered function"""
        from plugins import PluginManager

        manager = PluginManager()
        manager.load_plugin("system")

        result = manager.call_function("system_get_current_time")

        assert result is not None
        assert "time" in result
        assert "date" in result

    def test_call_nonexistent_function_raises_error(self):
        """Calling non-existent function should raise ValueError"""
        from plugins import PluginManager

        manager = PluginManager()

        with pytest.raises(ValueError, match="not found"):
            manager.call_function("nonexistent_function")


class TestSystemPlugin:
    """Test system plugin functions"""

    def test_get_current_time_returns_valid_format(self):
        """system_get_current_time should return formatted time"""
        from plugins.system import get_current_time

        result = get_current_time()

        assert "time" in result
        assert "date" in result
        assert "day_of_week" in result
        assert "timestamp" in result
        assert ":" in result["time"]
        assert "-" in result["date"]

    def test_get_system_info_returns_structure(self):
        """system_get_system_info should return system metrics"""
        # Import psutil first to check if it's available
        try:
            import psutil
            psutil_available = True
        except ImportError:
            psutil_available = False

        if not psutil_available:
            pytest.skip("psutil not available")

        from plugins.system import get_system_info
        result = get_system_info()

        assert "cpu" in result
        assert "memory" in result
        assert "disk" in result

    def test_execute_command_allows_safe_commands(self):
        """execute_command should allow whitelisted commands"""
        from plugins.system import execute_command

        result = execute_command("pwd")

        assert "success" in result
        assert result["success"] is True
        assert "stdout" in result

    def test_execute_command_blocks_unsafe_commands(self):
        """execute_command should block non-whitelisted commands"""
        from plugins.system import execute_command

        result = execute_command("rm -rf /")

        assert "success" in result
        assert result["success"] is False
        assert "error" in result


class TestWebSearchPlugin:
    """Test web search plugin"""

    def test_search_web_requires_query(self):
        """search_web should require query parameter"""
        from plugins.web_search import search_web

        result = search_web(query="")

        # Should return error or empty results for empty query
        assert result is not None
        if "error" in result:
            assert result["success"] is False

    def test_search_web_returns_structure(self):
        """search_web should return proper structure"""
        from plugins.web_search import search_web

        # Test with actual call (will use fallback methods if APIs unavailable)
        result = search_web(query="test")

        # Should always return a dict with success field
        assert isinstance(result, dict)
        assert "success" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
