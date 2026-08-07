"""用户交互界面：基于 Rich + Questionary 的终端交互式界面。"""
from __future__ import annotations

import getpass
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from . import acme, certs, config, deploy, renew, system
from .logger import get_logger

console = Console()
log = get_logger("ui")


def banner(title: str = "Acme Easy Manager") -> None:
    console.print(Panel.fit(
        f"[bold blue]{title}[/bold blue]\n"
        "[dim]一个友好的 SSL 证书申请与生命周期管理工具[/dim]",
        border_style="blue", box=box.DOUBLE,
    ))


def separator(text: str) -> None:
    console.rule(f"[bold cyan]{text}[/bold cyan]")


def show_env(report: system.EnvReport) -> None:
    table = Table(title="系统环境检测", box=box.ROUNDED)
    table.add_column("项目", style="bold")
    table.add_column("状态")
    table.add_column("信息")

    def flag(ok: bool) -> str:
        return "[green]✔[/green]" if ok else "[red]✘[/red]"

    table.add_row("系统", f"{report.os_name} {report.distro} {report.distro_version}", "")
    table.add_row("Shell", report.shell_type, report.shell)
    table.add_row("curl", flag(report.has_curl), "")
    table.add_row("wget", flag(report.has_wget), "")
    table.add_row("OpenSSL", flag(report.has_openssl), report.openssl_version)
    table.add_row("acme.sh", flag(report.acme_installed), report.acme_home if report.acme_installed else "未安装")
    console.print(table)


def menu(title: str, choices: list[str]) -> str:
    if len(choices) <= 1:
        return choices[0]
    choice = questionary.select(
        title, choices=choices, pointer="→",
        instruction="",  # 去掉 "Use arrow keys" 提示
        style=questionary.Style.from_dict({
            "selected": "bold",
        })
    ).ask()
    return choice or ""


def text_input(prompt: str, default: str = "", password: bool = False) -> str:
    if password:
        return getpass.getpass(prompt)
    return questionary.text(prompt, default=default).ask() or ""


def confirm(prompt: str, default: bool = False) -> bool:
    return bool(questionary.confirm(prompt, default=default).ask())


def select_domains(stage: str) -> list[str]:
    """交互式输入域名，返回域名列表。"""
    separator("输入域名")
    console.print("[bold]请输入要申请证书的域名（可输入多个，追加输入 SAN 域名）[/bold]\n"
                  "[dim]支持：单域名、多域名 SAN、泛域名（*.example.com）[/dim]")
    domains: list[str] = []
    while True:
        d = text_input(f"域名 #{len(domains)+1}" if domains else "主域名（第一个域名）", "")
        d = (d or "").strip().lower().rstrip(".")
        if not d:
            break
        ok, err = certs.validate_domain(d)
        if not ok:
            console.print(f"[red]✘ {err}[/red]")
            console.print("提示：如需申请*.example.com，请输入 *.example.com")
            continue
        if d not in domains:
            domains.append(d)
            console.print(f"[green]已添加：{d}[/green]")
        if len(domains) >= 1 and not confirm("继续添加更多域名？", default=False):
            break
    return domains


def choose_ca() -> str:
    _map = {"Let's Encrypt": "letsencrypt", "ZeroSSL": "zerossl",
            "Buypass": "buypass", "Google": "google"}
    default = config.get_config("ca", "letsencrypt")
    labels = list(_map.keys())
    default_idx = labels.index("Let's Encrypt") if default not in _map.values() else \
        [k for k, v in _map.items() if v == default][0]
    choice = menu("选择证书颁发机构 (CA)", labels)
    val = _map[choice]
    config.set_config("ca", val)
    return val


def choose_key_type() -> str:
    _map = {"ECC P-256": "ec-256", "ECC P-384": "ec-384",
            "RSA 2048": "2048", "RSA 4096": "4096"}
    choice = menu("选择密钥类型", list(_map))
    val = _map[choice]
    config.set_config("key_type", val)
    return val


def choose_provider() -> dict:
    """选择 DNS 服务商并填入凭据，返回 {provider, env, provider_name}。"""
    from .providers import all_providers
    providers = all_providers()
    names = [f"{p.display_name} ({p.name})" for p in providers]
    choice = menu("选择 DNS 服务商", names + ["返回"])
    if choice == "返回":
        return {}
    idx = names.index(choice)
    provider = providers[idx]

    # 读取已保存的凭据（持久化复用，避免每次重新输入）
    cfg = config.KVStore(config.PROVIDERS_DIR / f"{provider.name}.conf")
    saved = {k: cfg.get(k, "") for k in (f.key for f in provider.credential_fields)}

    credentials: dict[str, str] = {}
    for field in provider.credential_fields:
        default = saved.get(field.key, "")
        value = text_input(f"{field.label}（{field.key}）", default=default,
                           password=field.secret)
        # 留空则沿用已保存值（明示显示，不强制隐藏）
        if not value:
            value = default
        credentials[field.key] = value

    env = provider.env_from_credentials(credentials)

    # 保存凭据到独立配置文件（持久化，下次自动带出）
    for field in provider.credential_fields:
        if credentials.get(field.key):
            cfg.set(field.key, credentials[field.key])
    cfg.save()

    return {"provider": provider, "provider_name": provider.name, "env": env}

def view_certificates() -> None:
    """展示证书列表。"""
    separator("证书列表")
    certs_list = acme.list_certs()
    if not certs_list:
        console.print("[yellow]尚未发现任何已签发的证书[/yellow]")
        console.print("[dim]请先在“申请证书”中完成一次签发[/dim]")
        console.print(f"[dim]已检查的 acme.sh 目录：{acme.get_acme_home()}[/dim]")
        return
    table = Table(title=f"共 {len(certs_list)} 张证书", box=box.SIMPLE_HEAVY)
    table.add_column("主域名", style="bold")
    table.add_column("SAN", style="dim")
    table.add_column("CA")
    table.add_column("密钥")
    table.add_column("剩余天数", justify="right")
    for c in certs_list:
        days = c.expired_days
        if days > 30:
            color = "green"
        elif days > 7:
            color = "yellow"
        else:
            color = "red"
        table.add_row(c.main_domain, ", ".join(c.domains), c.ca, c.key_type,
                      f"[{color}]{days}[/{color}]")
    console.print(table)


def distinguish_advanced_menu():
    pass


def unsupported(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")


def success(msg: str) -> None:
    console.print(f"[bold green]✔ {msg}[/bold green]")


def failure(msg: str) -> None:
    console.print(f"[bold red]✘ {msg}[/bold red]")


def info(msg: str) -> None:
    console.print(f"[cyan]•[/cyan] {msg}")