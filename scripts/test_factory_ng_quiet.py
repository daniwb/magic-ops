import importlib.util
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {'work_schedule': {'enabled': True, 'timezone': 'Europe/Zurich',
                              'start': '22:00', 'end': '07:00'}}


def controller():
    spec = importlib.util.spec_from_file_location('quiet_controller', ROOT / 'scripts/factory-ng-controller.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class QuietTests(unittest.TestCase):
    def test_affinity_and_priority_are_inherited_by_children(self):
        cpu = max(os.sched_getaffinity(0))
        code = """
import os, subprocess, sys
from factory_ng_quiet import apply_resources
apply_resources({'resources': {'cpu_affinity': [%d], 'nice': 10}})
subprocess.run([sys.executable, '-c', 'import os; print(sorted(os.sched_getaffinity(0))); print(os.getpriority(os.PRIO_PROCESS, 0))'], check=True)
""" % cpu
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT / 'scripts',
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.splitlines(), [str([cpu]), '10'])


if __name__ == '__main__':
    unittest.main()
