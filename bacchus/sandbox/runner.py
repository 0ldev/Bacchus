"""
Sandbox execution for risky tool calls.

Provides OS-level isolation for commands and file operations.
Backend selection is automatic at runtime:
  - Windows: AppContainer (via ctypes Win32 API), fallback to restricted subprocess
  - Linux/Mac: bwrap (Bubblewrap), fallback to restricted subprocess
"""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class SandboxRunner:
    """Executes commands in an OS-level sandbox."""

    def __init__(self, sandbox_dir: Path):
        self.sandbox_dir = Path(sandbox_dir)
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def bwrap_available() -> bool:
        """Check if Bubblewrap is available (Linux/Mac)."""
        try:
            subprocess.run(
                ["bwrap", "--version"],
                capture_output=True, timeout=2, check=True
            )
            return True
        except Exception:
            return False

    def run_command(self, command: str, timeout: int = 30) -> tuple[bool, str]:
        """Run a shell command in a sandbox. Returns (success, output)."""
        if os.name == "nt":
            return self._run_appcontainer(command, timeout)
        elif self.bwrap_available():
            return self._run_bwrap(command, timeout)
        return self._run_restricted(command, timeout)

    def sandbox_path(self, original_path: str) -> str:
        """Redirect an absolute path into the sandbox directory tree."""
        p = Path(original_path)
        parts = p.parts[1:] if p.is_absolute() else p.parts
        sandboxed = self.sandbox_dir.joinpath(*parts) if parts else self.sandbox_dir / p.name
        sandboxed.parent.mkdir(parents=True, exist_ok=True)
        return str(sandboxed)

    def _run_bwrap(self, command: str, timeout: int) -> tuple[bool, str]:
        """Linux: Bubblewrap (bwrap) namespaced sandbox."""
        bwrap_cmd = [
            "bwrap",
            "--unshare-all",
            "--share-net",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/lib", "/lib",
            "--dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", "/tmp",
            "--bind", str(self.sandbox_dir), "/workspace",
            "--chdir", "/workspace",
            "--", "sh", "-c", command
        ]
        if Path("/lib64").exists():
            bwrap_cmd = bwrap_cmd[:14] + ["--ro-bind", "/lib64", "/lib64"] + bwrap_cmd[14:]
        try:
            result = subprocess.run(bwrap_cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout}s"
        except Exception as e:
            logger.warning(f"bwrap failed ({e}), falling back to restricted subprocess")
            return self._run_restricted(command, timeout)

    def _run_appcontainer(self, command: str, timeout: int) -> tuple[bool, str]:
        """Windows: AppContainer via ctypes, with restricted subprocess fallback."""
        try:
            return self._run_appcontainer_impl(command, timeout)
        except Exception as e:
            logger.warning(f"AppContainer failed ({e}), using restricted subprocess")
            return self._run_restricted(command, timeout)

    def _run_appcontainer_impl(self, command: str, timeout: int) -> tuple[bool, str]:
        """
        Launch process in Windows AppContainer via ctypes Win32 API.

        Steps:
        1. CreateAppContainerProfile - get container SID
        2. Set ACL on sandbox_dir to allow container SID (via icacls)
        3. Create anonymous pipes for stdout/stderr capture
        4. InitializeProcThreadAttributeList + UpdateProcThreadAttribute
           with PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES
        5. CreateProcess with EXTENDED_STARTUPINFO_PRESENT
        6. WaitForSingleObject / GetExitCodeProcess
        7. Read pipes - collect output
        8. DeleteAppContainerProfile
        """
        import ctypes
        import ctypes.wintypes as wt
        import uuid

        userenv = ctypes.windll.userenv
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32

        container_name = f"bacchus-sandbox-{uuid.uuid4().hex[:8]}"
        container_sid_ptr = ctypes.c_void_p(0)

        hr = userenv.CreateAppContainerProfile(
            container_name, "Bacchus Sandbox", "Bacchus sandbox container",
            None, 0, ctypes.byref(container_sid_ptr)
        )
        if hr != 0:
            raise RuntimeError(f"CreateAppContainerProfile failed: HRESULT={hr:#010x}")

        try:
            # Grant container SID access to sandbox_dir
            sid_str_buf = ctypes.c_wchar_p(None)
            advapi32.ConvertSidToStringSidW(container_sid_ptr, ctypes.byref(sid_str_buf))
            sid_str = sid_str_buf.value or ""
            if sid_str:
                subprocess.run(
                    ["icacls", str(self.sandbox_dir), "/grant",
                     f"{sid_str}:(OI)(CI)F", "/T"],
                    capture_output=True, timeout=10
                )

            # Create stdout/stderr pipes
            sa = wt.SECURITY_ATTRIBUTES()
            sa.nLength = ctypes.sizeof(sa)
            sa.bInheritHandle = True
            read_stdout, write_stdout = wt.HANDLE(), wt.HANDLE()
            read_stderr, write_stderr = wt.HANDLE(), wt.HANDLE()
            if not kernel32.CreatePipe(
                ctypes.byref(read_stdout), ctypes.byref(write_stdout), ctypes.byref(sa), 0
            ):
                raise RuntimeError("CreatePipe stdout failed")
            if not kernel32.CreatePipe(
                ctypes.byref(read_stderr), ctypes.byref(write_stderr), ctypes.byref(sa), 0
            ):
                raise RuntimeError("CreatePipe stderr failed")
            kernel32.SetHandleInformation(read_stdout, 1, 0)
            kernel32.SetHandleInformation(read_stderr, 1, 0)

            # Security capabilities for AppContainer (no extra capabilities = most restrictive)
            class SECURITY_CAPABILITIES(ctypes.Structure):
                _fields_ = [
                    ("AppContainerSid", ctypes.c_void_p),
                    ("Capabilities", ctypes.c_void_p),
                    ("CapabilityCount", wt.DWORD),
                    ("Reserved", wt.DWORD),
                ]

            sec_cap = SECURITY_CAPABILITIES()
            sec_cap.AppContainerSid = container_sid_ptr
            sec_cap.CapabilityCount = 0

            # Proc thread attribute list (1 attribute)
            PTASC = 0x00020009  # PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES
            attr_sz = ctypes.c_size_t(0)
            kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(attr_sz))
            attr_buf = ctypes.create_string_buffer(attr_sz.value)
            kernel32.InitializeProcThreadAttributeList(attr_buf, 1, 0, ctypes.byref(attr_sz))
            kernel32.UpdateProcThreadAttribute(
                attr_buf, 0, PTASC, ctypes.byref(sec_cap),
                ctypes.sizeof(sec_cap), None, None
            )

            # STARTUPINFOEXW structures
            class _SIFW(ctypes.Structure):
                _fields_ = [
                    ("cb", wt.DWORD), ("lpReserved", wt.LPWSTR),
                    ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
                    ("dwX", wt.DWORD), ("dwY", wt.DWORD),
                    ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
                    ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD),
                    ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD),
                    ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                    ("lpReserved2", ctypes.c_void_p),
                    ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE),
                    ("hStdError", wt.HANDLE),
                ]

            class SIXW(ctypes.Structure):
                _fields_ = [("StartupInfo", _SIFW), ("lpAttributeList", ctypes.c_void_p)]

            si = SIXW()
            si.StartupInfo.cb = ctypes.sizeof(si)
            si.StartupInfo.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
            si.StartupInfo.hStdOutput = write_stdout
            si.StartupInfo.hStdError = write_stderr
            si.StartupInfo.hStdInput = wt.HANDLE(0)
            si.lpAttributeList = ctypes.cast(attr_buf, ctypes.c_void_p)

            class PI(ctypes.Structure):
                _fields_ = [
                    ("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                    ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD),
                ]

            pi = PI()
            cmd_str = f'cmd.exe /c "{command}"'
            ok = kernel32.CreateProcessW(
                None, cmd_str, None, None, True,
                0x00080000 | 0x08000000,  # EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW
                None, str(self.sandbox_dir), ctypes.byref(si), ctypes.byref(pi)
            )
            kernel32.CloseHandle(write_stdout)
            kernel32.CloseHandle(write_stderr)
            if not ok:
                raise RuntimeError(f"CreateProcessW failed: error={kernel32.GetLastError()}")

            wait_ms = min(timeout * 1000, 0xFFFFFFFF)
            wr = kernel32.WaitForSingleObject(pi.hProcess, wait_ms)
            ec = wt.DWORD(0)
            kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(ec))

            def read_pipe(h) -> str:
                out, buf, n = [], ctypes.create_string_buffer(4096), wt.DWORD(0)
                while kernel32.ReadFile(h, buf, 4096, ctypes.byref(n), None) and n.value:
                    out.append(buf.raw[:n.value])
                kernel32.CloseHandle(h)
                return b"".join(out).decode("utf-8", errors="replace")

            stdout_txt = read_pipe(read_stdout)
            stderr_txt = read_pipe(read_stderr)
            kernel32.CloseHandle(pi.hProcess)
            kernel32.CloseHandle(pi.hThread)
            return (ec.value == 0 and wr != 0x00000102), stdout_txt + stderr_txt

        finally:
            try:
                userenv.DeleteAppContainerProfile(container_name)
            except Exception:
                pass
            try:
                kernel32.LocalFree(container_sid_ptr)
            except Exception:
                pass

    def _run_restricted(self, command: str, timeout: int) -> tuple[bool, str]:
        """Fallback: clean-environment subprocess inside sandbox_dir (best-effort isolation)."""
        clean_env = {
            "PATH": os.environ.get("PATH", ""),
            "TEMP": str(self.sandbox_dir), "TMP": str(self.sandbox_dir),
            "HOME": str(self.sandbox_dir), "USERPROFILE": str(self.sandbox_dir),
        }
        try:
            result = subprocess.run(
                command, shell=True, cwd=str(self.sandbox_dir),
                env=clean_env, capture_output=True, text=True, timeout=timeout
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout}s"
        except Exception as e:
            return False, f"Sandbox execution error: {e}"
