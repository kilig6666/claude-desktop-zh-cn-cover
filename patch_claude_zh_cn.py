#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-click zh-CN patcher for Claude Desktop on macOS and Windows.

What it does:
1. Locates the installed Claude Desktop app for the current platform.
2. Adds zh-CN to Claude Desktop's language whitelist.
3. Installs Chinese desktop-shell and frontend i18n resources.
4. Sets the current user's Claude config locale to zh-CN.
5. Backs up the original app and installs the patched copy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

LANG_CODE = "zh-CN"
ROOT = Path(__file__).resolve().parent
RESOURCES = ROOT / "resources"
PATCHER_CONFIG = ROOT / "patcher.config.json"
PATCHER_CONFIG_EXAMPLE = ROOT / "patcher.config.example.json"
APP_DEFAULT_MACOS = Path("/Applications/Claude.app")
KNOWN_DESKTOP_JSONS = ("en-US.json", "it-IT.json", "ja-JP.json", "ko-KR.json", "fr-FR.json")

FRONTEND_TRANSLATION = RESOURCES / "frontend-zh-CN.json"
DESKTOP_TRANSLATION = RESOURCES / "desktop-zh-CN.json"
LOCALIZABLE_STRINGS = RESOURCES / "Localizable.strings"

LANG_LIST_RE = re.compile(
    r'\["en-US","de-DE","fr-FR","ko-KR","ja-JP","es-419","es-ES","it-IT","hi-IN","pt-BR","id-ID"(.*?)\]'
)


def is_windows() -> bool:
    return os.name == "nt"


def is_macos() -> bool:
    return sys.platform == "darwin"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")


def load_patcher_config() -> dict[str, Any]:
    if not PATCHER_CONFIG.exists():
        return {}
    data = load_json(PATCHER_CONFIG)
    if not isinstance(data, dict):
        raise SystemExit(f"{PATCHER_CONFIG} must contain a JSON object.")
    return data


def config_section(config: dict[str, Any]) -> dict[str, Any]:
    key = "windows" if is_windows() else "macos"
    section = config.get(key)
    return section if isinstance(section, dict) else {}


def normalize_windows_app_path(path: Path) -> Path:
    path = Path(os.path.expandvars(str(path.expanduser())))
    if path.is_file() and path.name.lower() == "claude.exe":
        return path.parent
    if path.is_dir() and path.name.lower() == "resources" and (path.parent / "Claude.exe").exists():
        return path.parent
    return path


def normalize_app_path(path: Path) -> Path:
    return normalize_windows_app_path(path) if is_windows() else path.expanduser()


def is_windows_claude_dir(path: Path) -> bool:
    path = normalize_windows_app_path(path)
    return path.is_dir() and (path / "Claude.exe").exists() and (path / "resources").exists()


def is_valid_app_path(path: Path) -> bool:
    if is_windows():
        return is_windows_claude_dir(path)
    return path.exists() and path.is_dir() and path.name.endswith(".app")


def default_windows_user_home(user_home: Path) -> Path:
    return Path(os.environ.get("USERPROFILE") or user_home)


def default_windows_app_path(user_home: Path) -> Path:
    return Path(
        os.environ.get("LOCALAPPDATA") or (default_windows_user_home(user_home) / "AppData/Local")) / "Programs/Claude"


def build_config_template(user_home: Path) -> dict[str, Any]:
    windows_home = default_windows_user_home(user_home)
    if is_macos():
        macos_home = user_home
    else:
        macos_home = Path("/Users/<you>")
    return {
        "windows": {
            "app_path": str(default_windows_app_path(user_home)),
            "user_home": str(windows_home),
        },
        "macos": {
            "app_path": str(APP_DEFAULT_MACOS),
            "user_home": str(macos_home),
        },
    }


def ensure_patcher_config_template(user_home: Path) -> Path | None:
    if PATCHER_CONFIG.exists():
        return None
    save_json(PATCHER_CONFIG, build_config_template(user_home))
    print(f"Generated config template: {PATCHER_CONFIG}")
    return PATCHER_CONFIG


def read_registry_string(key: Any, name: str) -> str:
    try:
        import winreg
    except ImportError:
        return ""

    try:
        value, _ = winreg.QueryValueEx(key, name)
    except Exception:
        return ""
    return str(value).strip()


