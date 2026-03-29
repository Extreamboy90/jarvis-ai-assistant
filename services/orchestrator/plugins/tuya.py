"""
Tuya plugin - Control Tuya smart devices
"""

from plugins import function
import requests
import os

# URL del servizio Tuya API
TUYA_API_URL = os.getenv("TUYA_API_URL", "http://tuya-api:5000")

@function(
    name="get_devices",
    description="Get list of all Tuya smart devices",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_devices():
    """Get list of all Tuya devices"""
    try:
        response = requests.get(f"{TUYA_API_URL}/devices", timeout=5)
        response.raise_for_status()
        return {
            "success": True,
            "devices": response.json()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@function(
    name="get_device_status",
    description="Get status of a specific Tuya device",
    parameters={
        "type": "object",
        "properties": {
            "device_id": {
                "type": "string",
                "description": "The ID of the device"
            }
        },
        "required": ["device_id"]
    }
)
def get_device_status(device_id: str):
    """Get status of a specific device"""
    try:
        response = requests.get(f"{TUYA_API_URL}/device/{device_id}/status", timeout=5)
        response.raise_for_status()
        return {
            "success": True,
            "status": response.json()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@function(
    name="control_device",
    description="Control a Tuya device (turn on/off, set brightness, etc.)",
    parameters={
        "type": "object",
        "properties": {
            "device_id": {
                "type": "string",
                "description": "The ID of the device"
            },
            "command": {
                "type": "string",
                "description": "The command to send (e.g., 'turn_on', 'turn_off', 'set_brightness')"
            },
            "value": {
                "type": "string",
                "description": "Optional value for the command (e.g., brightness level)"
            }
        },
        "required": ["device_id", "command"]
    }
)
def control_device(device_id: str, command: str, value: str = None):
    """Control a Tuya device"""
    try:
        payload = {
            "command": command
        }
        if value is not None:
            payload["value"] = value

        response = requests.post(
            f"{TUYA_API_URL}/device/{device_id}/control",
            json=payload,
            timeout=5
        )
        response.raise_for_status()
        return {
            "success": True,
            "result": response.json()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@function(
    name="turn_on_light",
    description="Turn on a light or switch",
    parameters={
        "type": "object",
        "properties": {
            "device_name": {
                "type": "string",
                "description": "Name or ID of the light/switch to turn on"
            }
        },
        "required": ["device_name"]
    }
)
def turn_on_light(device_name: str):
    """Turn on a light"""
    return control_device(device_name, "turn_on")

@function(
    name="turn_off_light",
    description="Turn off a light or switch",
    parameters={
        "type": "object",
        "properties": {
            "device_name": {
                "type": "string",
                "description": "Name or ID of the light/switch to turn off"
            }
        },
        "required": ["device_name"]
    }
)
def turn_off_light(device_name: str):
    """Turn off a light"""
    return control_device(device_name, "turn_off")
