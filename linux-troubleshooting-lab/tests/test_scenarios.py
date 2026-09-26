import sys
import unittest
from linuxlab.lab.controller import LabController
from linuxlab.scenarios.registry import registry

class TestAllScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctrl = LabController()
        cls.ctrl.ensure_running()
        cls.ctrl.reset()

    def setUp(self):
        self.ctrl.reset()

    def tearDown(self):
        self.ctrl.reset()

    def test_cpu_scenario(self):
        s = registry.get("cpu_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)
        # Apply fix
        self.ctrl.exec_cmd("pkill -9 -f worker_loop")
        solved, msg, _ = s.verify(self.ctrl)
        self.assertTrue(solved, msg)

    def test_memory_scenario(self):
        s = registry.get("mem_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)
        # Apply fix
        self.ctrl.exec_cmd("pkill -9 -f mem_eater")
        solved, msg, _ = s.verify(self.ctrl)
        self.assertTrue(solved, msg)

    def test_disk_scenario(self):
        s = registry.get("disk_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)
        # Apply fix
        self.ctrl.exec_cmd("> /var/log/app/transaction.log")
        solved, msg, _ = s.verify(self.ctrl)
        self.assertTrue(solved, msg)

    def test_inodes_scenario(self):
        s = registry.get("inode_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)
        # Apply fix
        self.ctrl.exec_cmd("find /var/spool/app_cache -type f -delete")
        solved, msg, _ = s.verify(self.ctrl)
        self.assertTrue(solved, msg)

    def test_permissions_scenario(self):
        s = registry.get("perm_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)
        # Apply fix
        self.ctrl.exec_cmd("sudo chmod 644 /etc/app/web_app.conf && /usr/local/bin/systemctl restart web-app")
        solved, msg, _ = s.verify(self.ctrl)
        self.assertTrue(solved, msg)

    def test_services_scenario(self):
        s = registry.get("service_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)
        # Apply fix: restore clean json
        self.ctrl.exec_cmd('cat << "EOF" > /etc/app/web_app.conf\n{"port": 8080, "workers": 4, "debug": false}\nEOF')
        self.ctrl.exec_cmd("/usr/local/bin/systemctl restart web-app")
        solved, msg, _ = s.verify(self.ctrl)
        self.assertTrue(solved, msg)

    def test_networking_scenario(self):
        s = registry.get("net_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)
        # Apply fix: kill rogue listener and restart web-app
        self.ctrl.exec_cmd("pkill -9 -f rogue_listener")
        self.ctrl.exec_cmd("/usr/local/bin/systemctl restart web-app")
        solved, msg, _ = s.verify(self.ctrl)
        self.assertTrue(solved, msg)

    def test_logs_scenario(self):
        s = registry.get("log_001")
        self.assertIsNotNone(s)
        self.assertTrue(s.setup(self.ctrl))
        solved, _, _ = s.verify(self.ctrl)
        self.assertFalse(solved)
        # Apply fix: map db.internal to 127.0.0.1 in /etc/hosts
        self.ctrl.exec_cmd("sed 's/127.0.0.99/127.0.0.1/g' /etc/hosts | sudo tee /etc/hosts > /dev/null")
        solved, msg, _ = s.verify(self.ctrl)
        self.assertTrue(solved, msg)

if __name__ == "__main__":
    unittest.main()
