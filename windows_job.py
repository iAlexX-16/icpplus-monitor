"""Windows-owned process groups that cannot outlive their controlling application."""

import ctypes
from ctypes import wintypes
import os
import subprocess


if os.name == 'nt':
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    SIZE_T = ctypes.c_size_t

    class BasicLimits(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', wintypes.DWORD), ('minimum_working_set', SIZE_T),
                    ('maximum_working_set', SIZE_T), ('active_processes', wintypes.DWORD),
                    ('affinity', SIZE_T), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ('read_operations', 'write_operations', 'other_operations', 'read_bytes', 'write_bytes', 'other_bytes')]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('basic', BasicLimits), ('io', IoCounters), ('process_memory', SIZE_T),
                    ('job_memory', SIZE_T), ('peak_process_memory', SIZE_T), ('peak_job_memory', SIZE_T)]

    class StartupInfo(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('reserved', wintypes.LPWSTR), ('desktop', wintypes.LPWSTR),
                    ('title', wintypes.LPWSTR), ('x', wintypes.DWORD), ('y', wintypes.DWORD),
                    ('xsize', wintypes.DWORD), ('ysize', wintypes.DWORD), ('xchars', wintypes.DWORD),
                    ('ychars', wintypes.DWORD), ('fill', wintypes.DWORD), ('flags', wintypes.DWORD),
                    ('show', wintypes.WORD), ('reserved_size', wintypes.WORD), ('reserved_bytes', ctypes.c_void_p),
                    ('stdin', wintypes.HANDLE), ('stdout', wintypes.HANDLE), ('stderr', wintypes.HANDLE)]

    class ProcessInfo(ctypes.Structure):
        _fields_ = [('process', wintypes.HANDLE), ('thread', wintypes.HANDLE),
                    ('pid', wintypes.DWORD), ('tid', wintypes.DWORD)]

    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                     wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                                     ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL


class WindowsJob:
    def __init__(self, arguments, cwd, hidden_console=False):
        if os.name != 'nt':
            raise OSError('This process supervisor requires Windows.')
        self.job = self.process = None
        self.pid = None
        self.exit_code = None
        info = ProcessInfo()
        try:
            self.job = kernel.CreateJobObjectW(None, None)
            if not self.job:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            startup = StartupInfo()
            startup.cb = ctypes.sizeof(startup)
            startup.flags = 1  # STARTF_USESHOWWINDOW
            startup.show = 0  # SW_HIDE (only the helper console)
            flags = 0x4 | (0x10 if hidden_console else 0x08000000)  # suspended, with hidden/new or no console
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(item) for item in arguments]))
            if not kernel.CreateProcessW(str(arguments[0]), command, None, None, False, flags, None,
                                         str(cwd), ctypes.byref(startup), ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.process, self.pid = info.process, info.pid
            # Associate while suspended so no child can escape before ownership is established.
            if not kernel.AssignProcessToJobObject(self.job, self.process):
                raise ctypes.WinError(ctypes.get_last_error())
            if kernel.ResumeThread(info.thread) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception:
            if info.process:
                kernel.TerminateProcess(info.process, 1)
            self.close()
            raise
        finally:
            if info.thread:
                kernel.CloseHandle(info.thread)

    def poll(self):
        if not self.process:
            return self.exit_code
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(self.process, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if code.value == 259:  # STILL_ACTIVE
            return None
        self.exit_code = code.value
        return self.exit_code

    def close(self):
        if self.job:
            kernel.TerminateJobObject(self.job, 1)
            if self.process:
                kernel.WaitForSingleObject(self.process, 2000)
            kernel.CloseHandle(self.job)
            self.job = None
        if self.process:
            code = wintypes.DWORD()
            if kernel.GetExitCodeProcess(self.process, ctypes.byref(code)):
                self.exit_code = code.value
            kernel.CloseHandle(self.process)
            self.process = None


class SingleInstance:
    def __init__(self, name):
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        ctypes.set_last_error(0)
        self.handle = kernel.CreateMutexW(None, False, name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.already_running = ctypes.get_last_error() == 183

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None
