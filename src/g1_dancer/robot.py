from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional


class RobotError(RuntimeError):
    pass


class G1Robot:
    """Small, lazy-loaded adapter around Unitree's official SDK."""

    def __init__(self, network_interface: str, dry_run: bool = False):
        self.network_interface = network_interface
        self.dry_run = dry_run
        self._initialized = False
        self._loco: Any = None
        self._arm: Any = None
        self._lock = threading.Lock()
        self.log: List[Dict[str, Any]] = []

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            if self.dry_run:
                self._initialized = True
                return
            try:
                from unitree_sdk2py.core.channel import ChannelFactoryInitialize
                from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient
                from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
            except ImportError as exc:
                raise RobotError(
                    "unitree_sdk2py is not installed. Install it while online, or use --dry-run."
                ) from exc
            ChannelFactoryInitialize(0, self.network_interface)
            self._loco = LocoClient()
            self._loco.SetTimeout(10.0)
            self._loco.Init()
            self._arm = G1ArmActionClient()
            self._arm.SetTimeout(10.0)
            self._arm.Init()
            self._initialized = True

    @property
    def is_initialized(self) -> bool:
        with self._lock:
            return self._initialized

    def execute(self, step: Dict[str, Any]) -> None:
        self.initialize()
        if self.dry_run:
            self.log.append(dict(step))
            return
        if step["type"] == "arm_action":
            result = self._arm.ExecuteAction(step["action_id"])
        else:
            result = getattr(self._loco, step["method"])(*step.get("args", []))
        if result not in (None, 0):
            raise RobotError(f"Robot rejected {step['type']} step (SDK code {result})")

    def get_mimic_motions(self) -> Dict[str, Any]:
        if self.dry_run:
            raise RobotError("Cannot discover robot motions in dry-run mode")
        self.initialize()
        code, data = self._loco.GetMimicMotion()
        if code != 0 or not isinstance(data, dict):
            raise RobotError(f"Could not read mimic motions from robot (SDK code {code})")
        return data

    def get_unistore_apps(self) -> Dict[str, Any]:
        """Read installed apps; API 1001 was verified against the official app."""
        if self.dry_run:
            raise RobotError("UniStore discovery is unavailable in dry-run mode")
        self.initialize()
        from unitree_sdk2py.rpc.client import Client
        client = Client("action_store")
        client.SetTimeout(4.0)
        client._RegistApi(1001, 0)
        code, data = client._Call(1001, "{}")
        if code != 0:
            raise RobotError(f"UniStore discovery failed (SDK code {code})")
        try:
            value = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise RobotError("Invalid UniStore response") from exc
        if not isinstance(value, dict) or value.get("code") != 0:
            raise RobotError("UniStore rejected the installed-app query")
        return value

    def run_unistore_action(self, instance_id: str, action_id: str = "1") -> Dict[str, Any]:
        """Start an installed UniStore app action.

        API 1005 and the ``instance_id``/``action_id`` payload were captured
        from the official Unitree app while it started Fun Robot Twist. This
        deliberately has no companion stop method: no non-Damp stop protocol
        has been verified for UniStore apps.
        """
        if not isinstance(instance_id, str) or not instance_id:
            raise RobotError("Invalid UniStore app instance")
        self.initialize()
        if self.dry_run:
            self.log.append({"type": "unistore_run", "instance_id": instance_id, "action_id": action_id})
            return {"status": "accepted"}
        from unitree_sdk2py.rpc.client import Client
        client = Client("action_store")
        client.SetTimeout(4.0)
        client._RegistApi(1005, 0)
        code, data = client._Call(1005, json.dumps({"instance_id": instance_id, "action_id": action_id}))
        if code != 0:
            raise RobotError(f"UniStore start failed (SDK code {code})")
        try:
            value = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise RobotError("Invalid UniStore start response") from exc
        if value.get("code") != 0 or value.get("status") != "success":
            raise RobotError(value.get("message", "UniStore rejected the start command"))
        return value

    def execute_mimic_motion(self, motion_id: int) -> None:
        self.initialize()
        fsm_id = 550000 + motion_id
        if self.dry_run:
            self.log.append({"type": "mimic_motion", "motion_id": motion_id, "fsm_id": fsm_id})
            return
        result = self._loco.RunMimicMotion(motion_id)
        if result not in (None, 0):
            raise RobotError(f"Robot rejected mimic motion {motion_id} (SDK code {result})")

    def run_mode(self) -> None:
        """Enable Unitree's internal Walk/Run controller, then enter FSM 500."""
        self.initialize()
        if self.dry_run:
            self.log.append({"type": "run_mode", "internal_control": 2, "fsm_id": 500})
            return
        result = self._loco.SwitchToInternalCtrl(2)  # InternalFsmMode.WALKRUN
        if result not in (None, 0):
            raise RobotError(f"Robot rejected Run Mode controller switch (SDK code {result})")
        result = self._loco.SetFsmId(500)
        if result not in (None, 0):
            raise RobotError(f"Robot rejected Run Mode command (SDK code {result})")
        for _ in range(10):
            code, fsm_id = self._loco.GetFsmId()
            if code != 0:
                raise RobotError(f"Could not verify robot state (SDK code {code})")
            if fsm_id in {500, 501, 801}:
                return
            time.sleep(0.2)
        raise RobotError(
            f"Robot stayed in FSM {fsm_id}; put it in a stable standing state, release any other "
            "motion-control client, and enable Run Mode in the Unitree controller"
        )

    def walk_run(self) -> None:
        """Compatibility alias for Run Mode."""
        self.run_mode()

    def ready_mode(self) -> None:
        """Enter Unitree G1 Lock Stand (FSM 4), holding a ready standing pose."""
        self.initialize()
        if self.dry_run:
            self.log.append({"type": "ready_mode", "fsm_id": 4})
            return
        result = self._loco.SetFsmId(4)
        if result not in (None, 0):
            raise RobotError(f"Robot rejected Ready Mode / Lock Stand command (SDK code {result})")
        code, fsm_id = self._loco.GetFsmId()
        if code != 0 or fsm_id != 4:
            raise RobotError(f"Robot did not enter Lock Stand (FSM {fsm_id}, SDK code {code})")

    def damped_mode(self) -> None:
        """Enter Unitree Damped Mode (FSM 1)."""
        self.initialize()
        if self.dry_run:
            self.log.append({"type": "damped_mode", "fsm_id": 1})
            return
        result = self._loco.SetFsmId(1)
        if result not in (None, 0):
            raise RobotError(f"Robot rejected Damped Mode command (SDK code {result})")

    def emergency_stop(self) -> None:
        """Compatibility alias for the Damped Mode SDK command."""
        self.damped_mode()

    def stop(self, *, exit_mimic: bool = False) -> None:
        if self.dry_run:
            self.log.append({
                "type": "stop_mimic_motion" if exit_mimic else "stop_custom_action",
                "fsm_id": 500 if exit_mimic else None,
            })
            return
        self.initialize()
        if exit_mimic:
            result = self._loco.StopMimicMotion()
            if result not in (None, 0):
                raise RobotError(f"Robot rejected StopMimicMotion (SDK code {result})")
        else:
            # StopCustomAction is documented for recorded actions. Preset arm
            # actions use action 99 to release a held pose, so issue both and
            # still stop walking velocity below. Unsupported/no-op responses
            # must not prevent the remaining non-Damp stop requests.
            self._arm.StopCustomAction()
            self._arm.ExecuteAction(99)
        result = self._loco.StopMove()
        if result not in (None, 0):
            raise RobotError(f"Robot rejected StopMove (SDK code {result})")
