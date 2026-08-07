"""程序入口：初始化并进入主菜单循环。"""
from __future__ import annotations

from rich.console import Console

from . import acme, certs, config, deploy, renew, system, ui
from .logger import get_logger, setup as setup_logging

console = Console()


def require_ready() -> bool:
    """检查环境是否满足要求，否则引导安装。"""
    report = system.last_report() or system.detect()
    ui.show_env(report)

    if not report.has_openssl:
        ui.failure("缺少 OpenSSL，无法生成证书")
        ui.info("尝试安装：apt-get install openssl 或 yum install openssl")
        return False

    if not report.has_curl and not report.has_wget:
        ui.failure("缺少 curl/wget，无法下载 acme.sh 或发起证书请求")
        return False

    if not report.acme_installed:
        ui.info("未检测到 acme.sh，本次将自动安装")
        if ui.confirm("现在安装 acme.sh？", default=True):
            ok, msg = system.install_acme()
            if ok:
                ui.success(msg)
            else:
                ui.failure(f"安装失败：{msg}")
                return False
        else:
            return False

    # 检查并设置账户邮箱
    if not config.MAIN_CONFIG.exists():
        email = ui.text_input("请输入用于接收证书通知的邮箱", "")
        if email:
            config.set_config("account_email", email)
            ok, msg = acme.register_account(email)
            ui.info(msg)

    return True


def main_menu() -> None:
    choice = ui.menu("请选择操作", [
        "1. 申请证书（含自动 DNS 验证）",
        "2. 查看证书列表",
        "3. 手动续期/删除/重新申请",
        "4. 自动续期设置",
        "5. 部署证书到 Web 服务",
        "6. 系统环境 / acme.sh 管理",
        "7. 退出",
    ])
    if choice.startswith("1"):
        apply_flow()
    elif choice.startswith("2"):
        ui.view_certificates()
        _wait()
    elif choice.startswith("3"):
        manage_flow()
    elif choice.startswith("4"):
        renew_flow()
    elif choice.startswith("5"):
        deploy_flow()
    elif choice.startswith("6"):
        system_flow()
    else:
        return False
    return True


def system_flow() -> None:
    """系统环境与 acme.sh 管理。"""
    choice = ui.menu("系统环境与 acme.sh 管理", [
        "环境检测", "安装 / 修复 acme.sh", "卸载 acme.sh", "卸载本程序", "返回"
    ])
    if choice == "环境检测":
        ui.show_env(system.detect())
        _wait()
    elif choice == "安装 / 修复 acme.sh":
        if not _require_root("安装 acme.sh"):
            return
        report = system.last_report() or system.detect()
        if report.acme_installed:
            ui.info("acme.sh 已安装，将重新安装以修复")
        ok, msg = system.install_acme()
        (ui.success if ok else ui.failure)(msg)
        _wait()
    elif choice == "卸载 acme.sh":
        if not _require_root("卸载 acme.sh"):
            return
        ui.failure("卸载将删除 acme.sh 程序、定时任务以及全部已签发证书！")
        if ui.confirm("确认卸载 acme.sh？", default=False):
            ok, msg = system.uninstall_acme()
            (ui.success if ok else ui.failure)(msg)
        _wait()
    elif choice == "卸载本程序":
        ui.failure("卸载本程序将删除程序、配置与日志（含 DNS Token），仅保留卸载脚本 uninstall.sh")
        if ui.confirm("确认继续卸载本程序？", default=False):
            uninstall_program()


def apply_flow() -> None:
    ui.separator("申请证书")
    ca = ui.choose_ca()
    domains = ui.select_domains("domain")
    if not domains:
        ui.failure("未输入有效域名，已取消")
        return
    key_type = ui.choose_key_type()

    provider = ui.choose_provider()
    if not provider:
        ui.failure("未选择 DNS 服务商，已取消")
        return
    provider_name, env = provider["provider_name"], provider["env"]

    email = config.get_config("account_email", "")
    if not email:
        email = ui.text_input("用于 acme.sh 账户/通知的邮箱", "")
        config.set_config("account_email", email)
        acme.register_account(email)

    force = ui.confirm("强制重新签发（绕过缓存/续期）？", default=False)
    ui.info("正在申请证书，DNS 验证可能需要几分钟……")

    ok, msg = certs.apply(domains, provider_name, env, email,
                          ca=ca, key_type=key_type, force=force)
    if ok:
        ui.success(msg)
    else:
        ui.failure("签发失败")
        console.print(msg)


