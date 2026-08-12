"""Supervise browser subprocesses owned by the MCP server."""

from __future__ import annotations

import ctypes
import logging
import os
import signal
import subprocess
from collections.abc import Callable

from pydoll.browser.managers import BrowserProcessManager

logger = logging.getLogger(__name__)


class ManagedBrowserProcessManager(BrowserProcessManager):
    """Attach managed Chrome processes to an OS lifetime group when possible."""

    _process: subprocess.Popen[bytes] | None

    def __init__(self) -> None:
        self._job_handle: int | None = None
        self._process_creator: Callable[[list[str]], subprocess.Popen[bytes]] = self._create_process
        self._process = None
        logger.debug('Managed browser process manager initialized')

    def _create_process(self, command: list[str]) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != 'nt',
        )
        self._job_handle = _attach_to_kill_on_close_job(process.pid)
        return process

    def stop_process(self) -> None:
        try:
            process = self._process
            if process is not None:
                _signal_process_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    _signal_process_group(process, 9)
        finally:
            _close_handle(self._job_handle)
            self._job_handle = None


def _attach_to_kill_on_close_job(pid: int) -> int | None:
    if os.name != 'nt':
        return None
    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        if not _configure_job(kernel32, job):
            _close_handle(job)
            return None
        process = kernel32.OpenProcess(0x1F0FFF, False, pid)
        if not process or not kernel32.AssignProcessToJobObject(job, process):
            _close_handle(process)
            _close_handle(job)
            return None
        _close_handle(process)
        return int(job)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        logger.warning('Could not attach browser process to a Windows job: %s', exc)
        return None


def _configure_job(kernel32: ctypes.WinDLL, job: int) -> bool:
    class IoCounters(ctypes.Structure):
        _fields_ = [  # noqa: RUF012
            ('read_operations', ctypes.c_ulonglong),
            ('write_operations', ctypes.c_ulonglong),
            ('other_operations', ctypes.c_ulonglong),
            ('read_bytes', ctypes.c_ulonglong),
            ('write_bytes', ctypes.c_ulonglong),
            ('other_bytes', ctypes.c_ulonglong),
        ]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [  # noqa: RUF012
            ('per_process_user_time_limit', ctypes.c_longlong),
            ('per_job_user_time_limit', ctypes.c_longlong),
            ('limit_flags', ctypes.c_ulong),
            ('minimum_working_set_size', ctypes.c_size_t),
            ('maximum_working_set_size', ctypes.c_size_t),
            ('active_process_limit', ctypes.c_ulong),
            ('affinity', ctypes.c_size_t),
            ('priority_class', ctypes.c_ulong),
            ('scheduling_class', ctypes.c_ulong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [('basic_limit_information', BasicLimitInformation), ('io_info', IoCounters)]  # noqa: RUF012

    info = ExtendedLimitInformation()
    info.basic_limit_information.limit_flags = 0x00002000
    return bool(kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)))


def _close_handle(handle: int | None) -> None:
    if handle and os.name == 'nt':
        ctypes.WinDLL('kernel32', use_last_error=True).CloseHandle(handle)


def _signal_process_group(process: subprocess.Popen[bytes], sig: int) -> None:
    if os.name == 'nt':
        process.terminate() if sig == signal.SIGTERM else process.kill()
        return
    try:
        killpg: Callable[[int, int], None] | None = getattr(os, 'killpg', None)
        if killpg is None:
            process.send_signal(sig)
            return
        killpg(process.pid, sig)
    except ProcessLookupError:
        return
