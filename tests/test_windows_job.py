import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from windows_job import WindowsJob


@unittest.skipUnless(os.name == 'nt', 'Windows process ownership test')
class WindowsJobTests(unittest.TestCase):
    def setUp(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]

    def handle_for(self, pid):
        handle = self.kernel.OpenProcess(0x00100000 | 0x1000 | 1, False, pid)
        self.assertTrue(handle)
        return handle

    def is_active(self, handle):
        code = wintypes.DWORD()
        self.assertTrue(self.kernel.GetExitCodeProcess(handle, ctypes.byref(code)))
        return code.value == 259

    def cleanup_handle(self, handle):
        if handle:
            if self.is_active(handle):
                self.kernel.TerminateProcess(handle, 1)
                self.kernel.WaitForSingleObject(handle, 2000)
            self.kernel.CloseHandle(handle)

    def wait_for_file(self, path):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if path.exists():
                return json.loads(path.read_text())
            time.sleep(0.025)
        self.fail('The controlled helper did not start.')

    def test_close_terminates_owned_process_and_grandchild(self):
        directory = Path(__file__).resolve().parents[1] / '.cache/tmp'
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            marker = Path(temporary) / 'children.json'
            code = ("import subprocess,sys,time,json;from pathlib import Path;"
                    "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],creationflags=0x08000000);"
                    f"Path({str(marker)!r}).write_text(json.dumps({{'pid':child.pid}}));time.sleep(120)")
            job = WindowsJob([sys.executable, '-c', code], directory)
            child_handle = None
            try:
                child = self.wait_for_file(marker)
                child_handle = self.handle_for(child['pid'])
                self.assertIsNone(job.poll())
                self.assertTrue(self.is_active(child_handle))
                job.close()
                self.kernel.WaitForSingleObject(child_handle, 2000)
                self.assertFalse(self.is_active(child_handle))
                self.assertIsNotNone(job.poll())
            finally:
                job.close()
                self.cleanup_handle(child_handle)

    def test_owner_crash_also_terminates_its_check(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / '.cache/tmp'
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            marker = Path(temporary) / 'owned.json'
            code = ("import sys,time,json;from pathlib import Path;from windows_job import WindowsJob;"
                    f"job=WindowsJob([sys.executable,'-c','import time;time.sleep(120)'],{str(root)!r});"
                    f"Path({str(marker)!r}).write_text(json.dumps({{'pid':job.pid}}));time.sleep(120)")
            owner = subprocess.Popen([sys.executable, '-c', code], cwd=root, creationflags=0x08000000)
            child_handle = None
            try:
                child = self.wait_for_file(marker)
                child_handle = self.handle_for(child['pid'])
                owner.terminate()
                owner.wait(timeout=3)
                self.kernel.WaitForSingleObject(child_handle, 2000)
                self.assertFalse(self.is_active(child_handle))
            finally:
                if owner.poll() is None:
                    owner.terminate()
                    owner.wait(timeout=3)
                self.cleanup_handle(child_handle)
