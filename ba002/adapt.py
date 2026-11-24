# Copyright (C) 2026 tinyhan9
# SPDX-License-Identifier: GPL-3.0-only
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
UPDATE_MODE_NEW = 'return prefs.getString("mode","off");'


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
    return io.open(path, "r", encoding="utf-8", errors="surrogateescape", newline="").read()


def write(path: Path, text: str) -> None:
    io.open(path, "w", encoding="utf-8", errors="surrogateescape", newline="").write(text)


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

def install_relay(stage: Path) -> None:
    source = Path(__file__).with_name("Ba002BootRelay.java")
    if not source.is_file():
        raise SystemExit(f"[ba002] 缺少 {source}")
    target = stage / "app/src/main/java" / NEW_PKG.replace(".", "/") / "Ba002BootRelay.java"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = read(source)
    write(target, text.replace(f"package {OLD_PKG};", f"package {NEW_PKG};"))
    log("已注入 Ba002BootRelay")


# ---------------------------------------------------------------- 4. 关闭应用内自动更新

def disable_self_update(stage: Path) -> None:
    manager = stage / "app/src/main/java" / NEW_PKG.replace(".", "/") / "UpdateManager.java"
    text = read(manager)
    text = replace_once(text, UPDATE_MODE_OLD, UPDATE_MODE_NEW, "UpdateManager.mode() 默认值 notify")
    write(manager, text)
    log("应用内自动更新默认关闭")


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
    relay = java_root / "Ba002BootRelay.java"
    if not relay.is_file():
        problems.append("缺少 Ba002BootRelay.java")
    else:
        relay_text = read(relay)
        if f"package {NEW_PKG};" not in relay_text:
            problems.append("Ba002BootRelay 的 package 声明不对")

    if problems:
        raise SystemExit("[ba002] 自检失败：\n  - " + "\n  - ".join(problems))
    log("自检通过：无旧包名残留、HOME 声明唯一、别名已启用、relay 已就位")


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
