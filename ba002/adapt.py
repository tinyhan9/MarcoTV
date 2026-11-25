# Copyright (C) 2026 tinyhan9
# SPDX-License-Identifier: GPL-3.0-only
#
# 改编自 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，GPL-3.0-only）。
# 本文件是本分支新增的适配层，不含上游代码。
#
# 极光盒子 7X（BA002）适配层 —— 源码级变换
#
# 设计原则：**不改上游任何被 git 跟踪的文件**。
# 这个脚本把一个干净的源码树复制到 stage 目录，在副本上做变换，再交给上游
# scripts/build.py 去编译。好处是：
#   - fork 与上游保持可直接 merge 的关系（本仓库只新增 ba002/ 目录）
#   - 每次上游发版，git merge 之后重跑一遍即可，没有补丁冲突
#   - 变换点全部集中在本文件，改了什么一目了然
#
# 为什么必须适配（三条硬性证据，均在本机 BA002 上实测得出）
#
#   1. 包名白名单
#      com.android.server.SkyworthConfig 在 PackageManagerService 里过滤 HOME
#      候选。放行规则是「包名以 enable_launcher_components 里的某个前缀开头」，
#      该设置的出厂默认值为
#        com.skyworthdigital.sky2dlauncher / com.android.provision /
#        com.ktcp.launcher / com.xiaopaitech.plauncher /
#        com.xiaopaitech.wallpaperlauncher / com.edufound.ott.tvlauncher
#      注意这是 startsWith 前缀匹配，不是精确相等。
#
#      实测证据：把官方 0.21.3 原样装到 BA002 上，
#        pm list packages | grep pilipala      → com.pilipala.tvhome 在
#        pm query-activities -a MAIN -c HOME   → 4 个候选，没有它
#      即：APK 装得上，但 HOME 候选里被过滤掉了，永远当不了桌面。
#
#      所以包名必须落到 com.xiaopaitech.plauncher.* 前缀下。这个名字同时
#      避开了厂商自己的 com.xiaopaitech.plauncher（无该包）与
#      com.xiaopaitech.wallpaperlauncher（厂商壁纸桌面）。
#
#   2. HomeActivity 别名默认关闭
#      上游 manifest 里 activity-alias 是 android:enabled="false"，设计意图是
#      由应用内「一键启用 Marco TV」去打开它。BA002 上这条路走不通：
#        - 固件把 pm set-home-activity / pm enable / pm disable-user 的调用者
#          限定为 uid 2000 之外的进程，应用与 shell 都会被 "User no Permission" 拒绝
#        - 系统桌面选择页在部分固件版本里不可达
#      所以只能静态启用别名。
#
#   3. 厂商桌面抢前台
#      com.xiaopaitech.wallpaperlauncher 的 BootUpReceiver 在 BOOT_COMPLETED
#      时以 uid 1000 身份 startActivity，把自家 LauncherActivity 顶到前台，
#      盖掉 HOME role 持有者（约开机后 20 秒）。实测在
#      persist.sys.launcher.mode=plauncher 时，PhoneWindowManager 的
#      DisplayHomeButtonHandler 还会主动 clearPackagePreferredActivities，
#      把默认桌面抢回厂商桌面。
#
#      这里挂一个自己的 BOOT_COMPLETED 接收器，在开机后若干个时间点重放
#      HOME；同时构建脚本会把 persist.sys.launcher.mode 设为 custom（见
#      device.py），后者能让系统看门狗不再抢。
#
# 还有一处「下载即用」的必要改动：应用内自动更新默认关掉。本分支的包名与签名
# 都和官方不同（上游 build.py 用 --release 时会校验官方签名指纹），官方包在
# 本应用上必然装不上，与其每次开机弹一个注定失败的提示，不如默认静默。

from __future__ import annotations

import io
import os
import re
import shutil
from pathlib import Path

# ---------------------------------------------------------------- 常量

OLD_PKG = "com.pilipala.tvhome"
NEW_PKG = "com.xiaopaitech.plauncher.marcotv"

# 版本控制在仓库里会跳过这些（不要把 stage 写进自己的输入）
SKIP_DIRS = {
    ".git",
    ".github/workflows",
    "ba002",
    "build_ba002",
    "build",
    "dist",
    ".tools",
    "private",
    "node_modules",
    "__________stage",
}
# 契约与历史文件：改了会破坏 GPL 合规与可追溯性
SKIP_FILES = {"CHANGELOG.md", "LICENSE", "NOTICE", "SECURITY.md", "CONTRIBUTING.md"}