def find_windows_app_from_registry() -> Path | None:
    if not is_windows():
        return None

    try:
        import winreg
    except ImportError:
        return None

    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, root in roots:
        try:
            with winreg.OpenKey(hive, root) as uninstall_root:
                subkey_count = winreg.QueryInfoKey(uninstall_root)[0]
                for index in range(subkey_count):
                    try:
                        name = winreg.EnumKey(uninstall_root, index)
                        with winreg.OpenKey(uninstall_root, name) as entry:
                            display_name = read_registry_string(entry, "DisplayName")
                            if "claude" not in display_name.lower():
                                continue
                            for value_name in ("InstallLocation", "DisplayIcon", "InstallSource"):
                                raw = read_registry_string(entry, value_name)
                                if not raw:
                                    continue
                                candidate = normalize_windows_app_path(Path(raw.split(",", 1)[0].strip().strip('"')))
                                if is_windows_claude_dir(candidate):
                                    return candidate
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def iter_windows_program_roots(user_home: Path) -> list[Path]:
    local_app_data = Path(os.environ.get("LOCALAPPDATA") or (user_home / "AppData/Local"))
    roots = [
        local_app_data / "Programs",
        Path(os.environ.get("ProgramFiles", "")),
        Path(os.environ.get("ProgramFiles(x86)", "")),
    ]
    return [root for root in roots if str(root) and root.exists()]


def find_windows_app_by_scan(user_home: Path) -> Path | None:
    local_app_data = Path(os.environ.get("LOCALAPPDATA") or (user_home / "AppData/Local"))
    exact = [
        local_app_data / "Programs/Claude",
        local_app_data / "Programs/Claude Desktop",
    ]
    for candidate in exact:
        if is_windows_claude_dir(candidate):
            return candidate

    for root in iter_windows_program_roots(user_home):
        for pattern in ("Claude", "Claude*", "*Claude*"):
            for candidate in sorted(root.glob(pattern)):
                if is_windows_claude_dir(candidate):
                    return candidate
    return None


def resolve_user_home(explicit_user_home: Path | None, config: dict[str, Any]) -> Path:
    if explicit_user_home:
        return explicit_user_home.expanduser()
    configured = config_section(config).get("user_home")
    if configured:
        return Path(str(configured)).expanduser()
    return Path.home()


def resolve_app_path(explicit_app: Path | None, user_home: Path, config: dict[str, Any]) -> Path:
    if explicit_app:
        candidate = normalize_app_path(explicit_app)
        if not is_valid_app_path(candidate):
            raise SystemExit(f"Claude app not found or unsupported layout: {candidate}")
        print(f"Using Claude app from --app: {candidate}")
        return candidate

    if is_macos():
        configured = config_section(config).get("app_path")
        candidate = normalize_app_path(Path(str(configured)).expanduser()) if configured else APP_DEFAULT_MACOS
        print(f"Using Claude app: {candidate}")
        return candidate

    scanned = find_windows_app_by_scan(user_home)
    if scanned:
        print(f"Using Claude app from common Windows install path: {scanned}")
        return scanned

    registry_path = find_windows_app_from_registry()
    if registry_path:
        print(f"Using Claude app from Windows registry: {registry_path}")
        return registry_path

    configured = config_section(config).get("app_path")
    if configured:
        candidate = normalize_app_path(Path(str(configured)))
        if is_valid_app_path(candidate):
            print(f"Using Claude app from {PATCHER_CONFIG.name}: {candidate}")
            return candidate
        raise SystemExit(f"Configured Windows app_path is invalid: {candidate}")

    generated = ensure_patcher_config_template(user_home)
    extra = f" A template has been written to {generated}." if generated else ""
    raise SystemExit(
        "Could not locate Windows Claude automatically. "
        f"Pass --app, or edit {PATCHER_CONFIG.name} and set windows.app_path.{extra}"
    )


def iter_resource_roots(app: Path) -> list[Path]:
    if is_macos():
        return [app / "Contents/Resources"]
    return [
        app / "resources",
        app / "resources/app.asar.unpacked",
        app / "resources/app.asar.unpacked/resources",
    ]


def find_frontend_root(app: Path) -> Path:
    for root in iter_resource_roots(app):
        if (root / "ion-dist/i18n/en-US.json").exists():
            return root
    for root in iter_resource_roots(app):
        if (root / "ion-dist").exists():
            return root
    for path in app.rglob("en-US.json"):
        if path.parent.name == "i18n" and path.parent.parent.name == "ion-dist":
            return path.parent.parent.parent
    raise SystemExit(f"Cannot find frontend ion-dist directory in {app}")


def frontend_i18n_dir(app: Path) -> Path:
    return find_frontend_root(app) / "ion-dist/i18n"


def frontend_assets_dir(app: Path) -> Path:
    return find_frontend_root(app) / "ion-dist/assets/v1"


def desktop_resources_dir(app: Path) -> Path:
    for root in iter_resource_roots(app):
        if any((root / name).exists() for name in KNOWN_DESKTOP_JSONS):
            return root
    return iter_resource_roots(app)[0]


def quit_claude() -> None:
    if is_windows():
        run(["taskkill", "/IM", "Claude.exe", "/T", "/F"], check=False)
        return
    run(["osascript", "-e", 'tell application "Claude" to quit'], check=False)


def launch_claude(app: Path) -> None:
    if is_windows():
        exe = app / "Claude.exe"
        if exe.exists():
            subprocess.Popen([str(exe)], cwd=str(app))
        return
    run(["open", "-a", str(app)], check=False)


