import unittest
from openkpl.transform.draft import phase,boolish
class TestV02(unittest.TestCase):
    def test_phase(self):
        self.assertEqual(phase(1,18),"BAN_1"); self.assertEqual(phase(18,18),"PICK_2")
    def test_bool(self):
        self.assertTrue(boolish("TRUE")); self.assertFalse(boolish("FALSE"))
