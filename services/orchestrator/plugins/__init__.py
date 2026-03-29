"""
Plugin system for AI Assistant
Each plugin exposes functions that can be called by the LLM
"""

from typing import Dict, List, Callable, Any
import importlib
import inspect
import logging

logger = logging.getLogger(__name__)

class PluginManager:
    def __init__(self):
        self.plugins: Dict[str, Any] = {}
        self.functions: Dict[str, Callable] = {}

    def load_plugin(self, plugin_name: str):
        """Load a plugin module"""
        try:
            module = importlib.import_module(f"plugins.{plugin_name}")
            self.plugins[plugin_name] = module

            # Registra tutte le funzioni del plugin che hanno il decorator @function
            for name, obj in inspect.getmembers(module):
                if hasattr(obj, '_is_plugin_function'):
                    function_name = f"{plugin_name}_{name}"
                    self.functions[function_name] = obj
                    logger.info(f"Registered function: {function_name}")

        except Exception as e:
            logger.error(f"Error loading plugin {plugin_name}: {e}")

    def get_functions_schema(self) -> List[Dict]:
        """Get OpenAI function calling schema for all registered functions"""
        schemas = []
        for name, func in self.functions.items():
            if hasattr(func, '_function_schema'):
                schema = func._function_schema.copy()
                schema['name'] = name
                schemas.append(schema)
        return schemas

    def call_function(self, function_name: str, **kwargs) -> Any:
        """Call a registered function"""
        if function_name not in self.functions:
            raise ValueError(f"Function {function_name} not found")

        return self.functions[function_name](**kwargs)


def function(name: str, description: str, parameters: Dict):
    """
    Decorator to mark a function as callable by the LLM

    Usage:
        @function(
            name="get_weather",
            description="Get current weather for a location",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        )
        def get_weather(location: str):
            return f"Weather in {location}: Sunny, 22°C"
    """
    def decorator(func):
        func._is_plugin_function = True
        func._function_schema = {
            "description": description,
            "parameters": parameters
        }
        return func
    return decorator