TEXT_SUFFIXES = {
    ".java", ".xml", ".py", ".json", ".js", ".css", ".html", ".md",
    ".gradle", ".yml", ".yaml", ".properties", ".txt", ".pro", ".aidl",
}

# 上游 UpdateManager 的默认更新模式
UPDATE_MODE_OLD = 'return prefs.getString("mode","notify");'
# download：自动检查并下载到本地，然后由用户在更新页点一下安装。
# 之所以不选 off：本分支的更新源已经指向自己的仓库，包名与签名都对得上，
# 自动更新是可以真正走通的。之所以不选 notify：那样用户还得自己点下载。
UPDATE_MODE_NEW = 'return prefs.getString("mode","download");'


def log(message: str) -> None:
    print(f"[ba002] {message}")


# ---------------------------------------------------------------- 文件工具

def iter_text_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() in TEXT_SUFFIXES:
                yield path


def read(path: Path) -> str:
    """读成 LF 归一化的文本。

    为什么归一化：这个仓库在 Windows 上检出时是 CRLF，而所有锚点片段都按 LF 写。
    不归一化的话 `text.count(old)` 恒为 0，replace_once 会误报「找不到」，看起来
    像上游改了结构。stage 目录是构建中间产物，换行风格不影响 aapt2 / javac。
    """
    return io.open(path, "r", encoding="utf-8", errors="surrogateescape", newline="").read().replace("\r\n", "\n")


def write(path: Path, text: str) -> None:
    io.open(path, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(text)


def replace_once(text: str, old: str, new: str, what: str) -> str:
    """精确替换且只允许命中一次；上游改名时立即失败，而不是静默失效。"""
    count = text.count(old)
    if count == 0:
        raise SystemExit(
            f"[ba002] 适配失败：找不到「{what}」\n"
            f"  上游结构可能变了，请对照新版源码更新 ba002/adapt.py\n"
            f"  期望片段：{old[:140]}"
        )
    if count > 1:
        raise SystemExit(f"[ba002] 适配失败：「{what}」命中 {count} 次，预期 1 次")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------- 0. 复制

def stage_tree(source: Path, stage: Path) -> None:
    """把源码树复制到 stage。stage 必须在 source 之外或已被 SKIP_DIRS 排除。"""
    if stage.exists():
        shutil.rmtree(stage)
    stage.parent.mkdir(parents=True, exist_ok=True)

    def ignore(directory, names):
        rel = Path(directory).resolve().relative_to(source.resolve()).as_posix()
        skipped = []
        for name in names:
            if name in {".git", "build_ba002", "build", "dist", ".tools", "private", "node_modules"}:
                skipped.append(name)
            elif rel == "." and name == "ba002":
                skipped.append(name)
        return skipped

    shutil.copytree(source, stage, ignore=ignore)
    log(f"已复制源码到 stage: {stage}")


# ---------------------------------------------------------------- 1. 包名

def rename_package(stage: Path) -> None:
    old_path = Path(OLD_PKG.replace(".", os.sep))
    new_path = Path(NEW_PKG.replace(".", os.sep))
    moved = []

    for src_root in [stage / "app/src/main/java", stage / "lite"]:
        if not src_root.is_dir():
            continue
        old_dir = src_root / old_path
        if not old_dir.is_dir():
            continue
        new_dir = src_root / new_path
        if new_dir.exists():
            shutil.rmtree(new_dir)
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_dir), str(new_dir))
        moved.append(str(old_dir.relative_to(stage)))
    if not moved:
        raise SystemExit("[ba002] 找不到 com/pilipala/tvhome 目录")
    log(f"包目录搬迁: {', '.join(moved)}")

    old_slash = OLD_PKG.replace(".", "/")
    new_slash = NEW_PKG.replace(".", "/")
    changed = 0
    for path in iter_text_files(stage):
        text = read(path)
        # 两种写法都要看：包声明/import 用斜杠形式，字符串字面量与 manifest 用点形式。
        # 只判断点形式会漏掉 scripts/check_release.py 这种只写路径的地方。
        if OLD_PKG not in text and old_slash not in text:
            continue
        new_text = text.replace(old_slash, new_slash).replace(OLD_PKG, NEW_PKG)
        if new_text != text:
            write(path, new_text)
            changed += 1
    log(f"包名替换: {changed} 个文件")


# ---------------------------------------------------------------- 2. manifest

