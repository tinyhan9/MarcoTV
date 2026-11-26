# 安装指南

> 这份文档只讲**怎么装、装完怎么让它真的当桌面**。
> 想知道为什么官方版在这台盒子上不行，看 [BA002.md](BA002.md)。

适用设备：**极光盒子 7X**（型号 BA002，Android 11，Skyworth 系固件）。
其它型号没有验证过，能不能用看 [文末](#别的盒子能用吗)。

---

## 先看这一段：装完不等于能当桌面

这是新手最容易卡住的地方，先说清楚。

极光盒子固件在系统里加了一道过滤（代码在 `PackageManagerService.filterHomeApp()`）：按 HOME 键时，系统要先列出"哪些应用可以当桌面"，这个列表被固件按**包名前缀**筛过一遍。

结果就是：

| | 官方 Marco TV | 本适配版 |
|---|---|---|
| APK 能不能装上 | ✅ 能 | ✅ 能 |
| 能不能手动点开用 | ✅ 能 | ✅ 能 |
| 按 HOME 时会不会出现 | ❌ **永远不会** | ✅ 会 |
| 能不能设成默认桌面 | ❌ 不可能 | ✅ 可以 |

原因很简单：官方包名叫 `com.pilipala.tvhome`，固件的白名单里只有 `com.xiaopaitech.plauncher`、`com.ktcp.launcher` 这几个前缀，对不上就筛掉。本适配版把包名改成了 `com.xiaopaitech.plauncher.marcotv`，命中了白名单。

**所以：如果你只想"装个 APK 就完事"，那官方版和你无缘，本适配版也需要你多走一步。** 那一步就是下面的「第二步」。

---

## 目录

- [第一步：把 APK 装进盒子](#第一步把-apk-装进盒子)
  - [方式 A：有电脑（最稳，推荐）](#方式-a有电脑最稳推荐)
  - [方式 B：没电脑，用 U 盘](#方式-b没电脑用-u-盘)
- [第二步：让它真的当桌面](#第二步让它真的当桌面)
  - [路线 1：有电脑，一条命令搞定](#路线-1有电脑一条命令搞定)
  - [路线 2：没电脑，用应用内的「Home 兼容」](#路线-2没电脑用应用内的home-兼容)
- [第三步：验证真的成了](#第三步验证真的成了)
- [装完 / 升级完必做的一件事](#装完--升级完必做的一件事)
- [出问题了](#出问题了)
- [卸载与回退](#卸载与回退)
- [别的盒子能用吗](#别的盒子能用吗)

---

## 第一步：把 APK 装进盒子

先下载：[**MarcoTV-0.21.3-BA002.apk**](https://github.com/tinyhan9/MarcoTV/releases/latest)

顺手对一下校验和，确保文件没被下载坏（可跳过，出问题时再回来查）：

<details>
<summary>点开看怎么校验</summary>

Windows（PowerShell）：

```powershell
Get-FileHash .\MarcoTV-0.21.3-BA002.apk -Algorithm SHA256
```

macOS / Linux：

```bash
shasum -a 256 MarcoTV-0.21.3-BA002.apk
# 或 sha256sum MarcoTV-0.21.3-BA002.apk
```

输出应该等于 Release 页面附件 `MarcoTV-0.21.3-BA002.apk.sha256` 里那一串。

</details>

### 方式 A：有电脑（最稳，推荐）

这条路同时解决"装 APK"和"设成桌面"两件事，**一次搞定，不用再折腾**。

#### 1. 装好 ADB 工具

**Windows**

1. 下载 <https://developer.android.com/tools/releases/platform-tools>
2. 解压到一个你不会随手删掉的目录，比如 `D:\platform-tools`
3. 打开那个文件夹，在地址栏输入 `powershell` 回车 —— 这样打开的窗口就"在"这个目录里了

**macOS**

```bash
brew install android-platform-tools
```

没有 Homebrew 就装一个：<https://brew.sh>

**Linux**

```bash
sudo apt install android-tools-adb     # Debian / Ubuntu
sudo dnf install android-tools         # Fedora
```

#### 2. 让盒子和电脑在同一个 Wi-Fi / 同一个路由器下

这一步很重要：盒子默认没开 USB 调试，只能走网络。

#### 3. 打开盒子的调试开关

在盒子上：

1. 进 **设置**（系统设置，不是 Marco TV 的设置）
2. 找到 **关于** / **关于本机**
3. 连续点 **版本号** 7 次，直到提示"已进入开发者模式"
4. 退回设置，进 **开发者选项**
5. 打开 **USB 调试** / **网络调试** / **ADB 调试**（不同固件叫法不同，看到 ADB 字样的都打开）

> 找不到也没关系，先跳到第 4 步试试能不能连上。有些固件的这个开关出厂就是开的。

#### 4. 找到盒子的 IP 地址

在盒子上：**设置 → 关于 → 网络信息** / **状态**，记下 IP，例如 `192.168.5.87`。

#### 5. 连上

在电脑的终端窗口里（Windows 就是第 1 步打开的那个 PowerShell）：

```bash
adb connect 192.168.5.87:5555
```

把 `192.168.5.87` 换成你盒子的 IP。成功会显示：

```
connected to 192.168.5.87:5555
```

再确认一下：

```bash
adb devices
```

应该看到：

```
List of devices attached
192.168.5.87:5555       device
```

> 如果显示 `offline` 或 `unauthorized`，在盒子上看一眼有没有弹出"允许调试"的对话框，点允许。

#### 6. 装 APK

把下载好的 `MarcoTV-0.21.3-BA002.apk` 放到终端的当前目录，然后：

```bash
adb install -r MarcoTV-0.21.3-BA002.apk
```

看到 `Success` 就成了。

> 路径不好搞的话，把 APK 直接拖进终端窗口，路径会自动填上。

#### 7. 设成默认桌面

```bash
adb shell cmd role add-role-holder android.app.role.HOME com.xiaopaitech.plauncher.marcotv
adb shell setprop persist.sys.launcher.mode custom
```

这两条命令的作用：

- 第一条：告诉系统"默认桌面是 Marco TV"。写入 `/data/system/roles.xml`，**重启不丢**。
- 第二条：关掉固件里那个"每次按 HOME 就把桌面抢回厂商桌面"的看门狗。写进 persist 属性，**重启不丢**。

跑完就完事了，跳到 [第三步验证](#第三步验证真的成了)。

---

### 方式 B：没电脑，用 U 盘

这条路只能解决"装 APK"。**"设成默认桌面"要在盒子上手工点**，见[路线 2](#路线-2没电脑用应用内的home-兼容)。

#### 1. 准备 U 盘

把 `MarcoTV-0.21.3-BA002.apk` 拷到 U 盘根目录。建议顺手把文件名改短，比如 `marco.apk` —— 有些盒子的文件浏览器显示长文件名会截断。

#### 2. U 盘插到盒子上

插盒子侧面的 USB 口。

#### 3. 用盒子自带的文件管理器打开它

极光盒子一般有「媒体中心」/「文件管理」/「我的文件」。进去找到 U 盘，点 `marco.apk`。

#### 4. 允许安装未知来源

第一次装会提示"禁止安装未知来源应用"，按提示去打开：

**设置 → 安全 → 未知来源** 或 **设置 → 应用 → 特殊权限 → 安装未知应用**，找到你用的那个文件管理器，允许它安装。

#### 5. 装完

装好后桌面会出现 Marco TV 的图标，点开能正常用 —— 但**这时候它还不是默认桌面**，按 HOME 还是会回到厂商桌面。

继续看[路线 2](#路线-2没电脑用应用内的home-兼容)。

> **如果盒子上根本没有文件管理器**：从应用商店装一个（当贝市场、沙发管家之类都有文件管理器），或者用手机的"文件互传"类应用推到盒子上。极光盒子也支持「远程安装」—— 具体入口在系统设置里，不同固件位置不同。

---

## 第二步：让它真的当桌面

### 路线 1：有电脑，一条命令搞定

如果你走的是方式 A 并且已经跑了第 7 步的两条命令，**你已经完成了，不用看这里**。

如果跳过了，现在补上 —— 盒子连着 ADB 的情况下：

```bash
adb shell cmd role add-role-holder android.app.role.HOME com.xiaopaitech.plauncher.marcotv
adb shell setprop persist.sys.launcher.mode custom
```

然后重启盒子：

```bash
adb reboot
```

重启后开机直接进 Marco TV 就对了。

### 路线 2：没电脑，用应用内的「Home 兼容」

这条路不依赖 ADB。原理是：Marco TV 注册了一个**无障碍服务**，在系统处理 HOME 键之前先把按键拦下来，自己把桌面拉起来。所以它不需要拿到"默认桌面"这个身份也能工作。

#### 1. 打开盒子的无障碍设置

在盒子上：**系统设置 → 辅助功能 / 无障碍**。

不同固件叫法不同，看到「辅助功能」「无障碍」「Accessibility」都是它。

#### 2. 找到并开启 Marco TV 的服务

在服务列表里找 **Marco TV Home 键兼容**（英文是 `Marco TV Home 键兼容`，包名 `com.xiaopaitech.plauncher.marcotv`）。

打开它的开关，会弹出授权提示，选**允许**。

> **找不到这一项？** 说明你这版固件把无障碍入口藏起来了或者改了位置。试试：
> - 在系统设置里搜「无障碍」「辅助」
> - 或者在盒子上装个 `设置` 类的第三方应用（有些固件把原生设置藏了）
> - 都不行就只能回到[路线 1](#路线-1有电脑一条命令搞定)，借一台电脑用一下，两分钟的事

#### 3. 在 Marco TV 里确认

回到 Marco TV 桌面，按遥控器的 **菜单键**（就是那个三条横线 / `≡` 的键），或者把光标移到左上角的**齿轮图标**上按 OK，进设置。

然后：

**遥控器与多任务 → 默认桌面与 Home 键 → 桌面启用与检查**

这个页面会显示当前状态，并且有一个主按钮。因为你的盒子没有可用的"系统桌面选择页"，它会直接进 **Home 兼容** 模式，点确认就行。

#### 4. 重启盒子验证

断电重启（拔插头再插上也行）。开机后应该直接进 Marco TV。

如果开机先看到厂商桌面、几秒后才跳到 Marco TV —— 这是正常的，说明兼容模式在工作。

> ⚠️ **这条路线我没能在真机上完整验证过**。我手上的盒子在写这份文档时离线了，只在代码里确认这条路径存在（`HomeSetupPolicy.Route.ACCESSIBILITY` 分支），并且 `HomeKeyService` 的拦截逻辑在拿到无障碍授权后是有效的。如果你走这条路遇到问题，欢迎开 issue 说一声。

---

## 第三步：验证真的成了

### 最直观的验证：连按 HOME 键 20 次

拿起遥控器，**连按 HOME 键 20 次**。

- ✅ 每次都回到 Marco TV 桌面 → 成了
- ❌ 中途跳回厂商桌面 → 没成，看[出问题了](#出问题了)
- ❌ 弹出"选择主屏幕应用"的框 → 没成，看[出问题了](#出问题了)

### 再验证一次重启

断电重启（拔插头，等一下，再插上）。开机后：

- ✅ 直接进 Marco TV → 真的成了
- ❌ 进的是厂商桌面 → 看[出问题了](#出问题了)

### 有电脑的话，可以看得更清楚

```bash
# 应该输出 ... com.xiaopaitech.plauncher.marcotv/.HomeActivity
adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME
```

```bash
# 应该看到 mAlways=true（系统记住了你的选择）
adb shell dumpsys package | grep -A2 'marcotv/.HomeActivity' | grep mAlways
```

```bash
# 应该输出 ... com.xiaopaitech.plauncher.marcotv/...HomeActivity
adb shell dumpsys window | grep mCurrentFocus
```

---

## 装完 / 升级完必做的一件事

**每次升级 APK 之后，无障碍服务会被系统重置。**

这是 Android 的行为：APK 一更新，系统会重新校验所有无障碍服务，Marco TV 的 Home 键拦截服务会被从启用列表里摘掉。表现就是：升级后按 HOME 又回厂商桌面了。

修法，有电脑（一条命令）：

```bash
adb shell cmd settings put secure enabled_accessibility_services "com.ktcp.aiagent/com.ktcp.tvagent.service.VoiceAccessibilityService:com.xiaopaitech.plauncher.marcotv/com.xiaopaitech.plauncher.marcotv.HomeKeyService"
adb shell cmd settings put secure accessibility_enabled 1
```

没电脑：重新走一遍[路线 2 的第 1–2 步](#路线-2没电脑用应用内的home-兼容)，在无障碍设置里把服务开关关掉再打开。

> 只升级 APK 会掉这一项。「默认桌面身份」和「launcher.mode」这两项**不会**掉，重启和升级都不影响。

> **用应用内更新也一样**：菜单键 → 系统与关于 → 软件更新 → 点「下载新版」，下载完再点「安装已下载版本」。升级完无障碍服务同样会被系统重置，记得重跑上面这条命令。

---

## 出问题了

### 按 HOME 弹出"选择主屏幕应用"

**原因**：系统的"默认桌面"记录丢了。

**修法**（有电脑）：

```bash
adb shell cmd role add-role-holder android.app.role.HOME com.xiaopaitech.plauncher.marcotv
```

**没电脑**：菜单键进设置 → **遥控器与多任务 → 默认桌面与 Home 键 → 桌面启用与检查**，按页面上的按钮重新设置一遍。同一页往下还有个「Home 键兼容模式」开关，可以用来确认兼容模式是否开着。

### 选了「始终」但下次按 HOME 还问

**原因**：这个包里出现了两个 HOME 组件。Android 有个校验：如果候选集合和记录里存的不一致，就把这条记录当成失效，于是每次都重新问。

**怎么确认**（有电脑）：

```bash
adb shell pm query-activities -a android.intent.action.MAIN -c android.intent.category.HOME
```

看输出里 `packageName=com.xiaopaitech.plauncher.marcotv` 出现了几次。**正常应该恰好 1 次**。

出现多次说明装错了包（可能是把官方版和适配版混装了）。修法见[卸载与回退](#卸载与回退)。

### 开机先进厂商桌面，过一会儿才跳到 Marco TV

**这是正常的**。厂商桌面有个开机启动的接收器会抢先占前台，Marco TV 会在几秒后把它挤掉。最多等 45 秒。

如果**一直不跳**，说明两件事之一：

1. 无障碍服务掉了 → 看[升级后必做的一件事](#装完--升级完必做的一件事)
2. `launcher.mode` 被改回去了 → 有电脑的话重跑 `adb shell setprop persist.sys.launcher.mode custom`

### 装的时候提示"应用未安装"或"包冲突"

**原因**：你手机上/盒子上已经装了官方版 Marco TV（包名 `com.pilipala.tvhome`），或者装了另一个改过包名的版本。

两个包名不同，理论上能共存，但会互相干扰（都注册 HOME 组件，触发上面那个"每次都要选"的问题）。**只留一个。**

```bash
adb uninstall com.pilipala.tvhome
```

### 想看系统到底放行了谁、拦了谁

有电脑的话，这是最硬的判定手段：

```bash
adb logcat -s PackageManager
```

然后按一次 HOME，会看到类似：

```
I PackageManager: allow home apk: ... com.xiaopaitech.plauncher.marcotv
I PackageManager: block home apk: ... com.pilipala.tvhome
```

- `allow` 里有 marcovt → 包名对了，问题在后面的步骤（role / 无障碍）
- `allow` 里没有 marcovt → 包名没生效，检查你装的到底是不是本适配版

```bash
adb shell dumpsys package com.xiaopaitech.plauncher.marcotv | grep versionName
```

应该输出 `versionName=0.21.3`。如果输出 `com.pilipala.tvhome`，你装的是官方版。

---

## 卸载与回退

### 想换回官方桌面

```bash
adb shell cmd role remove-role-holder android.app.role.HOME com.xiaopaitech.plauncher.marcotv
adb shell setprop persist.sys.launcher.mode plauncher
adb uninstall com.xiaopaitech.plauncher.marcotv
```

第一条把默认桌面身份还回去，第二条让固件接管 HOME（会自动切回厂商桌面），第三条卸载。

### 卸载会不会丢数据

会。壁纸、应用排序、卡片布局都存在应用私有目录里，卸载就没了。

**卸载前先备份**：菜单键进设置 → **系统与关于 → 更新与备份 → 备份与恢复**，导出设置与自定义封面。另外动态壁纸文件在应用私有目录里，备份不含它，需要单独存一份原视频。

### 官方版和适配版能互相覆盖安装吗

**不能**。两者包名不同、签名也不同。要换必须**先卸载再装**，会丢数据。

---

## 别的盒子能用吗

**没验证过。** 本适配版只在极光盒子 7X（BA002，Android 11，Skyworth 系固件）上实机测过。

判断一台别的盒子需不需要这个适配版，一条命令：

```bash
adb shell pm query-activities -a android.intent.action.MAIN -c android.intent.category.HOME
```

装上官方版后跑这条：

- 候选列表里**有** `com.pilipala.tvhome` → 那台盒子没有这道锁，用官方版就行
- 候选列表里**没有** → 有锁。再看 `adb logcat -s PackageManager` 里 `block home apk:` 的内容

如果是创维 / 酷开系的固件，很可能共用同一套过滤逻辑，那本适配版大概率也能用。想要更保险，装好后立刻按 20 次 HOME 验一遍。

**别的品牌（小米、TCL、海信、索尼等）不要用这个包** —— 它们没有这个白名单机制，用官方版就好，装本适配版反而可能因为包名陌生行为异常。

---

## 还有问题

开 [issue](https://github.com/tinyhan9/MarcoTV/issues)，附上这几样东西能大幅加快定位：

```bash
adb shell dumpsys package com.xiaopaitech.plauncher.marcotv | grep versionName
adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME
adb shell dumpsys window | grep mCurrentFocus
adb logcat -s PackageManager
```

以及：盒子具体型号（在**设置 → 关于**里看）、Android 版本、你走的是哪条路线（有电脑 / 没电脑）。

---

[← 回主页](README.md) · [适配原理和技术细节 →](BA002.md)
