"""Device-level queries: device list, info, screen size, connectivity."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..adb.client import ADBClient, classify_error
from ..errors import ADBError, ToolError, guarded
from ..models.responses import ActionResponse, ErrorCode

_PROP_RE = re.compile(r"^\[(.*?)\]: \[(.*?)\]$")
_SIZE_RE = re.compile(r"(\d+)x(\d+)")

_INFO_PROPS = {
    "model": "ro.product.model",
    "manufacturer": "ro.product.manufacturer",
    "brand": "ro.product.brand",
    "device": "ro.product.device",
    "android_version": "ro.build.version.release",
    "sdk_version": "ro.build.version.sdk",
    "cpu_abi": "ro.product.cpu.abi",
    "build_fingerprint": "ro.build.fingerprint",
}


class DeviceManager:
    def __init__(self, adb: ADBClient) -> None:
        self.adb = adb

    @guarded("list_devices")
    def list_devices(self) -> ActionResponse:
        result = self.adb.run(["devices", "-l"], use_device=False)
        devices: List[Dict[str, object]] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("*") or line.startswith("List of devices"):
                continue
            tokens = line.split()
            if len(tokens) < 2:
                continue
            attrs = dict(t.split(":", 1) for t in tokens[2:] if ":" in t)
            devices.append(
                {
                    "serial": tokens[0],
                    "state": tokens[1],
                    "is_emulator": tokens[0].startswith("emulator-"),
                    "model": attrs.get("model"),
                    "product": attrs.get("product"),
                    "transport_id": attrs.get("transport_id"),
                }
            )
        msg = f"Found {len(devices)} device(s)" if devices else "No devices connected"
        return ActionResponse.ok("list_devices", msg, {"devices": devices, "count": len(devices)})

    @guarded("get_device_info")
    def get_device_info(self) -> ActionResponse:
        out = self.adb.shell("getprop").stdout
        props: Dict[str, str] = {}
        for line in out.splitlines():
            m = _PROP_RE.match(line.strip())
            if m:
                props[m.group(1)] = m.group(2)
        if not props:
            raise ToolError(ErrorCode.COMMAND_FAILED, "Could not read device properties")
        info: Dict[str, object] = {k: props.get(p) for k, p in _INFO_PROPS.items()}
        info["is_emulator"] = (
            props.get("ro.kernel.qemu") == "1"
            or props.get("ro.boot.qemu") == "1"
            or "emulator" in (props.get("ro.product.device") or "").lower()
            or "sdk_gphone" in (props.get("ro.product.name") or "")
        )
        info["serial"] = self.adb.device_id or props.get("ro.serialno")
        return ActionResponse.ok("get_device_info", "Device information retrieved", info)

    def screen_size(self) -> Tuple[int, int]:
        """Return (width, height) in pixels; raises ToolError on failure."""
        out = self.adb.shell("wm", "size").stdout
        matches = _SIZE_RE.findall(out)
        if not matches:
            raise ToolError(ErrorCode.COMMAND_FAILED, "Could not determine screen size", out.strip()[:200])
        w, h = matches[-1]  # "Override size" (if any) is printed last
        return int(w), int(h)

    @guarded("get_screen_size")
    def get_screen_size(self) -> ActionResponse:
        w, h = self.screen_size()
        data: Dict[str, object] = {"width": w, "height": h}
        try:
            dens = re.findall(r"(\d+)", self.adb.shell("wm", "density", check=False).stdout)
            if dens:
                data["density"] = int(dens[-1])
        except ADBError:
            pass
        return ActionResponse.ok("get_screen_size", f"Screen size is {w}x{h}", data)

    @guarded("is_device_connected")
    def is_device_connected(self) -> ActionResponse:
        """``success`` means the query ran; the answer is in ``data['connected']``."""
        r = self.adb.run(["get-state"], check=False)
        if classify_error(r.stderr) == ErrorCode.MULTIPLE_DEVICES:
            raise ADBError(
                ErrorCode.MULTIPLE_DEVICES,
                "Multiple devices connected",
                "Set ANDROID_DEVICE_ID to choose one.",
            )
        state = r.stdout.strip() or r.stderr.strip()
        connected = r.ok and r.stdout.strip() == "device"
        return ActionResponse.ok(
            "is_device_connected",
            "Device is connected" if connected else "Device is not connected",
            {"connected": connected, "state": state, "device_id": self.adb.device_id},
        )

    def is_responsive(self) -> bool:
        """Cheap liveness probe: can the device run a trivial shell command?"""
        try:
            r = self.adb.shell("echo", "ok", timeout=5, check=False)
        except ToolError:
            return False
        return r.ok and "ok" in r.stdout
