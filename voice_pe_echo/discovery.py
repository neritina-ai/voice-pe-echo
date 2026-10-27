"""Find ESPHome devices (such as the Voice PE) on the local network via mDNS."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

SERVICE_TYPE = "_esphomelib._tcp.local."


@dataclass
class FoundDevice:
    name: str
    friendly_name: str
    host: str
    addresses: list[str]
    port: int
    project_name: str
    project_version: str
    mac: str
    encryption: str  # "key" (a key is set), "none" (no key set) or "unknown"

    @property
    def is_voice_pe(self) -> bool:
        return "voice pe" in self.project_name.lower() or self.name.startswith(
            "home-assistant-voice"
        )

    def describe(self) -> str:
        key = {"key": "需要金鑰", "none": "不需要金鑰"}.get(self.encryption, "金鑰未知")
        mac = ":".join(self.mac[i : i + 2] for i in range(0, len(self.mac), 2)) or "?"
        firmware = self.project_version or "?"
        return (
            f"{self.friendly_name or self.name}\n"
            f"      主機：{self.host}  IP：{', '.join(self.addresses) or '?'}\n"
            f"      韌體：{firmware}  MAC：{mac}  {key}"
        )


def _txt(properties: dict[bytes, bytes | None], key: str) -> str:
    value = properties.get(key.encode())
    return value.decode("utf-8", "replace") if value else ""


def _parse(info: AsyncServiceInfo) -> FoundDevice:
    props = info.properties
    if b"api_encryption" in props:
        encryption = "key"
    elif b"api_encryption_supported" in props:
        encryption = "none"
    else:
        encryption = "unknown"
    addresses = sorted(info.parsed_scoped_addresses(), key=lambda a: ":" in a)  # IPv4 first
    return FoundDevice(
        name=info.name.removesuffix("." + SERVICE_TYPE),
        friendly_name=_txt(props, "friendly_name"),
        host=(info.server or "").rstrip("."),
        addresses=addresses,
        port=info.port or 6053,
        project_name=_txt(props, "project_name"),
        project_version=_txt(props, "project_version"),
        mac=_txt(props, "mac"),
        encryption=encryption,
    )


async def discover(aiozc: AsyncZeroconf, timeout: float = 3.0) -> list[FoundDevice]:
    names: set[str] = set()

    def on_change(
        zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
    ) -> None:
        if state_change is not ServiceStateChange.Removed:
            names.add(name)

    browser = AsyncServiceBrowser(aiozc.zeroconf, SERVICE_TYPE, handlers=[on_change])
    try:
        await asyncio.sleep(timeout)
    finally:
        await browser.async_cancel()

    infos = [AsyncServiceInfo(SERVICE_TYPE, name) for name in sorted(names)]
    await asyncio.gather(*(info.async_request(aiozc.zeroconf, 3000) for info in infos))
    return [_parse(info) for info in infos if info.port]
