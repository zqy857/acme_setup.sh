"""DNS Provider 基类与抽象接口。"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional

from .. import config


@dataclass
class CredentialField:
    key: str          # 配置项键名
    label: str        # 界面显示名
    secret: bool = True   # 是否为敏感信息（隐藏显示）

    @property
    def env_key(self) -> str:
        return f"SAVED_{self.key.upper()}"


class BaseProvider(abc.ABC):
    """所有 DNS Provider 的基类。"""

    #: acme.sh 使用的 provider 名（用于 --dns dns_xxx）
    name: ClassVar[str] = ""
    #: 服务商展示名
    display_name: ClassVar[str] = ""
    #: 需要用户填写的认证字段
    credential_fields: ClassVar[list[CredentialField]] = []

    def env_from_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        """将用户填写的凭据转换为 acme.sh 所需的环境变量。"""
        env: dict[str, str] = {}
        provider = self.name.upper()  # 例如 CF
        for cred in self.credential_fields:
            value = credentials.get(cred.key)
            if value:
                # acme.sh 使用 <PROVIDER>_Token、<PROVIDER>_Key 等约定
                env[f"{provider}_{cred.key.upper()}"] = value
        return env

    @classmethod
    def get(cls, key: str) -> Optional["BaseProvider"]:
        for provider in all_providers():
            if provider.name == key or provider.display_name == key:
                return provider
        return None


def all_providers() -> list[BaseProvider]:
    from .cloudflare import CloudflareProvider
    from .aliyun import AliYunProvider
    from .tencent import TencentProvider
    from .huawei import HuaweiProvider

    return [
        CloudflareProvider(),
        AliYunProvider(),
        TencentProvider(),
        HuaweiProvider(),
    ]