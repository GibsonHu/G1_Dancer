import unittest

from unitree_sdk2py.g1.arm.g1_arm_action_api import (
    ROBOT_API_ID_ARM_ACTION_STOP_CUSTOM_ACTION,
)
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient


class SdkStopTests(unittest.TestCase):
    def test_stop_custom_action_uses_official_api_id(self):
        client = object.__new__(G1ArmActionClient)
        calls = []
        client._Call = lambda api_id, parameter: (calls.append((api_id, parameter)) or (0, None))
        self.assertEqual(client.StopCustomAction(), 0)
        self.assertEqual(calls, [(ROBOT_API_ID_ARM_ACTION_STOP_CUSTOM_ACTION, "{}")])

    def test_stop_mimic_motion_returns_to_walk_run_fsm(self):
        client = object.__new__(LocoClient)
        calls = []
        client.SetFsmId = lambda fsm_id: (calls.append(fsm_id) or 0)
        self.assertEqual(client.StopMimicMotion(), 0)
        self.assertEqual(calls, [500])


if __name__ == "__main__":
    unittest.main()
