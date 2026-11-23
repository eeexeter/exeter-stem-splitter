import ctypes
from ctypes import wintypes
import subprocess


class BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("process_time_limit", ctypes.c_int64),
        ("job_time_limit", ctypes.c_int64),
        ("limit_flags", wintypes.DWORD),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limits", BasicLimitInformation),
        ("io_counters", ctypes.c_uint64 * 6),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
kernel.CreateJobObjectW.restype = wintypes.HANDLE
kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
kernel.SetInformationJobObject.restype = wintypes.BOOL
kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
kernel.AssignProcessToJobObject.restype = wintypes.BOOL
kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel.CloseHandle.restype = wintypes.BOOL

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001


class WorkerJob:
    def __init__(self):
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimitInformation()
        limits.basic_limits.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                              ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, pid):
        process = kernel.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(process)

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None


def start_worker(command):
    job = WorkerJob()
    process = None
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
        )
        with process.stdin:
            # The worker blocks here until Windows will also track any children it launches.
            job.assign(process.pid)
            process.stdin.write("start\n")
    except OSError:
        job.close()
        if process is not None:
            process.wait()
            process.stdout.close()
        raise
    return process, job