RELAY_RECEIVER_XML = """        <!-- 极光盒子 7X（BA002）适配：厂商桌面 com.xiaopaitech.wallpaperlauncher 的
             BootUpReceiver 在 BOOT_COMPLETED 时以 uid 1000 身份 startActivity，会盖掉
             本应用这个 HOME role 持有者。下面这个接收器在开机后的若干时间点重放 HOME，
             把前台抢回来。只在 BOOT_COMPLETED 触发（LOCKED_BOOT_COMPLETED 阶段应用
             私有数据尚未解密，显式组件启动会抛 NPE）。 -->
        <receiver android:name=".Ba002BootRelay" android:exported="false" android:directBootAware="true">
            <intent-filter android:priority="999">
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>
"""

ALIAS_OLD = (
    'android:name=".HomeActivity" android:targetActivity=".MainActivity" '
    'android:exported="true" android:enabled="false"'
)
ALIAS_NEW = (
    'android:name=".HomeActivity" android:targetActivity=".MainActivity" '
    'android:exported="true" android:enabled="true"'
)

RELAY_ANCHOR = '        <service android:name=".RecoveryService"'


def patch_manifest(stage: Path, debuggable: bool) -> None:
    manifest = stage / "app/src/main/AndroidManifest.xml"
    text = read(manifest)

    # versionName 不动（与上游完全对齐）；versionCode 加 RELEASE_REVISION，
    # 否则已装同 code 的设备永远看不到本分支的修订版。
    match = re.search(r'android:versionCode="(\d+)"', text)
    if not match:
        raise SystemExit("[ba002] manifest 里找不到 android:versionCode")
    official_code = int(match.group(1))
    release_code = official_code + RELEASE_REVISION
    if RELEASE_REVISION:
        text = text.replace(
            f'android:versionCode="{official_code}"',
            f'android:versionCode="{release_code}"',
            1,
        )
    log(f"versionCode {official_code} -> {release_code}（versionName 保持上游）")

    text = replace_once(text, ALIAS_OLD, ALIAS_NEW, "HomeActivity 别名的 enabled=false")

    if debuggable:
        text = replace_once(
            text,
            '<application android:name=".MarcoApplication"',
            '<application android:name=".MarcoApplication" android:debuggable="true"',
            "application 标签（插入 debuggable）",
        )

    if ".Ba002BootRelay" not in text:
        text = replace_once(text, RELAY_ANCHOR, RELAY_RECEIVER_XML + RELAY_ANCHOR, "RecoveryService 声明")

    write(manifest, text)
    log(f"manifest 适配完成（debuggable={debuggable}）")


# ---------------------------------------------------------------- 3. 抢前台接收器

# 本分支新增、需要随构建注入 stage 的源文件。
# Ba002RelayPolicy 把判定规则抽成纯逻辑，Ba002BootRelay 只负责接线 ——
# 这样 ba002/test_relay.py 能在 JVM 上把所有分支跑完，不必装到电视上才发现判定写错。
ADAPT_SOURCES = [
    "Ba002BootRelay.java",
    "Ba002RelayPolicy.java",
]


def install_relay(stage: Path) -> None:
    """把适配层源文件注入 stage，并把包名对齐成 NEW_PKG。"""
    target_dir = stage / "app/src/main/java" / NEW_PKG.replace(".", "/")
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ADAPT_SOURCES:
        source = Path(__file__).with_name(name)
        if not source.is_file():
            raise SystemExit(f"[ba002] 缺少 {source}")
        write(target_dir / name, read(source).replace(f"package {OLD_PKG};", f"package {NEW_PKG};"))
    log(f"已注入 {len(ADAPT_SOURCES)} 个适配层源文件: {', '.join(ADAPT_SOURCES)}")


# ---------------------------------------------------------------- 4. 自动更新指向本仓库

# 上游 UpdatePolicy 把更新源写死成 Pilipala9919 的仓库与镜像。本分支的包名、
# 签名都与官方不同，官方 APK 永远装不上（verifyApk 会比对签名），所以必须把
# 更新源换成自己的，否则应用内「检查更新」只会拿到一个注定装不上的包。
#
# 换源时要同时改五处，漏一处就会在运行时被拦下或连不上：
#   1. feeds()      —— 频道文件名加 ba002- 前缀，避免和上游 feed 混淆
#   2. MIRROR/FEED  —— 两个 feed 地址
#   3. downloads()  —— APK 下载地址
#   4. apkUrl()     —— 允许的 APK 主机与路径前缀
#   5. transferUrl()—— 允许的重定向/传输主机
#
# 安全性不靠这里：verifyApk 会强制比对包名、versionCode、versionName 与
# **签名证书**，官方包（签名不同）即使被喂进来也会被拒。