def copy_app(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    print(f"Copying app to temporary workspace: {dst}")
    if is_macos():
        run(["ditto", str(src), str(dst)])
    else:
        shutil.copytree(src, dst)


def patch_language_whitelist(app: Path) -> Path:
    assets_dir = frontend_assets_dir(app)
    candidates = sorted(assets_dir.glob("index-*.js"))
    if not candidates:
        raise SystemExit(f"Cannot find frontend index bundle in {assets_dir}")

    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if '"zh-CN"' in text:
            print(f"Language whitelist already contains zh-CN: {path.name}")
            return path
        if LANG_LIST_RE.search(text):
            patched = LANG_LIST_RE.sub(
                '["en-US","de-DE","fr-FR","ko-KR","ja-JP","es-419","es-ES","it-IT","hi-IN","pt-BR","id-ID","zh-CN"]',
                text,
                count=1,
            )
            path.write_text(patched, encoding="utf-8")
            print(f"Patched language whitelist: {path.name}")
            return path

    raise SystemExit("Could not patch language whitelist. Claude's bundle format may have changed.")


def patch_hardcoded_frontend_strings(app: Path) -> None:
    assets_dir = frontend_assets_dir(app)
    replacements = {
        '"Sent on every inference and `/v1/models` discovery request (joined into the CLI\'s `ANTHROPIC_CUSTOM_HEADERS`).\\n\\nUse this for fleet-wide constants. For per-user or per-session values, have the **credential helper script** emit JSON with a `headers` field — those are merged over these static entries (helper wins on conflict)."': '"每次推理和 `/v1/models` 发现请求都会发送此信息（已添加到 CLI 的 `ANTHROPIC_CUSTOM_HEADERS` 中）。\\n\\n此信息用于全局常量。对于每个用户或每个会话的值，请让**凭证辅助脚本**生成带有 `headers` 字段的 JSON——这些值会与这些静态条目合并（冲突时以辅助脚本的值为准）。"',

        '\'Claude runs the executable with no arguments and reads **stdout** (trimmed). Exit code must be `0`; any output on **stderr** is logged but ignored. **Stdout must be the credential only** — no banners, prompts, or log lines.\\n\\n**Output format** — either:\\n- a single bare token (the API key / bearer token), or\\n- a JSON object `{"token": "...", "headers": {"Name": "Value", ...}}` when per-request headers are needed (gateway provider only; merged over **Gateway extra headers**, helper wins on conflict)\\n\\nResult is cached for the TTL below. On TTL expiry the helper is re-invoked transparently — no user prompt, no relaunch.\\n\\n**Typical use:** a shell script that pulls from Keychain, 1Password CLI, or an internal secret broker. Example:\\n\\n`security find-generic-password -s anthropic-api -w`\\n\\nIf this field is set, static credential fields (API key, bearer token) are ignored. The helper always wins.\'': '\'Claude 运行该可执行文件时不带任何参数，并读取 **stdout**（已精简）。退出代码必须为 `0`；**stderr** 上的任何输出都会被记录但会被忽略。**stdout 必须仅包含凭据**——不包含横幅、提示或日志行。\\n\\n**输出格式**——可以是：\\n- 单个裸令牌（API 密钥/持有者令牌），或者\\n- 当需要每个请求的标头时，可以使用 JSON 对象 `{"token": "...", "headers": {"Name": "Value", ...}}`（仅限网关提供商；会与 **网关额外标头** 合并，冲突时辅助程序优先）\\n\\n结果会缓存以下 TTL 值。TTL 到期后，辅助程序会透明地重新调用——无需用户提示，也无需重新启动。\\n\\n**典型用途：** 从 Keychain、1Password CLI 或内部密钥代理拉取凭据的 shell 脚本。示例：\\n\\n`security find-generic-password -s anthropic-api -w`\\n\\n如果设置了此字段，则会忽略静态凭据字段（API 密钥、持有者令牌）。辅助方法始终优先。\'',

        '"Only affects **tool calls** — inference and MCP traffic are covered by their own allowlists elsewhere.\\n\\nAccepts exact hostnames (`api.github.com`), wildcards (`*.corp.com` matches one subdomain level), and `*` to allow all.\\n\\nWildcards don\'t cross schemes. `*.corp.com` matches `docs.corp.com` but not `corp.com` itself — add both if you need the apex.\\n\\nIP literals and localhost always resolve regardless of this list; this is a public-egress filter, not a sandbox.\\n\\nHosts you add here also need to be open on your network firewall — see **Egress Requirements** for the full allowlist."': '"仅影响**工具调用**——推理和 MCP 流量由它们各自的允许列表在其他地方进行管理。\\n\\n接受精确主机名（例如 `api.github.com`）、通配符（例如 `*.corp.com` 匹配一个子域名级别）以及 `*` 以允许所有访问。\\n\\n通配符不会跨协议。`*.corp.com` 匹配 `docs.corp.com`，但不匹配 `corp.com` 本身——如果需要根域名，请同时添加两者。\\n\\nIP 地址和 localhost 始终解析，不受此列表的影响；这是一个公共出口过滤器，而不是沙箱。\\n\\n您在此处添加的主机还需要在您的网络防火墙上开放——有关完整的允许列表，请参阅**出口要求**。"',

        '{body:"\\"Essential\\" means the signals Anthropic needs to keep your deployment working: **crash stacks**, **startup failure reasons**, and **version/OS metadata**. No prompts, completions, file contents, or identifiers beyond a random install ID.\\n\\n**What you lose when this is on:** when a Cowork build hits a bug that only reproduces on your OS version or locale, Anthropic can\'t see it unless a user manually reports. Fixes ship slower.\\n\\n**Why this is discouraged, not blocked:** some air-gapped environments require zero outbound telemetry as a matter of policy. The switch exists for them — if you don\'t have that constraint, leave it off."': '{body:"\\"必要\\"指的是 Anthropic 维持部署正常运行所需的信号：**崩溃堆栈**、**启动失败原因**和**版本/操作系统元数据**。除了随机安装 ID 之外，不会收集任何提示、补全信息、文件内容或标识符。\\n\\n**启用此功能后会丢失什么：**当 Cowork 构建遇到仅在您的操作系统版本或语言环境中才会出现的错误时，除非用户手动报告，否则 Anthropic 将无法检测到该错误。修复程序的发布速度会变慢。\\n\\n**不建议启用此功能，但并非完全禁用：**某些物理隔离环境出于策略考虑，要求完全禁止对外传输遥测数据。您可以为此启用此功能——如果您没有此类限制，请将其关闭。"',

        'help:{body:\'"Nonessential" covers two things: **product-usage analytics** (which features get used, navigation patterns — no prompts or completions) and the **Send** action in Help → Generate Diagnostic Report. Turning this on stops both.\\n\\nDestination for both: `claude.ai`. Already listed under Egress Requirements → Nonessential telemetry.\'': 'help:{body:\'"非必要"涵盖两项内容：**产品使用情况分析**（哪些功能被使用、导航模式——不包括提示或自动完成）以及"帮助"→"生成诊断报告"中的**发送**操作。启用此选项将停止这两项操作。\\n\\n两者的目标地址均为：`claude.ai`。已列于"出口要求"→"非必要遥测"下。\'',


        '"Desktop extensions (Python runtime)"': '"桌面扩展（Python 运行时）"',
        '"Auto-updates"': '"自动更新"',
        '"Core (VM bundle + Claude CLI binary)"': '"核心（VM 包 + Claude CLI 二进制文件）"',
        '"Per-user soft cap, counted client-side over the duration below. Not a server-enforced quota."': '"每个用户的软上限，在以下时间段内由客户端计算。并非服务器强制执行的配额。"',
        '"Max tokens per window"': '"每个窗口的最大令牌数"',
        'title:"Usage limits"': 'title:"使用限制"',
        '"This disables artifact previews and connector icons. Artifacts will not render in conversations."': '""',
        '"Block nonessential services"': '"这将禁用工件预览和连接器图标。工件将不会在对话中显示。"',
        '"Usage analytics help us prioritize improvements for third-party inference. Diagnostic-report uploads will also be blocked. No message content is included in either."': '"使用情况分析有助于我们优先改进第三方推理功能。诊断报告上传也将被阻止。以上两项措施均不包含任何消息内容。"',
        '"Block nonessential telemetry"': '"阻止非必要的遥测"',
        '"Crash and error reports are how we diagnose failures specific to your inference setup. Support turnaround will be slower without them."': '"崩溃和错误报告是我们诊断特定推理设置故障的关键。如果没有这些报告，支持响应速度将会变慢。"',
        '"Block essential telemetry"': '"阻止必要的遥测"',
        '"Anthropic telemetry"': '"Anthropic 遥测"',
        '"Hours before a downloaded update force-installs. Blank = 72-hour default."': '"下载的更新会在几小时内强制安装。空白处表示默认的 72 小时。"',
        ',suffix:"hours",': ',suffix:"小时",',
        '"Auto-update enforcement window"': '"自动更新强制窗口"',
        '"Stop Cowork from fetching updates. You\'ll need to push new versions yourself."': '"停止 Cowork 获取更新。您需要自行推送新版本。"',
        '"Block auto-updates"': '"阻止自动更新"',
        ',group:"Updates"': ',group:"更新"',
        '"Extra resource attributes to attach to every span/metric, e.g. enduser.id=alice@example.com."': '"附加到每个 span/metric 的额外资源属性，例如 enduser.id=alice@example.com。"',
        '"OpenTelemetry resource attributes"': '"OpenTelemetry 资源属性"',
        '"Optional auth headers for the collector."': '"收集器的可选身份验证标头。"',
        '"OpenTelemetry exporter headers"': '"OpenTelemetry导出器头"',
        '"grpc or http/protobuf."': '"grpc 或 http/protobuf。"',
        '"OpenTelemetry exporter protocol"': '"OpenTelemetry导出器协议"',
        '"Where Cowork sends OpenTelemetry logs and metrics. Leave blank to disable."': '"Cowork 会将 OpenTelemetry 日志和指标发送到此处。留空则禁用此功能。"',
        '"OpenTelemetry collector endpoint"': '"OpenTelemetry 收集器端点"',
        '"OpenTelemetry"': '"开放遥测"',
        '"Prompts, completions, and your data are never sent to Anthropic — telemetry covers crash and usage signals only."': '"提示、完成情况和您的数据永远不会发送给 Anthropic——遥测数据仅涵盖崩溃和使用情况信号。"',
        '"Reject desktop extensions that are not signed by a trusted publisher."': '"拒绝安装未经可信发布者签名的桌面扩展程序。"',
        '"Require signed extensions"': '"需要签署的扩展"',
        '"The in-app catalogue of installable extensions. Hide to allow sideload only."': '"应用内可安装扩展程序目录。隐藏后仅允许侧载。"',
        '"Show extension directory"': '"显示扩展目录"',
        '".dxt and .mcpb installs."': '".dxt 和 .mcpb 安装。"',
        '"Allow desktop extensions"': '"允许桌面扩展"',
        ',group:"Extensions"': ',group:"扩展"',
        '"Local stdio servers added via the Developer settings. Remote servers come from the managed list above, or plugins mounted to a user\'s computer by an organization admin."': '"本地 stdio 服务器通过开发者设置添加。远程服务器来自上述托管列表，或由组织管理员挂载到用户计算机上的插件。"',
        '"Allow user-added MCP servers"': '"允许用户添加的 MCP 服务器"',
        '"Org-pushed remote MCP servers. May embed bearer tokens."': '"组织推送的远程 MCP 服务器。可能嵌入持有者令牌。"',
        '"Managed MCP servers"': '"托管 MCP 服务器"',
        '"MCP servers"': '"MCP 服务器"',
        '"Folders users may attach as a workspace. Leave unset for unrestricted access."': '"用户可将文件夹附加为工作区。如需无限制访问，请勿设置。"',
        '"Allowed workspace folders"': '"允许的工作区文件夹"',
        '"Built-in tools removed from Cowork."': '"Cowork 中已移除内置工具。"',
        '"Disabled built-in tools"': '"已禁用内置工具"',
        '"Domains Cowork\'s tools may reach during a turn. Also surfaced under Egress Requirements."': '"Cowork 的工具在回合期间可能触及的领域。也出现在“出口要求”下。"',
        '"Show the Code tab (terminal-based coding sessions). Sessions run on the host, not inside the VM."': '"显示“代码”选项卡（基于终端的编码会话）。会话在主机上运行，而不是在虚拟机内部运行。"',
        '"Allowed egress hosts"': '"允许的出口主机"',
        '"Allow Claude Code tab"': '"允许 Claude 代码选项卡"',
        '"Go straight to this provider at launch — users won\'t see the option to sign in to Anthropic instead."': '"上线后请直接访问此提供商——用户不会看到登录 Anthropic 的选项。"',
        '"Skip login-mode chooser"': '"跳过登录模式选择器"',

        '"Absolute path to an executable that prints the credential."': '"打印凭据的可执行文件的绝对路径。"',
        '"Credential helper script"': '"凭据辅助脚本"',
        '"Tags telemetry events with your org so support can find them. Not used for auth."': '"使用组织名称标记遥测事件，以便支持人员能够找到它们。不用于身份验证。"',
        '"Organization UUID"': '"组织 UUID"',
        '"Offer 1M-context variant"': '"提供 1M 上下文变体"',
        '"Model ID"': '"模型ID"',
        '"First entry is the picker default. Aliases like sonnet, opus accepted. Optional for gateway — when set, the picker shows exactly this list instead of /v1/models discovery. Turn on 1M context only for models your provider actually serves with the extended window."': '"第一个条目是选择器的默认值。接受 sonnet、opus 等别名。网关可选——启用后，选择器将显示此列表，而不是 /v1/models 发现列表。仅对提供商实际提供的、具有扩展窗口的模型启用 1M 上下文。"',
        '"Model list"': '"模型列表"',
        '"Identity & models"': '"身份与模型"',
        '"Gateway API key"': '"网关 API key"',
        '"Gateway auth scheme"': '"网关认证方案"',
        '"Gateway extra headers"': '"网关额外标头"',
        '"Full URL of the inference gateway endpoint."': '"推理网关端点的完整URL。"',
        ',title:"Gateway base URL"': ',title:"网关URL"',

        '"Extra headers sent to the gateway, one \'Name: Value\' per entry. For tenant routing, org IDs, etc."': '"发送到网关的额外标头，每个条目一个“名称:值”。用于路由、组织 ID 等。"',
        '"Bearer (default) sends Authorization: Bearer. x-api-key is for the Anthropic API directly — auto-selected when the URL is *.anthropic.com."': '"Bearer（默认）发送 Authorization: Bearer。x-api-key 直接用于 Anthropic API — 当 URL 为 *.anthropic.com 时自动选择。"',
        '"Choose where Claude Desktop sends inference requests."':'"选择 Claude Desktop 向何处发送推理请求。"',
        ':{title:"Connection",':':{title:"连接",',
        '{title:"Sandbox & workspace"}':'{title:"沙盒和工作区"}',
        '{title:"Connectors & extensions"}':'{title:"连接器和扩展"}',
        ':{title:"Telemetry & updates",':':{title:"遥测和更新",',
        '{title:"Egress Requirements",':'{title:"出口要求",',
        '{title:"Usage limits"}':'{title:"使用限制"}',
        '{title:"Plugins & skills",':'{title:"插件和技能",',
        'Plugins and skills aren\'t set in this configuration. Mount plugin bundles to the folder below using your device-management tool and Cowork will load them at launch.':'此配置中未设置插件和技能。请使用设备管理工具将插件包挂载到以下文件夹，Cowork 将在启动时加载它们。',
        '"Drop plugin folders here. Read-only to the app."':'"将插件文件夹拖放到此处。对应用程序只读。"',
        '"Hosts your network firewall must allow, derived from your current settings. This list is read-only and updates as you make changes. Traffic is HTTPS on port 443 unless a custom port is specified (OTLP, gateway, or MCP server URLs)."':'"此列表包含您的网络防火墙必须允许的主机，其值取决于您当前的设置。此列表为只读，会随着您的更改而更新。除非指定自定义端口（例如 OTLP、网关或 MCP 服务器 URL），否则流量将通过 443 端口上的 HTTPS 协议传输。"',
        'l="Free space",i="Autocompact buffer"': 'l="剩余空间",i="自动压缩缓冲区"',
        'e.length?"All"': 'e.length?"全部"',
        ',["0","All"]]': ',["0","全部"]]',
        ',jl="Local",Cl="Cloud",Ml="Remote Control",Il="All"': ',jl="本地",Cl="云端",Ml="远程控制",Il="全部"',
        'children:"All projects"': 'children:"所有项目"',
        '[["active","Active"],["archived","Archived"],["all","All"]]': '[["active","活跃"],["archived","已存档"],["all","全部"]]',
        '[["date","Date"]': '[["date","日期"]',
        '[["state","State"]]': '[["state","状态"]]',
        '["none","None"]]': '["none","无"]]',
        '[["project","Project"]]': '[["project","项目"]]',
        '[["environment","Environment"]]': '[["environment","环境"]]',
        'label:"Sort by",': 'label:"排序方式",',
        '[["alpha","Alphabetically"],["created","Created time"],["recency","Recency"]]': '[["alpha","按字母顺序"],["created","按创建时间"],["recency","按最近使用"]]',
        '{title:"Projects",': '{title:"项目",',
        'Je="New project",': 'Je="新建项目",',
        ',placeholder:"Search projects"}': ',placeholder:"搜索项目"}',
        ',as={recent:"Recent",created:"Created",alphabetical:"Alphabetical"}': ',as={recent:"按最近使用",created:"按创建时间",alphabetical:"按字母顺序"}',
        ',children:"Clear filters"': ',children:"清除筛选"',
        ',tooltip:"Search",tooltipKeyboardShortcut': ',tooltip:"搜索",tooltipKeyboardShortcut',
        ',tooltip:"Collapse sidebar"': ',tooltip:"折叠侧边栏"',
        'label:"Environment",': 'label:"环境",',
        'label:"Last activity",': 'label:"最后活动",',
        ',children:"Project"': ',children:"项目"',
        'label:"Group by",': 'label:"按组",',
        'label:"Status",': 'label:"状态",',
        ',children:"New task"': ',children:"新建任务"',
        ',placeholder:"Filter scheduled tasks"}': ',placeholder:"筛选计划任务"}',
        'const wpn={nextRun:"Next run",name:"Name"}': 'const wpn={nextRun:"按下次运行",name:"按名称"}',
        ',label:"New session"': ',label:"新建会话"',
        ',message:"Scheduled tasks only run while your computer is awake.",': ',message:"计划任务仅在计算机处于唤醒状态时运行。",',
        '}),"No scheduled tasks yet."]}': '}),"尚无计划任务。"]}',
        ',children:"Run tasks on a schedule or whenever you need them. Type /schedule in any existing task to set one up."}': ',children:"按计划或在需要时运行任务。在任何现有任务中键入 /schedule 来设置一项。"}',
        ',{title:"Scheduled tasks",': ',{title:"计划任务",',
        'const Ll={chat:"New chat",cowork:"New task",code:"New session",operon:"New session"}': 'const Ll={chat:"新建对话",cowork:"新建任务",code:"新建会话",operon:"新建会话"}',
        ',children:"Pinned"': ',children:"已置顶"',
        'const Fl="Recents"': 'const Fl="最近使用"',
        ',label:"Projects"': ',label:"项目"',
        ',label:"Scheduled"': ',label:"计划任务"',
        ',label:"Customize"': ',label:"自定义"',
        ',name:"Customize"': ',name:"自定义"',
        '"Drag to pin"': '"拖到此处固定"',
        '"Drop here"': '"拖到此处"',
        '"Let go"': '"松开"',
    }
    patched_files = 0
    patched_strings = 0

    for path in sorted(assets_dir.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        patched = text
        count = 0
        for source, target in replacements.items():
            occurrences = patched.count(source)
            if occurrences:
                patched = patched.replace(source, target)
                count += occurrences
        if patched != text:
            path.write_text(patched, encoding="utf-8")
            patched_files += 1
            patched_strings += count

    print(f"Patched hardcoded frontend strings: {patched_strings} replacements in {patched_files} files")


def merge_frontend_locale(app: Path) -> tuple[int, int, int]:
    i18n_dir = frontend_i18n_dir(app)
    source = i18n_dir / "en-US.json"
    target = i18n_dir / "zh-CN.json"
    require_file(source)
    require_file(FRONTEND_TRANSLATION)

    en = load_json(source)
    zh_pack = load_json(FRONTEND_TRANSLATION)
    if not isinstance(en, dict) or not isinstance(zh_pack, dict):
        raise SystemExit("Unsupported frontend i18n JSON shape.")

    merged: dict[str, Any] = {}
    translated = 0
    fallback = 0
    for key, value in en.items():
        if key in zh_pack:
            merged[key] = zh_pack[key]
            if zh_pack[key] != value:
                translated += 1
        else:
            merged[key] = value
            fallback += 1

    save_json(target, merged)
    extra = len(set(zh_pack) - set(en))
    print(f"Installed frontend zh-CN: {translated} translated, {fallback} fallback, {extra} extra old keys ignored")
    return translated, fallback, extra


def install_desktop_locale(app: Path) -> None:
    resources_dir = desktop_resources_dir(app)
    require_file(DESKTOP_TRANSLATION)

    shutil.copy2(DESKTOP_TRANSLATION, resources_dir / "zh-CN.json")
    if is_macos():
        require_file(LOCALIZABLE_STRINGS)
        for folder in ["zh-CN.lproj", "zh_CN.lproj"]:
            out_dir = resources_dir / folder
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(LOCALIZABLE_STRINGS, out_dir / "Localizable.strings")
    print("Installed desktop shell zh-CN resources")


def install_statsig_locale(app: Path) -> None:
    statsig_dir = frontend_i18n_dir(app) / "statsig"
    if not statsig_dir.exists():
        return
    target = statsig_dir / "zh-CN.json"
    bundled = RESOURCES / "statsig-zh-CN.json"
    if bundled.exists():
        shutil.copy2(bundled, target)
    elif (statsig_dir / "en-US.json").exists():
        shutil.copy2(statsig_dir / "en-US.json", target)
    print("Installed statsig zh-CN resource")


def iter_user_config_paths(user_home: Path) -> list[Path]:
    if is_windows():
        appdata = Path(os.environ.get("APPDATA") or (user_home / "AppData/Roaming"))
        return [
            appdata / "Claude/config.json",
            appdata / "Claude-3p/config.json",
        ]
    support_dir = user_home / "Library/Application Support"
    return [
        support_dir / "Claude/config.json",
        support_dir / "Claude-3p/config.json",
    ]


def set_user_locale(user_home: Path) -> None:
    targets = [path for path in iter_user_config_paths(user_home) if path.exists()]
    if not targets:
        targets = [iter_user_config_paths(user_home)[0]]

    for config in targets:
        data: dict[str, Any] = {}
        if config.exists():
            try:
                data = load_json(config)
            except Exception:
                backup = config.with_suffix(config.suffix + ".bak-invalid")
                shutil.copy2(config, backup)
                print(f"Existing config was not valid JSON; backed up to {backup}")
        data["locale"] = LANG_CODE
        save_json(config, data)

        if is_macos():
            sudo_uid = os.environ.get("SUDO_UID")
            sudo_gid = os.environ.get("SUDO_GID")
            if sudo_uid and sudo_gid:
                os.chown(config, int(sudo_uid), int(sudo_gid))
        print(f"Set Claude config locale: {config}")


def build_backup_path(original: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if original.name.endswith(".app"):
        backup_name = f"{original.stem}.backup-before-zh-CN-{stamp}.app"
    else:
        backup_name = f"{original.name}.backup-before-zh-CN-{stamp}"
    return original.with_name(backup_name)


def backup_and_replace(original: Path, patched: Path, dry_run: bool) -> Path:
    backup = build_backup_path(original)
    if dry_run:
        print(f"[dry-run] Would move {original} -> {backup}")
        print(f"[dry-run] Would move {patched} -> {original}")
        return backup

    print(f"Backing up current app: {backup}")
    shutil.move(str(original), str(backup))
    print(f"Installing patched app: {original}")
    shutil.move(str(patched), str(original))
    return backup


def verify(app: Path) -> None:
    frontend = frontend_i18n_dir(app) / "zh-CN.json"
    data = load_json(frontend)
    values = [v for v in data.values() if isinstance(v, str)]
    chinese = sum(1 for v in values if re.search(r"[\u4e00-\u9fff]", v))
    print(f"Verified frontend zh-CN JSON: {chinese}/{len(values)} strings contain Chinese")

    if not is_macos():
        require_file(desktop_resources_dir(app) / "zh-CN.json")
        print("Verified Windows desktop shell zh-CN resource")
        return

    verify_result = run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)], check=False)
    if verify_result.returncode != 0:
        print("Patched app no longer matches Claude's original signature; re-signing the app for local launch.")
        print(verify_result.stdout.rstrip())
        entitlements_raw = subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", str(app)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        ).stdout.strip()
        if not entitlements_raw:
            raise SystemExit("Could not extract Claude entitlements before re-signing.")
        entitlements = plistlib.loads(entitlements_raw)
        entitlements["com.apple.security.cs.disable-library-validation"] = True
        entitlements_path = app.parent / "adhoc-entitlements.plist"
        entitlements_path.write_bytes(plistlib.dumps(entitlements))
        resign_result = run(
            [
                "codesign",
                "--force",
                "--deep",
                "--sign",
                "-",
                "--options",
                "runtime",
                "--entitlements",
                str(entitlements_path),
                str(app),
            ],
            check=False,
        )
        if resign_result.returncode != 0:
            raise SystemExit(f"codesign failed after patching:\n{resign_result.stdout}")
        verify_result = run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)], check=False)
        if verify_result.returncode != 0:
            raise SystemExit(f"Patched app still failed codesign verification:\n{verify_result.stdout}")
        print("Applied deep ad-hoc signature with local-launch entitlements")

    quarantine_result = run(["xattr", "-dr", "com.apple.quarantine", str(app)], check=False)
    if quarantine_result.returncode == 0:
        print("Cleared com.apple.quarantine from patched app")

    result = run(["codesign", "-dv", str(app)], check=False).stdout
    for line in result.splitlines():
        if line.startswith("TeamIdentifier="):
            print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch Claude Desktop with zh-CN language resources.")
    parser.add_argument("--app", type=Path,
                        help="Path to Claude.app on macOS, or Claude install directory / Claude.exe on Windows")
    parser.add_argument("--user-home", type=Path, help="Home directory whose Claude config should be updated")
    parser.add_argument("--dry-run", action="store_true",
                        help="Prepare and verify a patched temp app, but do not replace the installed Claude")
    parser.add_argument("--launch", action="store_true", help="Launch Claude after installation")
    args = parser.parse_args()

    require_file(FRONTEND_TRANSLATION)
    require_file(DESKTOP_TRANSLATION)
    if is_macos():
        require_file(LOCALIZABLE_STRINGS)

    config = load_patcher_config()
    user_home = resolve_user_home(args.user_home, config)
    app = resolve_app_path(args.app, user_home, config)
    if not app.exists():
        raise SystemExit(f"Claude app not found: {app}")

    if is_macos():
        try:
            in_applications = app.resolve().as_posix().startswith("/Applications/")
        except Exception:
            in_applications = str(app).startswith("/Applications/")
        if os.geteuid() != 0 and in_applications:
            print("This usually needs sudo because /Applications is protected.", file=sys.stderr)

    if args.dry_run:
        print("[dry-run] Claude will not be quit.")
    else:
        quit_claude()

    tmp_root = Path(tempfile.mkdtemp(prefix="claude-zh-cn-patch."))
    patched_app = tmp_root / app.name

    copy_app(app, patched_app)
    patch_language_whitelist(patched_app)
    patch_hardcoded_frontend_strings(patched_app)
    merge_frontend_locale(patched_app)
    install_desktop_locale(patched_app)
    install_statsig_locale(patched_app)
    if args.dry_run:
        print(f"[dry-run] Would set Claude config locale under: {user_home}")
    else:
        set_user_locale(user_home)
    verify(patched_app)

    backup = backup_and_replace(app, patched_app, args.dry_run)
    if not args.dry_run:
        print(f"Backup kept at: {backup}")
        if args.launch:
            launch_claude(app)

    print("Done. Select Language -> 中文（中国） in Claude if it is not already selected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