def manage_flow() -> None:
    ui.view_certificates()
    choice = ui.menu("证书管理", [
        "续期单张证书", "重新申请证书", "删除证书", "删除全部证书", "清理签发失败的残留文件", "批量续期全部", "返回"
    ])
    if choice == "清理签发失败的残留文件":
        leftovers = certs.list_failed_leftovers()
        if not leftovers:
            ui.success("没有发现签发失败的残留文件")
            _wait()
            return
        ui.info(f"发现 {len(leftovers)} 个残留目录：")
        for item in leftovers:
            console.print(f"[dim]  - {item['name']}[/dim]")
        if ui.confirm("确认删除以上残留文件？", default=False):
            ok, total = certs.cleanup_leftovers([i["name"] for i in leftovers])
            (ui.success if ok == total else ui.failure)(f"已清理 {ok}/{total} 个")
        _wait()
        return
    if choice == "重新申请证书":
        ui.info("重新申请请先选择域名，流程与首次申请一致")
        apply_flow()
        return
    if choice == "删除全部证书":
        cert_list = acme.list_certs()
        if not cert_list:
            ui.failure("没有可删除的证书")
            return
        ui.failure(f"即将删除全部 {len(cert_list)} 张证书，此操作不可撤销！")
        if ui.confirm("确认删除所有证书？", default=False):
            rm_folder = ui.confirm("是否同时删除本地证书文件夹？",
                                    default=config.get_config("delete_folder", "1") == "1")
            if ui.confirm("再次确认：确定要删除以上所有证书？", default=False):
                ok = failed = 0
                for c in cert_list:
                    judge, _msg = certs.delete(c.main_domain, rm_folder)
                    ok += 1 if judge else 0
                    failed += 0 if judge else 1
                ui.success(f"删除完成：成功 {ok} 张，失败 {failed} 张")
        _wait()
        return
    if choice == "批量续期全部":
        ok, total = certs.renew_all()
        ui.success(f"成功续期 {ok}/{total} 张证书")
        return
    if choice in ("续期单张证书", "删除证书"):
        cert_list = acme.list_certs()
        if not cert_list:
            ui.failure("没有可用证书")
            return
        domain = ui.menu("选择证书", [c.main_domain for c in cert_list])
        if choice == "续期单张证书":
            ui.info(f"正在续期 {domain}……")
            ok, msg = certs.renew(domain, force=ui.confirm("强制续期？", default=False))
        else:
            if ui.confirm(f"确认删除 {domain} 的证书？", default=False):
                rm_folder = ui.confirm("是否同时删除本地证书文件夹？",
                                        default=config.get_config("delete_folder", "1") == "1")
                if rm_folder:
                    config.set_config("delete_folder", "1")
                ok, msg = certs.delete(domain, rm_folder)
            else:
                return
        (ui.success if ok else ui.failure)(msg)
        _wait()


def renew_flow() -> None:
    enabled, desc = renew.check_enabled()
    ui.info(f"自动续期状态：{desc}")
    choice = ui.menu("自动续期设置", ["开启自动续期", "关闭自动续期", "查看定时任务", "返回"])
    if choice == "开启自动续期":
        ok, msg = renew.enable()
        (ui.success if ok else ui.failure)(msg)
    elif choice == "关闭自动续期":
        ok, msg = renew.disable()
        (ui.success if ok else ui.failure)(msg)
    elif choice == "查看定时任务":
        ui.info(renew.show_schedule())
    _wait()


def deploy_flow() -> None:
    cert_list = acme.list_certs()
    if not cert_list:
        ui.failure("请先申请证书")
        return
    domain = ui.menu("选择要部署的证书", [c.main_domain for c in cert_list])
    service = ui.menu("选择目标服务", ["Caddy", "Nginx", "Apache", "Docker"])
    std = {"Nginx": "nginx", "Apache": "apache", "Caddy": "caddy", "Docker": "nginx"}[service]
    if service == "Docker":
        ui.info("Docker 环境请使用自定义路径挂载证书卷")
        custom = ui.confirm("是否自定义证书保存路径？", default=True)
    else:
        custom = ui.confirm("是否自定义证书保存路径？", default=False)
    if custom:
        cert_path = ui.text_input("证书(cert)保存路径", default=f"/etc/ssl/certs/{domain}.cer")
        key_path = ui.text_input("私钥(key)保存路径", default=f"/etc/ssl/private/{domain}.key")
        ca_path = ui.text_input("CA(ca)保存路径", default=f"/etc/ssl/certs/{domain}-ca.cer")
    else:
        cert_path, key_path, ca_path = f"/etc/certs/{domain}/fullchain.cer", f"/etc/certs/{domain}/key.pem", f"/etc/certs/{domain}/ca.crt"

    reload_choice = ui.confirm("部署后执行服务重载使证书生效？", default=True)
    target = deploy.DeployTarget(cert=cert_path, key_path=key_path, ca_path=ca_path,
                                 service=std, reload=reload_choice)
    if reload_choice:
        target.reload_command = ui.text_input("自定义重载命令（留空自动识别）", "")

    result = deploy.deploy_cert(domain, target, reload=reload_choice)
    (ui.success if result.ok else ui.failure)(result.message)
    for s in result.steps:
        console.print(f"[dim]  - {s}[/dim]")


def _wait() -> None:
    input("\n按下 [回车] 继续……")


def _require_root(action: str) -> bool:
    """检查当前是否为 root，否则提示并返回 False。"""
    import os as _os
    if _os.name == "posix" and _os.geteuid() == 0:
        return True
    ui.failure(f"「{action}」必须使用 root 权限！")
    ui.info("请退出后用 sudo 运行：sudo bash install.sh")
    ui.info("或在已安装环境下：sudo python3 -m acme_easy_manager")
    return False


def uninstall_program() -> None:
    """卸载本程序：删除配置/日志，生成卸载脚本提示，退出。"""
    import shutil
    from pathlib import Path

    ui.info("正在清理配置与日志目录 ...")
    for p in (config.BASE_DIR,):
        if p.exists():
            try:
                shutil.rmtree(p)
                ui.success(f"已删除配置目录: {p}")
            except OSError as e:
                ui.failure(f"删除配置目录失败: {e}")

    ui.info("程序文件请使用项目目录下的卸载脚本删除：")
    ui.info("    chmod +x uninstall.sh && ./uninstall.sh")
    ui.failure("程序即将退出。")
    raise SystemExit(0)


def main() -> int:
    config.ensure_dirs()  # 先确定可写数据目录（含回退），再初始化日志
    setup_logging()
    ui.banner()
    if not require_ready():
        ui.info("环境准备未完成，程序退出")
        return 1
    while True:
        try:
            if not main_menu():
                break
        except KeyboardInterrupt:
            ui.info("已中断")
            break
        except Exception as e:  # noqa: BLE001
            get_logger().exception("未捕获异常")
            ui.failure(f"发生内部错误：{e}")
            _wait()
    console.print("[bold green]再见，感谢使用 Acme Easy Manager！[/bold green]")
    return 0