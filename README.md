# Claude Desktop 中文补丁（zh-CN，macOS / Windows）

一个用于 Claude Desktop 的中文界面补丁。

当前支持：

- macOS 版 Claude Desktop
- Windows 版 Claude Desktop

脚本会给 Claude 添加 `中文（中国）` 语言选项，并安装中文界面资源。

## Windows 30 秒快速开始

如果你主要是给 Windows 版 Claude 汉化，直接按这个最短流程走：

1. 安装 Python 3
2. 退出 Claude Desktop
3. 双击 `install_windows.bat`
4. 如果脚本提示“找不到 Claude”，就打开它自动生成的 `patcher.config.json`
5. 把里面的 `windows.app_path` 改成你的 Claude 安装目录
6. 再双击 `install_windows.bat` 跑一次

如果你喜欢 PowerShell，也可以直接执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
```

## 功能特点

- 自动给 Claude 前端语言白名单加入 `zh-CN`
- 自动合并当前 Claude 版本的英文语言文件与随包中文翻译
- 新版本新增但暂未翻译的字段保留英文，避免界面缺失文本
- 安装前自动备份原始 Claude 应用目录
- 自动写入 Claude 用户配置，将语言设置为 `zh-CN`
- Windows 支持自动查找常见安装路径、扫描候选目录、读取注册表
- 自动查找失败时，支持通过 `patcher.config.json` 或 `--app` 手动指定路径

## 适用环境

- Python 3
- 已安装 Claude Desktop
- macOS 或 Windows

## 仓库文件说明

- `patch_claude_zh_cn.py`：真正执行补丁的跨平台 Python 脚本
- `install.command`：macOS 双击运行入口
- `install_windows.bat`：Windows 双击运行入口
- `install_windows.ps1`：Windows PowerShell 运行入口
- `patcher.config.example.json`：路径配置示例
- `resources/frontend-zh-CN.json`：Claude 前端界面中文翻译
- `resources/desktop-zh-CN.json`：Claude 桌面壳层中文翻译
- `resources/Localizable.strings`：macOS 原生菜单中文资源
- `resources/statsig-zh-CN.json`：statsig i18n 兜底资源
- `resources/manifest.json`：语言包信息

## macOS 使用方式

### 方式一：双击运行

1. 退出 Claude Desktop
2. 下载或克隆本项目
3. 双击 `install.command`
4. 按提示输入这台 Mac 的登录密码
5. 安装完成后重新打开 Claude
6. 如果没有自动切换，打开左下角账号菜单，选择 `Language -> 中文（中国）`

### 方式二：终端运行

```bash
cd /path/to/claude-desktop-zh-cn
sudo /usr/bin/python3 patch_claude_zh_cn.py --launch
```

## Windows 使用方式

### 方式一：双击运行（推荐）

1. 退出 Claude Desktop
2. 确保机器已安装 Python 3
3. 双击 `install_windows.bat`
4. 等待脚本自动查找 Claude 并完成补丁
5. Claude 会自动尝试重新打开
6. 如果没有自动切换，打开 Claude 左下角账号菜单，选择 `Language -> 中文（中国）`

说明：

- `install_windows.bat` 会优先尝试：
  - `py -3`
  - `python`
- 两者都找不到时，窗口会停住并提示你先安装 Python 3
- `install_windows.bat` 默认会带上 `--launch`

### 方式二：PowerShell 运行

如果你更习惯 PowerShell，可以直接执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
```

说明：

- `install_windows.ps1` 也会自动找 `py -3` / `python`
- 默认也会带上 `--launch`
- 如果你系统默认不允许直接运行 `.ps1`，用上面的 `ExecutionPolicy Bypass` 即可

### 方式三：终端运行 Python 脚本

在 `cmd` 或 PowerShell 中进入项目目录后执行：

```powershell
py -3 patch_claude_zh_cn.py --launch
```

如果你的机器没有 `py`，可以用：

```powershell
python patch_claude_zh_cn.py --launch
```

## Windows 默认查找路径与优先级

脚本会按下面顺序找 Claude：

1. 常见默认安装目录：
   - `%LocalAppData%\Programs\Claude`
   - `%LocalAppData%\Programs\Claude Desktop`
2. 扫描常见程序目录中的 `Claude*`
3. 读取 Windows 注册表中的安装位置
4. 自动生成或读取 `patcher.config.json`
5. 使用命令行 `--app` 显式指定

## Windows 手动指定安装路径

如果自动查找失败，可以直接传路径。

### 指定安装目录

```powershell
py -3 patch_claude_zh_cn.py --app "C:\Users\you\AppData\Local\Programs\Claude" --launch
```

### 直接指定 `Claude.exe`

```powershell
py -3 patch_claude_zh_cn.py --app "C:\Users\you\AppData\Local\Programs\Claude\Claude.exe" --launch
```

### 给 `install_windows.bat` 透传参数

```bat
install_windows.bat --app "C:\Users\you\AppData\Local\Programs\Claude"
```

也可以配合自定义用户目录：

```bat
install_windows.bat --app "D:\Apps\Claude" --user-home "C:\Users\you"
```

