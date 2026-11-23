import ctypes as ct
from ctypes import wintypes as win
import os
from pathlib import Path
from threading import get_native_id
from tkinter import filedialog
from uuid import UUID


EVENT_OBJECT_SHOW = 0x8002
OBJID_WINDOW = 0
WINEVENT_OUTOFCONTEXT = 0
GA_ROOT = 2
GW_OWNER = 4
MONITOR_DEFAULTTONEAREST = 2
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
FOLDERID_DOCUMENTS = UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")
KF_FLAG_DONT_VERIFY = 0x4000

WinEventProc = ct.WINFUNCTYPE(None, win.HANDLE, win.DWORD, win.HWND, win.LONG,
                            win.LONG, win.DWORD, win.DWORD)


class MonitorInfo(ct.Structure):
    _fields_ = [("size", win.DWORD), ("bounds", win.RECT), ("work_area", win.RECT), ("flags", win.DWORD)]


def documents_folder():
    ole32 = ct.WinDLL("ole32")
    shell32 = ct.WinDLL("shell32")
    ole32.CoInitialize.argtypes = (ct.c_void_p,)
    ole32.CoTaskMemFree.argtypes = (ct.c_void_p,)
    shell32.SHGetKnownFolderPath.argtypes = (ct.c_void_p, win.DWORD, win.HANDLE, ct.POINTER(ct.c_void_p))
    initialized = ole32.CoInitialize(None) >= 0
    folder_id = ct.create_string_buffer(FOLDERID_DOCUMENTS.bytes_le)
    path = ct.c_void_p()
    try:
        if shell32.SHGetKnownFolderPath(folder_id, KF_FLAG_DONT_VERIFY, None, ct.byref(path)) == 0 and path.value:
            return Path(ct.wstring_at(path))
        return Path.home() / "Documents"
    finally:
        ole32.CoTaskMemFree(path)
        if initialized:
            ole32.CoUninitialize()


def open_audio_file(parent, title, filetypes):
    user32 = ct.WinDLL("user32")
    user32.GetAncestor.argtypes = (win.HWND, win.UINT)
    user32.GetAncestor.restype = win.HWND
    user32.GetWindow.argtypes = (win.HWND, win.UINT)
    user32.GetWindow.restype = win.HWND
    user32.GetWindowTextW.argtypes = (win.HWND, win.LPWSTR, ct.c_int)
    user32.MonitorFromWindow.argtypes = (win.HWND, win.DWORD)
    user32.MonitorFromWindow.restype = win.HMONITOR
    user32.GetMonitorInfoW.argtypes = (win.HMONITOR, ct.POINTER(MonitorInfo))
    user32.SetWindowPos.argtypes = (win.HWND, win.HWND, ct.c_int, ct.c_int, ct.c_int, ct.c_int, win.UINT)
    user32.SetWinEventHook.argtypes = (win.DWORD, win.DWORD, win.HMODULE, WinEventProc,
                                      win.DWORD, win.DWORD, win.DWORD)
    user32.SetWinEventHook.restype = win.HANDLE
    user32.UnhookWinEvent.argtypes = (win.HANDLE,)

    owner = user32.GetAncestor(parent.winfo_id(), GA_ROOT)
    dialog_title = ct.create_unicode_buffer(len(title) + 2)
    resized = False

    @WinEventProc
    def resize_dialog(_hook, _event, hwnd, object_id, child_id, _thread, _time):
        nonlocal resized
        if resized or not hwnd or object_id != OBJID_WINDOW or child_id != 0:
            return
        if user32.GetWindow(hwnd, GW_OWNER) != owner:
            return
        user32.GetWindowTextW(hwnd, dialog_title, len(dialog_title))
        if dialog_title.value != title:
            return

        monitor = user32.MonitorFromWindow(owner, MONITOR_DEFAULTTONEAREST)
        info = MonitorInfo(size=ct.sizeof(MonitorInfo))
        if user32.GetMonitorInfoW(monitor, ct.byref(info)):
            work = info.work_area
            resized = True
            user32.SetWindowPos(hwnd, None, work.left, work.top, work.right - work.left,
                                work.bottom - work.top, SWP_NOZORDER | SWP_NOACTIVATE)

    # Tk runs a native modal message loop while the Explorer dialog is open.
    hook = user32.SetWinEventHook(EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, None, resize_dialog,
                                 os.getpid(), get_native_id(), WINEVENT_OUTOFCONTEXT)
    try:
        return filedialog.askopenfilename(parent=parent, title=title, filetypes=filetypes)
    finally:
        if hook:
            user32.UnhookWinEvent(hook)
