from __future__ import annotations

from typing import Any, Dict, Tuple


# Unitree G1ArmActionClient.action_map, presented in a stable UI order.
PRESET_MOTIONS: Tuple[Dict[str, Any], ...] = (
    {"id": "high-wave", "name": "Wave", "action_id": 26, "icon": "👋"},
    {"id": "shake-hand", "name": "Shake hand", "action_id": 27, "icon": "🤝"},
    {"id": "high-five", "name": "High five", "action_id": 18, "icon": "✋"},
    {"id": "clap", "name": "Clap", "action_id": 17, "icon": "👏"},
    {"id": "hug", "name": "Hug", "action_id": 19, "icon": "🫂"},
    {"id": "heart", "name": "Heart", "action_id": 20, "icon": "🫶"},
    {"id": "right-heart", "name": "Right heart", "action_id": 21, "icon": "♡"},
    {"id": "face-wave", "name": "Face wave", "action_id": 25, "icon": "🙋"},
    {"id": "hands-up", "name": "Hands up", "action_id": 15, "icon": "🙌"},
    {"id": "right-hand-up", "name": "Right hand up", "action_id": 23, "icon": "☝"},
    {"id": "reject", "name": "Reject", "action_id": 22, "icon": "🙅"},
    {"id": "x-ray", "name": "X-ray", "action_id": 24, "icon": "🩻"},
    {"id": "left-kiss", "name": "Left kiss", "action_id": 12, "icon": "💋"},
    {"id": "right-kiss", "name": "Right kiss", "action_id": 13, "icon": "💋"},
    {"id": "two-hand-kiss", "name": "Two-hand kiss", "action_id": 11, "icon": "😘"},
    {"id": "release-arm", "name": "Release arms", "action_id": 99, "icon": "↔"},
)

MOTIONS_BY_ID = {motion["id"]: motion for motion in PRESET_MOTIONS}


def public_motions() -> list[Dict[str, Any]]:
    return [{"id": item["id"], "name": item["name"], "icon": item["icon"]} for item in PRESET_MOTIONS]