### 给 `install_windows.ps1` 透传参数

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1 --app "D:\Apps\Claude" --user-home "C:\Users\you"
```

## 使用配置文件指定路径

如果你不想每次传 `--app`，可以在项目根目录新建 `patcher.config.json`。

另外，**Windows 自动找不到 Claude 时，脚本现在会自动生成一个 `patcher.config.json` 模板**，你只要按提示改里面的 `windows.app_path` 再跑一次即可。

### macOS / Linux shell 复制示例文件

```bash
cp patcher.config.example.json patcher.config.json
```

### Windows CMD 复制示例文件

```bat
copy patcher.config.example.json patcher.config.json
```

### Windows PowerShell 复制示例文件

```powershell
Copy-Item patcher.config.example.json patcher.config.json
```

示例内容：

```json
{
  "windows": {
    "app_path": "C:\\Users\\<you>\\AppData\\Local\\Programs\\Claude",
    "user_home": "C:\\Users\\<you>"
  },
  "macos": {
    "app_path": "/Applications/Claude.app",
    "user_home": "/Users/<you>"
  }
}
```

说明：

- `windows.app_path`：Windows Claude 安装目录，或 `Claude.exe` 所在目录
- `windows.user_home`：Windows 用户主目录
- `macos.app_path`：macOS Claude.app 路径
- `macos.user_home`：macOS 用户主目录

建议：

- 如果你的 Windows Claude 装在非默认盘符或自定义目录，优先配置 `patcher.config.json`
- 如果你只临时跑一次，优先直接用 `--app`
- 如果脚本自动生成了 `patcher.config.json`，优先先改这个文件，再重跑 `install_windows.bat` 或 `install_windows.ps1`

## 脚本会做什么

### 两个平台都会做的事

- 复制 Claude 到临时目录再打补丁
- 给前端语言白名单加入 `zh-CN`
- 合并当前 Claude 版本的 `en-US.json` 和随包中文翻译
- 安装 `statsig` 的 `zh-CN.json`
- 写入用户配置中的 `locale = zh-CN`
- 备份原始 Claude 后，再把补丁版替换回去

### 仅 macOS 会做的事

- 安装 `Localizable.strings` 到 `zh-CN.lproj` / `zh_CN.lproj`
- 对补丁后的 app 重新做本地 ad-hoc 重签名
- 追加 `disable-library-validation`
- 清理 `com.apple.quarantine`

### 仅 Windows 会做的事

- 直接替换 Windows 安装目录中的 Claude 资源
- 不做 macOS 的签名 / quarantine 处理
- 可以通过 `install_windows.bat` 或 `install_windows.ps1` 运行

## 备份与恢复

脚本安装前会在 Claude 原目录旁边生成备份。

### macOS 备份示例

```text
/Applications/Claude.backup-before-zh-CN-20260426-120000.app
```

### Windows 备份示例

```text
C:\Users\you\AppData\Local\Programs\Claude.backup-before-zh-CN-20260426-120000
```

### 恢复步骤

1. 退出 Claude Desktop
2. 删除或移走当前补丁版 Claude
3. 把备份目录改回原名
4. 重新打开 Claude

## 常见问题 / 排障

### 1. Windows 双击 `install_windows.bat` 没反应或一闪而过

通常是因为：

- 没安装 Python 3
- `py -3` 和 `python` 都不在 PATH 里

解决方式：

- 先在终端执行：

```powershell
py -3 --version
```

如果失败，再试：

```powershell
python --version
```

- 两个都不通，就先安装 Python 3，再重新双击 `install_windows.bat`

### 2. Windows 自动找不到 Claude

优先按下面顺序处理：

1. 先看项目根目录里是否已经自动生成了 `patcher.config.json`
2. 如果有，就把里面的 `windows.app_path` 改成你的真实安装目录
3. 再重新运行：
   - `install_windows.bat`
   - 或 `powershell -ExecutionPolicy Bypass -File .\install_windows.ps1`
4. 如果你不想改配置文件，就直接指定 `--app`
5. 确认你传的是：
   - Claude 安装目录
   - 或 `Claude.exe`

### 2.1 自动生成的 `patcher.config.json` 长什么样

通常会类似：

```json
{
  "windows": {
    "app_path": "C:\\Users\\你的用户名\\AppData\\Local\\Programs\\Claude",
    "user_home": "C:\\Users\\你的用户名"
  },
  "macos": {
    "app_path": "/Applications/Claude.app",
    "user_home": "/Users/<you>"
  }
}
```

你一般只需要改：

- `windows.app_path`
- 必要时改 `windows.user_home`

### 3. 补丁完成后还是英文

先检查：

1. 打开 Claude 左下角账号菜单
2. 手动切到 `Language -> 中文（中国）`
3. 完全退出 Claude 再重开一次

### 4. Claude 更新后又变回英文

这是正常现象。Claude 更新通常会覆盖补丁资源。重新运行一次脚本即可。

### 5. macOS 打开后提示签名或安全相关问题

这个仓库的 macOS 补丁流程已经会自动做本地 ad-hoc 重签名并补 `disable-library-validation`。如果仍有问题：

1. 先恢复备份
2. 再重新运行脚本
3. 确认你补丁的是当前正在使用的 Claude.app

## 注意

- Claude Desktop 更新后可能会覆盖补丁，需要重新运行脚本
- macOS 补丁后不再保留 Anthropic 官方 Developer ID / notarization 运行态签名
- Windows 自动查找失败时，优先用 `--app` 或 `patcher.config.json`
- 如果 Claude 启动后没有自动切换语言，手动在语言菜单里选择 `中文（中国）`

## 免责声明

本项目为非官方中文补丁，仅修改本机 Claude Desktop 的本地资源文件。Claude Desktop 更新后资源结构可能变化；若补丁失败，请更新本项目、手动指定路径，或重新运行脚本。
