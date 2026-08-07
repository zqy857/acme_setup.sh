"""腾讯云 DNS API 认证。"""
from __future__ import annotations

from .base import BaseProvider, CredentialField


class TencentProvider(BaseProvider):
    name = "tencent"
    display_name = "腾讯云 DNS"
    credential_fields = [
        CredentialField(key="secretid", label="SecretId", secret=True),
        CredentialField(key="secretkey", label="SecretKey", secret=True),
    ]

    def env_from_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        return {
            "Tencent_SecretId": credentials.get("secretid", ""),
            "Tencent_SecretKey": credentials.get("secretkey", ""),
        }