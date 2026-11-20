import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from live_test import assert_transform, choose_level, XFORM
from bridge_mcp import MCPError


class LiveGuardTests(unittest.TestCase):
    def test_transform_exact_values(self):
        assert_transform(XFORM)
        with self.assertRaises(MCPError): assert_transform({**XFORM,'location':{'x':0,'y':0,'z':0}})

    def test_existing_map_is_never_reused(self):
        existing={'/Game/CodexBridgeTests/ARC01_TestLevel','/Game/CodexBridgeTests/ARC01_TestLevel_001'}
        self.assertEqual(choose_level(lambda p:p in existing),'/Game/CodexBridgeTests/ARC01_TestLevel_002')

    def test_first_run_uses_preferred_map(self):
        self.assertEqual(choose_level(lambda p:False),'/Game/CodexBridgeTests/ARC01_TestLevel')


if __name__=='__main__': unittest.main()
