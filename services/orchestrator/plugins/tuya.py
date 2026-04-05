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


@function(
    name="get_home_status_summary",
    description="Get a summary of smart home status (lights, temperature, energy) for dashboard",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_home_status_summary():
    """
    Get smart home status summary for Mission Control dashboard.
    Returns aggregated info about lights, temperature, and devices.
    """
    try:
        # Get all devices
        devices_result = get_devices()

        if not devices_result.get("success"):
            return {
                "success": False,
                "error": devices_result.get("error", "Failed to get devices")
            }

        devices = devices_result.get("devices", [])

        if not devices:
            return {
                "success": True,
                "total_devices": 0,
                "lights_on": 0,
                "lights_off": 0,
                "temperature": None,
                "energy_consumption": 0,
                "summary": "Nessun dispositivo smart home configurato"
            }

        # Analyze devices
        lights_on = 0
        lights_off = 0
        temperature = None
        energy_total = 0
        device_list = []

        for device in devices:
            device_id = device.get("id")
            device_name = device.get("name", "Unknown")
            device_type = device.get("type", "").lower()

            # Get device status
            status_result = get_device_status(device_id)

            if status_result.get("success"):
                status = status_result.get("status", {})

                # Count lights
                if "light" in device_type or "switch" in device_type:
                    is_on = status.get("power", False) or status.get("state", "off") == "on"
                    if is_on:
                        lights_on += 1
                    else:
                        lights_off += 1

                    device_list.append({
                        "name": device_name,
                        "type": "light",
                        "status": "on" if is_on else "off"
                    })

                # Get temperature (from thermostat or sensor)
                if "temp" in device_type or "thermostat" in device_type or "climate" in device_type:
                    temp_value = status.get("temperature") or status.get("current_temperature")
                    if temp_value:
                        temperature = round(float(temp_value), 1)

                        device_list.append({
                            "name": device_name,
                            "type": "temperature",
                            "value": temperature
                        })

                # Get energy consumption
                power = status.get("power_consumption") or status.get("current_power") or status.get("power_w")
                if power:
                    try:
                        energy_total += float(power)
                    except:
                        pass

        # Generate summary text
        summary_parts = []

        if lights_on > 0:
            summary_parts.append(f"{lights_on} luci accese")
        else:
            summary_parts.append("Tutte le luci spente")

        if temperature:
            summary_parts.append(f"temperatura {temperature}°C")

        if energy_total > 0:
            summary_parts.append(f"consumo {round(energy_total)}W")

        summary = ", ".join(summary_parts) if summary_parts else "Nessun dispositivo attivo"

        return {
            "success": True,
            "total_devices": len(devices),
            "lights_on": lights_on,
            "lights_off": lights_off,
            "temperature": temperature,
            "energy_consumption": round(energy_total, 1),
            "devices": device_list[:10],  # Max 10 devices in summary
            "summary": summary
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error getting home status: {str(e)}"
        }
