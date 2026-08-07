# Acme Easy Manager

一个友好的**终端交互式 SSL 证书管理工具**，大幅降低 [acme.sh](https://github.com/acmesh-official/acme.sh) 的使用门槛。无需记忆复杂的命令行参数，通过类似安装向导的交互界面即可完成证书申请、验证、部署与续期管理。

## 功能特性

- **环境自动检测**：检测 Linux 发行版、Shell、curl/wget、OpenSSL 版本及 acme.sh 是否安装；缺少必要组件时提供自动安装。
- **证书申请**：
  - 支持单域名、多域名 SAN、泛域名（`*.example.com`）
  - 自动校验域名格式
  - 多 CA 支持：Let's Encrypt、ZeroSSL、Buypass、Google
  - 密钥方案：ECC P-256 / ECC P-384 / RSA 2048 / RSA 4096
  - DNS 验证方式：填入 API Token 即可，无需手动设置环境变量
- **DNS 服务商**：Cloudflare、阿里云、腾讯云、华为云（模块化设计，易扩展）。
- **证书生命周期管理**：查看列表、显示签发/过期时间、剩余有效天数、手动续期、删除、重新申请。
- **自动续期**：检测并配置 cron / systemd timer 定时任务，可开启、关闭、查看。
- **部署**：自动安装证书到 Nginx / Apache / Caddy / Docker（自定义路径），部署后可自动重载服务。
- **错误处理与日志**：将 acme.sh 原始错误翻译成用户可理解的提示与解决建议；所有记录写入日志文件。
- **安全配置管理**：敏感信息隐藏显示、配置文件权限自动收紧为 `0600`，避免 Token 泄露。

## 安装

### 方式一：便捷脚本（推荐）

```bash
chmod +x install.sh
./install.sh              # 默认：在项目内创建 .venv 虚拟环境（推荐，最干净）
./install.sh --local      # 直接把依赖装到当前文件夹 vendor/ 目录，无需虚拟环境
```

> 三种运行方式，均只影响项目文件夹、不修改系统 Python（可规避 Debian/Ubuntu 的 PEP 668 限制）：
> - `python3 run.py` — 自动创建并使用 `.venv`
> - `python3 run.py --local` — 依赖直接安装到当前文件夹 `vendor/` 并加载
> - `python3 run.py --no-venv` — 使用系统 Python（需已全局安装依赖）

### 方式二：手动

```bash
pip install -r requirements.txt
python -m acme_easy_manager
```

## 卸载

运行卸载脚本可删除程序文件、配置与日志，并可选择同时卸载 acme.sh：

```bash
./uninstall.sh
```

> 卸载过程分步询问：是否卸载 acme.sh、是否删除配置文件（含 DNS Token 等敏感信息）、是否删除程序目录。

## 使用

启动后进入交互式主菜单，按提示即可完成全部操作：

```
─────────────────────────────────────────────
   1. 申请证书（含自动 DNS 验证）
   2. 查看证书列表
   3. 手动续期 / 删除 / 重新申请
   4. 自动续期设置
   5. 部署证书到 Web 服务
   6. 系统环境检测
   7. 退出
─────────────────────────────────────────────
```

### 申请一个证书的典型路径
1. 选择「申请证书」
2. 选择 CA（如 Let's Encrypt）与密钥类型（如 ECC P-256）
3. 输入主域名及可选 SAN/泛域名
4. 选择 DNS 服务商并填入 API Token / AccessKey（敏感信息不回显）
5. 程序自动保存配置并调用 acme.sh 完成 DNS 验证与签发
6. （可选）部署到目标服务并重载

## 配置与安全

- 配置文件默认位于 `~/.config/acme-easy-manager/`
  - `settings.conf`：全局设置（默认 CA、密钥类型、邮箱）
  - `providers/<name>.conf`：各 DNS 服务商认证信息
- 敏感键值写入后权限自动设为 `0600`，目录为 `0700`。
- 日志文件：`<配置目录>/logs/acme-manager.log`

## 项目结构

```
acme_easy_manager/
├── cli.py           # 入口与主菜单流程
├── ui.py            # Rich + Questionary 交互界面
├── system.py        # 环境检测 / acme.sh 安装 / 账户注册
├── config.py        # 配置文件与权限管理
├── logger.py        # 日志系统
├── acme.py          # acme.sh 命令封装与证书解析
├── certs.py         # 证书生命周期管理
├── renew.py         # 自动续期（定时任务）
├── deploy.py        # 证书部署
├── errors.py        # 错误翻译
└── providers/       # DNS 服务商插件
    ├── base.py      # 抽象基类
    ├── cloudflare.py / aliyun.py / tencent.py / huawei.py
```

> 注意：当前为第一阶段 Linux CLI 版本。Web 管理面板、多服务器管理、消息通知、Docker 化部署等高级功能将在后续版本加入。

## 系统要求

- Python 3.8+
- curl 或 wget
- OpenSSL
- Linux / macOS

## 路线图

- [x] acme.sh 安装检测与自动安装
- [x] Let's Encrypt 证书申请（DNS 自动验证）
- [x] Cloudflare / 阿里云 / 腾讯云 / 华为云 DNS API
- [x] ECC / RSA 密钥
- [x] 证书查看 / 续期 / 删除
- [x] 自动续期定时任务
- [x] 基础部署（Nginx / Apache / Caddy / Docker / 自定义）
- [ ] Web 管理面板
- [ ] 多服务器管理
- [ ] 消息通知
- [ ] Docker 化部署