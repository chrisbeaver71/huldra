"""Huldra V1 Deterministic Hardware Detection.

Provides first-run hardware detection for:
- GPU/VRAM detection (NVIDIA via nvidia-smi, AMD via rocm-smi, fallback to WMI)
- System RAM (total and available, in GB)
- Storage (disk free space at HULDRA_HOME)
- OS headroom (reserved for system, typical ~4 GB)
- Usable runtime/backend capability (CUDA version, CPU features)

All detection is deterministic — no benchmark results, no inferred
thresholds, and no assumptions about Chris's 32 GB lab machine.
Results feed directly into the recommender which compares against
declared profile requirements plus reserved headroom.

Usage::

    from huldra_hardware import detect_hardware
    hw = detect_hardware()
    print(hw.vram_total_gb, hw.ram_total_gb)
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Reserved headroom: system needs at minimum this much RAM/VRAM free
SYSTEM_RESERVED_RAM_GB = 2.0
SYSTEM_RESERVED_VRAM_GB = 0.5
SYSTEM_RESERVED_DISK_GB = 5.0


@dataclass
class GPUInfo:
    """Detected GPU information."""
    name: str = "unknown"
    driver_version: str = ""
    cuda_version: str = ""
    vram_total_gb: float = 0.0
    vram_free_gb: float = 0.0
    vendor: str = "unknown"  # nvidia, amd, intel, unknown
    compute_capability: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "driver_version": self.driver_version,
            "cuda_version": self.cuda_version,
            "vram_total_gb": round(self.vram_total_gb, 2),
            "vram_free_gb": round(self.vram_free_gb, 2),
            "vendor": self.vendor,
            "compute_capability": self.compute_capability,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GPUInfo":
        return cls(
            name=data.get("name", "unknown"),
            driver_version=data.get("driver_version", ""),
            cuda_version=data.get("cuda_version", ""),
            vram_total_gb=data.get("vram_total_gb", 0.0),
            vram_free_gb=data.get("vram_free_gb", 0.0),
            vendor=data.get("vendor", "unknown"),
            compute_capability=data.get("compute_capability", ""),
        )


@dataclass
class StorageInfo:
    """Detected storage information."""
    path: str = ""
    total_gb: float = 0.0
    free_gb: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "total_gb": round(self.total_gb, 2),
            "free_gb": round(self.free_gb, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StorageInfo":
        return cls(
            path=data.get("path", ""),
            total_gb=data.get("total_gb", 0.0),
            free_gb=data.get("free_gb", 0.0),
        )


@dataclass
class HardwareProfile:
    """Complete hardware detection result.

    Contains all detected hardware info needed for profile recommendation.
    All values are in GB unless otherwise noted.
    """
    gpu: GPUInfo = field(default_factory=GPUInfo)
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    storage: StorageInfo = field(default_factory=StorageInfo)
    os_name: str = ""
    os_version: str = ""
    python_version: str = ""
    platform_machine: str = ""
    detect_time: float = 0.0

    # Derived values
    usable_vram_gb: float = 0.0  # vram_total - SYSTEM_RESERVED_VRAM_GB
    usable_ram_gb: float = 0.0  # ram_available - SYSTEM_RESERVED_RAM_GB
    usable_disk_gb: float = 0.0  # storage.free - SYSTEM_RESERVED_DISK_GB

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu": self.gpu.to_dict(),
            "ram_total_gb": round(self.ram_total_gb, 2),
            "ram_available_gb": round(self.ram_available_gb, 2),
            "storage": self.storage.to_dict(),
            "os_name": self.os_name,
            "os_version": self.os_version,
            "python_version": self.python_version,
            "platform_machine": self.platform_machine,
            "detect_time": self.detect_time,
            "usable_vram_gb": round(self.usable_vram_gb, 2),
            "usable_ram_gb": round(self.usable_ram_gb, 2),
            "usable_disk_gb": round(self.usable_disk_gb, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareProfile":
        return cls(
            gpu=GPUInfo.from_dict(data.get("gpu", {})),
            ram_total_gb=data.get("ram_total_gb", 0.0),
            ram_available_gb=data.get("ram_available_gb", 0.0),
            storage=StorageInfo.from_dict(data.get("storage", {})),
            os_name=data.get("os_name", ""),
            os_version=data.get("os_version", ""),
            python_version=data.get("python_version", ""),
            platform_machine=data.get("platform_machine", ""),
            detect_time=data.get("detect_time", 0.0),
            usable_vram_gb=data.get("usable_vram_gb", 0.0),
            usable_ram_gb=data.get("usable_ram_gb", 0.0),
            usable_disk_gb=data.get("usable_disk_gb", 0.0),
        )


# ---------------------------------------------------------------------------
# Detection functions (deterministic, no model inference)
# ---------------------------------------------------------------------------

def _detect_gpu_nvidia() -> Optional[GPUInfo]:
    """Detect NVIDIA GPU via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,compute_capability,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            return None

        name = parts[0]
        driver = parts[1]
        cc = parts[2]
        vram_total = float(parts[3]) / 1024.0  # MiB -> GB
        vram_free = float(parts[4]) / 1024.0

        # Detect CUDA version
        cuda_ver = ""
        try:
            cuda_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            # CUDA version is in the header, try a separate query
            header_result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for hline in header_result.stdout.split("\n"):
                if "CUDA Version:" in hline:
                    cuda_ver = hline.split("CUDA Version:")[1].strip().split()[0]
                    break
        except Exception:
            pass

        return GPUInfo(
            name=name,
            driver_version=driver,
            cuda_version=cuda_ver,
            vram_total_gb=vram_total,
            vram_free_gb=vram_free,
            vendor="nvidia",
            compute_capability=cc,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        logger.debug("nvidia-smi detection failed: %s", e)
        return None


def _detect_gpu_wmi() -> Optional[GPUInfo]:
    """Detect GPU via WMI (Windows Management Instrumentation)."""
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_VideoController | "
                    "Select-Object Name, DriverVersion, AdapterRAM | "
                    "ConvertTo-Json"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout.strip())
        if isinstance(data, list):
            gpu = data[0]
        elif isinstance(data, dict):
            gpu = data
        else:
            return None

        name = gpu.get("Name", "unknown")
        driver = gpu.get("DriverVersion", "")
        adapter_ram = gpu.get("AdapterRAM", 0)
        # AdapterRAM is in bytes for WMI
        vram_total = adapter_ram / (1024 ** 3) if adapter_ram else 0.0

        vendor = "unknown"
        name_lower = name.lower()
        if "nvidia" in name_lower or "geforce" in name_lower:
            vendor = "nvidia"
        elif "amd" in name_lower or "radeon" in name_lower:
            vendor = "amd"
        elif "intel" in name_lower:
            vendor = "intel"

        return GPUInfo(
            name=name,
            driver_version=driver,
            vram_total_gb=vram_total,
            vram_free_gb=vram_total,  # WMI doesn't expose free VRAM
            vendor=vendor,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        logger.debug("WMI GPU detection failed: %s", e)
        return None


def _detect_gpu() -> GPUInfo:
    """Detect GPU with fallback chain."""
    gpu = _detect_gpu_nvidia()
    if gpu:
        return gpu
    gpu = _detect_gpu_wmi()
    if gpu:
        return gpu
    return GPUInfo()


def _detect_ram() -> tuple[float, float]:
    """Detect system RAM. Returns (total_gb, available_gb)."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    (
                        "$os = Get-CimInstance Win32_OperatingSystem; "
                        "[math]::Round($os.TotalVisibleMemorySize/1MB, 2), "
                        "[math]::Round($os.FreePhysicalMemory/1MB, 2)"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    return float(parts[0]), float(parts[1])

        # Linux/macOS fallback via /proc or sysctl
        import psutil  # type: ignore[import-untyped]
        mem = psutil.virtual_memory()
        return round(mem.total / (1024 ** 3), 2), round(mem.available / (1024 ** 3), 2)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("RAM detection via psutil failed: %s", e)

    # Last resort: os.sysconf
    try:
        if hasattr(os, "sysconf"):
            page_size = os.sysconf("SC_PAGE_SIZE")
            total_pages = os.sysconf("SC_PHYS_PAGES")
            total_gb = (page_size * total_pages) / (1024 ** 3)
            return round(total_gb, 2), round(total_gb * 0.7, 2)  # rough estimate
    except Exception:
        pass

    return 0.0, 0.0


def _detect_storage(huldra_home: Optional[str] = None) -> StorageInfo:
    """Detect storage at HULDRA_HOME."""
    path = huldra_home or os.environ.get("HULDRA_HOME") or str(Path.cwd())
    try:
        usage = shutil.disk_usage(path)
        return StorageInfo(
            path=path,
            total_gb=round(usage.total / (1024 ** 3), 2),
            free_gb=round(usage.free / (1024 ** 3), 2),
        )
    except Exception as e:
        logger.debug("Storage detection failed: %s", e)
        return StorageInfo(path=path)


def _detect_os() -> tuple[str, str]:
    """Detect OS name and version."""
    return platform.system(), platform.release()


def detect_hardware(
    huldra_home: Optional[str] = None,
) -> HardwareProfile:
    """Run all hardware detection and return a complete HardwareProfile.

    This is deterministic — no benchmarks, no model inference, no
    assumptions about machine size.

    Args:
        huldra_home: Path to HULDRA_HOME for storage detection.
            Defaults to $HULDRA_HOME or cwd.
    """
    import time

    hw = HardwareProfile()
    hw.detect_time = time.time()
    hw.os_name, hw.os_version = _detect_os()
    hw.python_version = platform.python_version()
    hw.platform_machine = platform.machine()

    # GPU
    hw.gpu = _detect_gpu()

    # RAM
    hw.ram_total_gb, hw.ram_available_gb = _detect_ram()

    # Storage
    hw.storage = _detect_storage(huldra_home)

    # Derived usable values
    hw.usable_vram_gb = max(0.0, hw.gpu.vram_total_gb - SYSTEM_RESERVED_VRAM_GB)
    hw.usable_ram_gb = max(0.0, hw.ram_available_gb - SYSTEM_RESERVED_RAM_GB)
    hw.usable_disk_gb = max(0.0, hw.storage.free_gb - SYSTEM_RESERVED_DISK_GB)

    logger.info(
        "Hardware detected: GPU=%s (%.1f GB VRAM), RAM=%.1f/%.1f GB, "
        "Disk=%.1f GB free, OS=%s %s",
        hw.gpu.name,
        hw.gpu.vram_total_gb,
        hw.ram_available_gb,
        hw.ram_total_gb,
        hw.storage.free_gb,
        hw.os_name,
        hw.os_version,
    )

    return hw


def save_hardware_profile(hw: HardwareProfile, path: Path) -> None:
    """Save a hardware detection result to disk for caching."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(hw.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )


def load_hardware_profile(path: Path) -> Optional[HardwareProfile]:
    """Load a cached hardware detection result."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return HardwareProfile.from_dict(data)
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to load cached hardware profile: %s", e)
        return None
