"""
System plugin - Basic system operations
"""

from plugins import function
import subprocess
import datetime
import os

@function(
    name="get_current_time",
    description="Get the current date and time",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_current_time():
    """Get current date and time"""
    now = datetime.datetime.now()
    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "timestamp": now.timestamp()
    }

@function(
    name="execute_command",
    description="Execute a safe shell command (read-only operations only)",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command to execute"
            }
        },
        "required": ["command"]
    }
)
def execute_command(command: str):
    """Execute a safe shell command"""
    # Whitelist di comandi sicuri
    allowed_commands = ["ls", "pwd", "date", "uptime", "df", "free", "whoami"]

    cmd_parts = command.split()
    if not cmd_parts or cmd_parts[0] not in allowed_commands:
        return {
            "success": False,
            "error": f"Command not allowed. Allowed commands: {', '.join(allowed_commands)}"
        }

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@function(
    name="get_system_info",
    description="Get system information (CPU, memory, disk usage)",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_system_info():
    """Get system information using Python libraries"""
    try:
        import psutil

        # CPU info
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        # Memory info
        mem = psutil.virtual_memory()
        mem_total_gb = mem.total / (1024**3)
        mem_used_gb = mem.used / (1024**3)
        mem_percent = mem.percent

        # Disk info
        disk = psutil.disk_usage('/')
        disk_total_gb = disk.total / (1024**3)
        disk_used_gb = disk.used / (1024**3)
        disk_percent = disk.percent

        return {
            "success": True,
            "cpu": {
                "cores": cpu_count,
                "usage_percent": cpu_percent
            },
            "memory": {
                "total_gb": round(mem_total_gb, 2),
                "used_gb": round(mem_used_gb, 2),
                "percent": mem_percent
            },
            "disk": {
                "total_gb": round(disk_total_gb, 2),
                "used_gb": round(disk_used_gb, 2),
                "percent": disk_percent
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
