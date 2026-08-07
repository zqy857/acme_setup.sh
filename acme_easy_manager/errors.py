"""错误处理：将 acme.sh 原始错误翻译为普通用户可理解的提示。"""
from __future__ import annotations

import re
from typing import Optional

# 规则：匹配模式 -> (原因, 建议)
_RULES: list[tuple[str, tuple[str, str]]] = [
    # DNS 相关问题
    ("can not verify the domain", ("DNS 验证失败", "1) 检查 DNS API Token 是否有该域名的解析权限; 2) 确认域名解析记录已正确配置; 3) DNS 记录可能尚未生效，等待几分钟后重试")),
    ("api error code: 81057", ("阿里云 DNS 鉴权失败", "请检查阿里云 AccessKey ID / Secret 是否正确，且已授权 AliyunDNSFullAccess")),
    ("invalid api key", ("API Key 无效", "检查 API Token / Key 是否填写正确、是否有过期或被撤销")),
    ("zone not found", ("DNS 区域不存在", "确认在 DNS 服务商处已添加该主域名")),
    ("clock skew", ("系统时间偏差过大", "请同步时间（如运行 timedatectl set-ntp true）后重试")),
    # 域名问题
    ("invalid domain", ("域名格式不合法", "请检查域名是否包含非法字符或多余点号")),
    ("domain is not", ("域名不能用于申请", "泛域名与已有域名冲突，或域名不允许签发，请核对输入")),
    # CA / 签发问题
    ("too many certificates", ("证书签发过于频繁", "受 Let's Encrypt 速率限制，请等待一段时间后再申请")),
    ("rate limit", ("请求被限速", "申请过于频繁，请稍后重试（Let's Encrypt 每周每域名 5 次）")),
    ("invalid account", ("ACME 账户无效", "请重新注册账户邮箱后重试")),
    ("timed out", ("网络请求超时", "检查网络连通性与防火墙，或切换证书签发机构重试")),
    ("connection refused", ("连接被拒绝", "检查本机网络或代理设置")),
    ("EVP_PKEY_get1_EC_KEY", ("OpenSSL 版本过旧", "请升级 OpenSSL 到 1.0.2 以上")),
    ("unexpected error", ("未知错误", "请查看日志文件 acme-manager.log 以获取详细信息")),
    ("The remaining calls", ("API 调用次数不足", "请检查您的 DNS API 配额或账户余额")),
    ("permission denied", ("权限不足", "请以正确用户运行，或检查文件/目录权限")),
    ("no such file or directory", ("文件或目录不存在", "请检查 acme.sh 路径或证书安装目录是否存在")),
    ("deploy hook error", ("部署失败", "请检查目标服务路径与重启命令是否正确")),
    ("already existed", ("证书已存在", "请先删除或强制覆盖，或使用重新申请功能")),
]

_UNKNOWN = ("执行异常", "请检查日志与网络，若为 DNS 相关请核对认证信息")


def extract_error(raw: str) -> str:
    """从 acme.sh 输出中提取主要错误信息。"""
    raw = (raw or "").strip()
    if not raw:
        return "无错误输出"
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if re.search(r"error|fail|denied|invalid|refused|timed|unable", ln, re.I):
            return ln[:300]
    return lines[-1][:300] if lines else ""

def summarize_error(raw: str) -> tuple[str, str]:
    """翻译原始输出，返回 (原因, 建议)。"""
    text = (raw or "").lower()
    for pattern, (reason, advice) in _RULES:
        if pattern in text:
            return reason, advice
    return _UNKNOWN


def format_error(raw: str) -> str:
    """返回完整可读的错误说明。"""
    raw = (raw or "").strip()
    reason, advice = summarize_error(raw)
    detail = extract_error(raw)
    block = f"[bold red]{reason}[/bold red]\n[cyan]原信息:[/cyan] {detail}\n[green]建议:[/green] {advice}"
    return block