REPO_OWNER = "tinyhan9"
REPO_NAME = "MarcoTV"
REPO_BRANCH = "ba002"

# versionName 与上游对齐（用户要求），versionCode 在上游基础上加这个数。
# 每次本分支单独发修订版时把它加 1。上游发新版时通常可以归 0，
# 因为上游的 code 本身已经变大了。
RELEASE_REVISION = 3
FEED_PATH = "docs/updates/"

# raw.githubusercontent 不受 Pages 与 CDN 缓存影响，改动立刻生效，放第一位。
FEED_PRIMARY = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}/{FEED_PATH}"
# jsDelivr 在国内通常可达，作为后备；注意它按分支缓存，可能延迟数小时。
FEED_FALLBACK = f"https://cdn.jsdelivr.net/gh/{REPO_OWNER}/{REPO_NAME}@{REPO_BRANCH}/{FEED_PATH}"

UPDATE_MIRROR_OLD = 'static final String FEED="https://pilipala9919.github.io/MarcoTV/updates/";\n    static final String MIRROR="https://marcotv.wlj9919.top/";'
UPDATE_MIRROR_NEW = (
    f'static final String FEED="{FEED_FALLBACK}";\n'
    f'    static final String MIRROR="{FEED_PRIMARY}";'
)

UPDATE_FEEDS_OLD = """        String name=(BuildEdition.RESTRICTED?"restricted-":"")+channel;
        return new String[]{MIRROR+"updates/"+name+".json",FEED+name+".json"};"""
UPDATE_FEEDS_NEW = """        // 本分支用自己的频道文件（ba002-stable.json / ba002-preview.json），
        // 与上游的 stable.json 分开，互不覆盖。
        String name="ba002-"+channel+".json";
        return new String[]{MIRROR+name,FEED+name};"""

UPDATE_DOWNLOAD_OLD = """        String file="MarcoTV-"+version+(BuildEdition.RESTRICTED?"-Restricted":"")+".apk";
        return new String[]{MIRROR+file,"https://github.com/Pilipala9919/MarcoTV/releases/download/v"+version+"/"+file};"""
UPDATE_DOWNLOAD_NEW = """        String file="MarcoTV-"+version+"-BA002.apk";
        return new String[]{"https://github.com/""" + REPO_OWNER + "/" + REPO_NAME + """/releases/download/v"+version+"-ba002/"+file};"""

# apkUrl 用整段方法替换而不是字符串锚点：方法体里有 Java 正则（反斜杠成对出现），
# 写成 Python 字符串常量时转义层数极易数错，数错就会误报「上游结构变了」。
UPDATE_APKURL_PATTERN = r"static boolean apkUrl\(String value\)\{.*?\n    \}\n"

UPDATE_APKURL_NEW = """static boolean apkUrl(String value){
        try{
            URI u=new URI(value);
            if(!editionUrl(u.getPath()))return false;
            // 只信任本仓库的 release 资产；官方包签名不同，verifyApk 仍会拒绝。
            return "https".equals(u.getScheme())
                    &&u.getUserInfo()==null&&u.getPort()==-1&&u.getQuery()==null&&u.getFragment()==null
                    &&"github.com".equals(u.getHost())
                    &&u.getPath().startsWith("/__REPO_OWNER__/__REPO_NAME__/releases/download/")
                    &&u.getPath().endsWith(".apk")
                    &&!u.getPath().contains("..")&&u.getRawPath().equals(u.getPath());
        }catch(Exception e){
            return false;
        }
    }
"""

UPDATE_TRANSFER_OLD = """                    &&("marcotv.wlj9919.top".equals(h)||"pilipala9919.github.io".equals(h)||"github.com".equals(h)||"release-assets.githubusercontent.com".equals(h)||"objects.githubusercontent.com".equals(h));"""
UPDATE_TRANSFER_NEW = """                    &&("raw.githubusercontent.com".equals(h)||"cdn.jsdelivr.net".equals(h)
                    ||"github.com".equals(h)||"release-assets.githubusercontent.com".equals(h)||"objects.githubusercontent.com".equals(h));"""


