"""Cloudflare DNS API 认证。"""
from __future__ import annotations

from .base import BaseProvider, CredentialField


class CloudflareProvider(BaseProvider):
    name = "cf"
    display_name = "Cloudflare"
    # Cloudflare 已取消 Global API Key，仅用 API Token（性能更安全）
    credential_fields = [
        CredentialField(key="token", label="Cloudflare API Token", secret=False),
    ]

    def env_from_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        env: dict[str, str] = {}
        if credentials.get("token"):
            env["CF_Token"] = credentials["token"]
        return env