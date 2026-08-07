"""华为云 DNS API 认证。"""
from __future__ import annotations

from .base import BaseProvider, CredentialField


class HuaweiProvider(BaseProvider):
    name = "huawei"
    display_name = "华为云 DNS"
    credential_fields = [
        CredentialField(key="username", label="IAM 用户名", secret=False),
        CredentialField(key="password", label="IAM 用户密码", secret=True),
        CredentialField(key="domain", label="账号名 / 主账号", secret=False),
        CredentialField(key="projectid", label="项目 ID (可选)", secret=False),
    ]

    def env_from_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        env = {
            "HUAWEICLOUD_Username": credentials.get("username", ""),
            "HUAWEICLOUD_Password": credentials.get("password", ""),
            "HUAWEICLOUD_DomainName": credentials.get("domain", ""),
        }
        if credentials.get("projectid"):
            env["HUAWEICLOUD_ProjectID"] = credentials["projectid"]
        return env