def patch_update_endpoint(stage: Path) -> None:
    """把应用内更新检查指向本仓库，而不是上游。"""
    policy = stage / "app/src/main/java" / NEW_PKG.replace(".", "/") / "UpdatePolicy.java"
    text = read(policy)
    text = replace_once(text, UPDATE_MIRROR_OLD, UPDATE_MIRROR_NEW, "UpdatePolicy 的 FEED / MIRROR 常量")
    text = replace_once(text, UPDATE_FEEDS_OLD, UPDATE_FEEDS_NEW, "UpdatePolicy.feeds() 的频道文件名")
    text = replace_once(text, UPDATE_DOWNLOAD_OLD, UPDATE_DOWNLOAD_NEW, "UpdatePolicy.downloads() 的下载地址")
    new_apkurl = UPDATE_APKURL_NEW.replace("__REPO_OWNER__", REPO_OWNER).replace("__REPO_NAME__", REPO_NAME)
    text, hits = re.subn(UPDATE_APKURL_PATTERN, new_apkurl, text, count=1, flags=re.S)
    if hits != 1:
        raise SystemExit("[ba002] 适配失败：UpdatePolicy.apkUrl() 结构变了，找不到方法边界")
    text = replace_once(text, UPDATE_TRANSFER_OLD, UPDATE_TRANSFER_NEW, "UpdatePolicy.transferUrl() 的主机白名单")
    write(policy, text)
    log("应用内更新源已指向本仓库")


# ---------------------------------------------------------------- 5. 关闭应用内自动更新

def disable_self_update(stage: Path) -> None:
    manager = stage / "app/src/main/java" / NEW_PKG.replace(".", "/") / "UpdateManager.java"
    text = read(manager)
    text = replace_once(text, UPDATE_MODE_OLD, UPDATE_MODE_NEW, "UpdateManager.mode() 默认值 notify")
    write(manager, text)
    log("应用内自动更新默认 download（自动下载、手动确认安装）")


# ---------------------------------------------------------------- 5. 自检

def verify(stage: Path) -> None:
    """确认 stage 里干净：没有残留旧包名，HOME 声明只有一个，别名是开的。"""
    problems = []

    leftovers = []
    for path in iter_text_files(stage):
        text = read(path)
        if OLD_PKG in text or OLD_PKG.replace(".", "/") in text:
            leftovers.append(str(path.relative_to(stage)))
    if leftovers:
        problems.append("残留旧包名: " + ", ".join(leftovers[:10]))

    manifest = read(stage / "app/src/main/AndroidManifest.xml")
    if manifest.count("android.intent.category.HOME") != 1:
        problems.append(
            f'HOME 声明应只有 1 处，实际 {manifest.count("android.intent.category.HOME")} 处'
            "（同包多个 HOME 组件会让 Android 的 PreferredComponent.sameSet() 校验失效，"
            "表现为每次按 HOME 都弹选择框）"
        )
    if 'android:enabled="true"' not in manifest.split(".HomeActivity")[1][:200]:
        problems.append("HomeActivity 别名没有启用")
    if ".Ba002BootRelay" not in manifest:
        problems.append("manifest 里没有 Ba002BootRelay")

    java_root = stage / "app/src/main/java" / NEW_PKG.replace(".", "/")
    for name in ADAPT_SOURCES:
        adapt_file = java_root / name
        if not adapt_file.is_file():
            problems.append(f"缺少 {name}")
            continue
        if f"package {NEW_PKG};" not in read(adapt_file):
            problems.append(f"{name} 的 package 声明不对")

    if problems:
        raise SystemExit("[ba002] 自检失败：\n  - " + "\n  - ".join(problems))
    log("自检通过：无旧包名残留、HOME 声明唯一、别名已启用、适配层源文件已就位")


# ---------------------------------------------------------------- 入口

def adapt(source: Path, stage: Path, debuggable: bool = True) -> Path:
    source = source.resolve()
    stage = stage.resolve()
    if not (source / "app/src/main/AndroidManifest.xml").is_file():
        raise SystemExit(f"[ba002] {source} 不像 MarcoTV 源码树")
    if stage == source or source in stage.parents and stage.name != source.name:
        pass
    log(f"源: {source}")
    log(f"舞台: {stage}")
    stage_tree(source, stage)
    rename_package(stage)
    patch_manifest(stage, debuggable)
    install_relay(stage)
    patch_update_endpoint(stage)
    disable_self_update(stage)
    verify(stage)
    return stage


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="把 MarcoTV 源码适配到极光盒子 7X（BA002）")
    parser.add_argument("--source", default=".", help="源码树根目录（默认当前目录）")
    parser.add_argument("--stage", default="build_ba002/stage", help="stage 目录")
    parser.add_argument("--no-debuggable", action="store_true", help="不打开 android:debuggable")
    args = parser.parse_args()
    adapt(Path(args.source), Path(args.stage), debuggable=not args.no_debuggable)
