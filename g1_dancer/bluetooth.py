from __future__ import annotations

import re
import shutil
import subprocess
from typing import List


MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class BluetoothError(RuntimeError):
    pass


def _require_bluetoothctl() -> None:
    if not shutil.which("bluetoothctl"):
        raise BluetoothError("bluetoothctl is not installed (install the BlueZ package)")


def _run(*arguments: str, timeout: float = 20) -> str:
    _require_bluetoothctl()
    result = subprocess.run(
        ["bluetoothctl", *arguments], capture_output=True, text=True, timeout=timeout
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise BluetoothError(output or f"bluetoothctl {' '.join(arguments)} failed")
    return output


def paired_devices() -> List[str]:
    return [line.strip() for line in _run("devices", "Paired").splitlines() if line.strip()]


def connected_devices() -> List[str]:
    devices = []
    for line in paired_devices():
        parts = line.split(maxsplit=2)
        if len(parts) >= 2 and "Connected: yes" in _run("info", parts[1]):
            devices.append(line)
    return devices


def scan(seconds: int = 10) -> str:
    if seconds < 1 or seconds > 60:
        raise BluetoothError("Scan duration must be between 1 and 60 seconds")
    return _run("--timeout", str(seconds), "scan", "on", timeout=seconds + 5)


def pair(mac: str) -> str:
    if not MAC_RE.fullmatch(mac):
        raise BluetoothError("Expected a Bluetooth MAC such as AA:BB:CC:DD:EE:FF")
    mac = mac.upper()
    _run("power", "on")
    _run("agent", "on")
    _run("default-agent")
    pairing = _run("pair", mac, timeout=45)
    _run("trust", mac)
    connection = _run("connect", mac)
    return pairing + "\n" + connection


def connect(mac: str) -> str:
    if not MAC_RE.fullmatch(mac):
        raise BluetoothError("Invalid Bluetooth MAC")
    return _run("connect", mac.upper())
