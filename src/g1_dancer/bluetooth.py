from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Dict, List


MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
# Keep LF intact: bluetoothctl uses it to separate discovered devices.  The
# previous expression removed it along with terminal controls, merging an
# entire scan into one unreadable name in the web UI.
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x09\x0b-\x1f\x7f]")


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
    output = ANSI_RE.sub("", (result.stdout + result.stderr)).strip()
    if result.returncode != 0:
        raise BluetoothError(output or f"bluetoothctl {' '.join(arguments)} failed")
    return output


def _devices(command: str) -> List[Dict[str, str]]:
    result = []
    for line in ANSI_RE.sub("", _run(command)).splitlines():
        match = re.match(r"Device\s+((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s*(.*)$", line)
        if match:
            result.append({"address": match.group(1).upper(), "name": match.group(2).strip() or match.group(1)})
    return result


def _is_audio(info: str) -> bool:
    return "Icon: audio" in info or any(marker in info for marker in (
        "Audio Sink", "Audio Source", "Headset", "Handsfree", "A2DP",
    ))


def paired_devices() -> List[Dict[str, Any]]:
    """Paired audio devices with their current connection state."""
    devices = []
    # BlueZ 5.64 uses paired-devices, rather than the former devices Paired form.
    for device in _devices("paired-devices"):
        info = _run("info", device["address"])
        if _is_audio(info):
            devices.append({**device, "connected": "Connected: yes" in info, "audio": True})
    return devices


def connected_devices() -> List[Dict[str, Any]]:
    return [device for device in paired_devices() if device["connected"]]


def scan(seconds: int = 10) -> List[Dict[str, str]]:
    if seconds < 1 or seconds > 30:
        raise BluetoothError("Scan duration must be between 1 and 30 seconds")
    _run("power", "on")
    _run("--timeout", str(seconds), "scan", "on", timeout=seconds + 5)
    devices = []
    for device in _devices("devices"):
        # A device advertising an audio profile (for example JBL Go 4) is what
        # can actually be paired as this app's output. Hide trackers and other
        # nearby BLE devices from the audio picker.
        address_as_name = device["address"].replace(":", "-")
        # Some BLE advertisements have no usable friendly name and BlueZ shows
        # their address instead. They are not meaningful choices in an audio
        # picker, so wait until the speaker advertises a real name.
        if device["name"].upper() == address_as_name or device["name"] == device["address"]:
            continue
        if _is_audio(_run("info", device["address"])):
            devices.append(device)
    return devices


def _validate(mac: str) -> str:
    if not MAC_RE.fullmatch(mac):
        raise BluetoothError("Expected a Bluetooth MAC such as AA:BB:CC:DD:EE:FF")
    return mac.upper()


def _disconnect_other_audio(selected: str) -> None:
    for device in connected_devices():
        if device["address"] != selected:
            _run("disconnect", device["address"])


def pair(mac: str) -> Dict[str, Any]:
    mac = _validate(mac)
    _run("power", "on")
    _run("pairable", "on")
    _run("pair", mac, timeout=45)
    _run("trust", mac)
    return connect(mac)


def connect(mac: str) -> Dict[str, Any]:
    mac = _validate(mac)
    _disconnect_other_audio(mac)
    output = _run("connect", mac, timeout=30)
    if "Connection successful" not in output:
        raise BluetoothError(output or "Bluetooth device did not connect")
    return next((device for device in paired_devices() if device["address"] == mac), {
        "address": mac, "name": mac, "connected": True, "audio": True,
    })
