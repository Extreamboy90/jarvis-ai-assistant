"""
Gemini API client for AI Assistant
Handles all interactions with Google Gemini API
"""

import os
import logging
import json
from typing import List, Dict, Optional
import google.generativeai as genai

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for Google Gemini API with function calling support"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini client

        Args:
            api_key: Google API key (or set GOOGLE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")

        if not self.api_key:
            logger.warning("No GOOGLE_API_KEY found, Gemini will not work")
            self.enabled = False
            return

        try:
            genai.configure(api_key=self.api_key)

            # Use Gemini 2.5 Flash (latest and fastest)
            self.model_fast = genai.GenerativeModel('gemini-2.5-flash')
            self.model_smart = genai.GenerativeModel('gemini-2.5-flash')

            self.enabled = True
            logger.info("Gemini client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.enabled = False

    def _convert_messages_to_gemini_format(self, messages: List[Dict]) -> List[Dict]:
        """
        Convert OpenAI-style messages to Gemini format

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            List of Gemini-compatible messages
        """
        gemini_messages = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Gemini uses 'user' and 'model' roles (not 'assistant')
            if role == "assistant":
                role = "model"
            elif role == "system":
                # System messages are prepended to first user message
                continue

            gemini_messages.append({
                "role": role,
                "parts": [{"text": content}]
            })

        return gemini_messages

    def _convert_functions_to_gemini_tools(self, functions: List[Dict]) -> List:
        """
        Convert function schema to Gemini tools format

        Args:
            functions: List of function schemas (OpenAI format)

        Returns:
            List of Gemini function declarations
        """
        if not functions:
            return []

        tools = []

        for func in functions:
            # Extract function info
            name = func.get("name", "")
            description = func.get("description", "")
            parameters = func.get("parameters", {})

            # Clean properties - remove unsupported fields like "default"
            properties = {}
            for prop_name, prop_value in parameters.get("properties", {}).items():
                cleaned_prop = {
                    "type": prop_value.get("type", "string"),
                    "description": prop_value.get("description", "")
                }
                # Remove empty descriptions
                if not cleaned_prop["description"]:
                    del cleaned_prop["description"]
                properties[prop_name] = cleaned_prop

            # Convert to Gemini format
            gemini_func = {
                "name": name,
                "description": description,
                "parameters": {
                    "type": parameters.get("type", "object"),
                    "properties": properties,
                    "required": parameters.get("required", [])
                }
            }

            tools.append(gemini_func)

        return tools

    def chat(
        self,
        messages: List[Dict],
        functions: List[Dict] = None,
        use_smart: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> Dict:
        """
        Send chat request to Gemini

        Args:
            messages: Conversation history
            functions: Available functions for calling
            use_smart: Use Pro model instead of Flash
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns:
            Response dict with 'message' and optional 'function_call'
        """
        if not self.enabled:
            raise Exception("Gemini client not initialized (missing API key)")

        try:
            # Select model
            model = self.model_smart if use_smart else self.model_fast
            model_name = "gemini-1.5-pro" if use_smart else "gemini-1.5-flash"
            logger.info(f"Using Gemini model: {model_name}")

            # Convert messages to Gemini format
            gemini_messages = self._convert_messages_to_gemini_format(messages)

            # Extract system prompt from messages if present
            system_prompt = None
            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                    break

            # Build prompt from messages
            if not gemini_messages:
                raise ValueError("No valid messages to send")

            # Combine all messages into a single prompt for now
            # (Gemini API prefers single turn for function calling)
            prompt_parts = []
            if system_prompt:
                prompt_parts.append(f"System: {system_prompt}\n")

            for msg in messages:
                if msg.get("role") != "system":
                    role = "User" if msg.get("role") == "user" else "Assistant"
                    prompt_parts.append(f"{role}: {msg.get('content', '')}")

            prompt = "\n".join(prompt_parts)

            # Configure generation
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            # Prepare tools if functions provided
            tools = None
            if functions:
                gemini_tools = self._convert_functions_to_gemini_tools(functions)
                if gemini_tools:
                    tools = [{"function_declarations": gemini_tools}]
                    logger.info(f"Configured {len(gemini_tools)} functions for Gemini")

            # Make API call
            if tools:
                response = model.generate_content(
                    prompt,
                    tools=tools,
                    generation_config=generation_config
                )
            else:
                response = model.generate_content(
                    prompt,
                    generation_config=generation_config
                )

            # Parse response
            result = {
                "message": "",
                "function_call": None
            }

            # Check for function calls
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]

                # Check if there's a function call
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts') and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, 'function_call') and part.function_call:
                                # Function call detected
                                fc = part.function_call
                                function_name = getattr(fc, 'name', '')
                                function_args = dict(getattr(fc, 'args', {})) if hasattr(fc, 'args') and fc.args else {}

                                logger.info(f"Function call detected: {function_name} with args: {function_args}")

                                if function_name:  # Only add if name is not empty
                                    result["function_call"] = {
                                        "function": function_name,
                                        "parameters": function_args
                                    }
                                else:
                                    logger.warning(f"Empty function name detected")
                            elif hasattr(part, 'text') and part.text:
                                result["message"] = part.text

            # If no function call, get text response
            if not result["function_call"] and not result["message"]:
                if hasattr(response, 'text') and response.text:
                    result["message"] = response.text

            return result

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise Exception(f"Gemini error: {str(e)}")

    def check_availability(self) -> bool:
        """Check if Gemini API is available"""
        return self.enabled
