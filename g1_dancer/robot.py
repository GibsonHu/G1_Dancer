from __future__ import annotations

import threading
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

    def stop(self) -> None:
        if self.dry_run:
            self.log.append({"type": "stop"})
            return
        self.initialize()
        result = self._loco.StopMove()
        if result not in (None, 0):
            raise RobotError(f"Robot rejected StopMove (SDK code {result})")
