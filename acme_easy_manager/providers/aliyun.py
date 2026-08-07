"""阿里云 DNS API 认证。"""
from __future__ import annotations

from .base import BaseProvider, CredentialField


class AliYunProvider(BaseProvider):
    name = "ali"
    display_name = "阿里云 DNS"
    credential_fields = [
        CredentialField(key="accesskeyid", label="AccessKey ID", secret=True),
        CredentialField(key="accesskeysecret", label="AccessKey Secret", secret=True),
    ]

    def env_from_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        return {
            "Ali_Key": credentials.get("accesskeyid", ""),
            "Ali_Secret": credentials.get("accesskeysecret", ""),
        }