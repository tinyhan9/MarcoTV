# Copyright (C) 2026 tinyhan9
# SPDX-License-Identifier: GPL-3.0-only
#
# 让本仓库跟着上游走：把 upstream/main 合并进来，然后报告适配层是否需要调整。
#
# 用法：
#   python ba002/upgrade.py --check    # 只报告新版本号与适配点是否还对得上
#   python ba002/upgrade.py            # 合并 upstream/main 并重跑适配自检
#
# 设计意图：本仓库只新增 ba002/ 目录，不改上游文件，所以 merge 应该零冲突。
# 如果 adapt.py 依赖的结构被上游改了，adapt.py 的 verify() 会在自检阶段明确
# 指出哪一处对不上，不会静默产出坏包。

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ba002"))


def run(args, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)


def log(message: str) -> None:
    print(f"[upgrade] {message}")


def current_version() -> str:
    import xml.etree.ElementTree as ET

    manifest = ROOT / "app/src/main/AndroidManifest.xml"
    root = ET.parse(manifest).getroot()
    return root.get("{http://schemas.android.com/apk/res/android}versionName") or "?"


def check_only() -> int:
    has_upstream = run(["git", "remote", "get-url", "upstream"]).returncode == 0
    if not has_upstream:
        log("没有配置 upstream 远端。先执行：")
        log("  git remote add upstream https://github.com/Pilipala9919/MarcoTV.git")
        log("  git fetch upstream")
        return 1

    log("拉取 upstream...")
    run(["git", "fetch", "upstream", "--tags"])
    log(f"当前工作树版本: {current_version()}")

    diff = run(["git", "diff", "--stat", "HEAD", "upstream/main"])
    if diff.returncode != 0:
        log("无法比较 upstream/main")
        return 1
    if not diff.stdout.strip():
        log("与 upstream/main 完全一致，无需升级")
        return 0

    log("upstream/main 上的改动：")
    for line in diff.stdout.strip().splitlines()[-15:]:
        print("  " + line)

    # 看 adapt.py 依赖的锚点有没有被动
    anchors = {
        "HomeActivity 别名 enabled=false": "android:name=\".HomeActivity\"",
        "application 标签": "<application android:name=\".MarcoApplication\"",
        "RecoveryService 声明": "<service android:name=\".RecoveryService\"",
        "UpdateManager mode 默认值": 'return prefs.getString("mode","notify");',
    }
    log("检查适配锚点（在 upstream/main 上）：")
    problems = 0
    for name, needle in anchors.items():
        blob = run(["git", "show", f"upstream/main:app/src/main/AndroidManifest.xml"]).stdout
        if name != "UpdateManager mode 默认值":
            ok = needle in blob
        else:
            src = run(["git", "show",
                       "upstream/main:app/src/main/java/com/pilipala/tvhome/UpdateManager.java"]).stdout
            ok = needle in src
        print(f"  {'OK ' if ok else '变了'} {name}")
        if not ok:
            problems += 1

    if problems:
        log(f"有 {problems} 处锚点变了，合并后需要更新 ba002/adapt.py 再构建")
        return 2
    log("所有适配锚点都在，可以直接合并")
    return 0


def merge() -> int:
    code = check_only()
    if code == 2:
        log("锚点有变化，仍继续合并，但之后务必更新 adapt.py")
    log("合并 upstream/main")
    result = run(["git", "merge", "--no-edit", "upstream/main"])
    print(result.stdout or result.stderr)
    if result.returncode != 0:
        log("合并有冲突。本仓库只新增 ba002/，理论上不该冲突 —— 请检查是否误改了上游文件")
        return 1

    log("合并完成，跑适配自检")
    import adapt as ba002_adapt
    stage = ROOT / "build_ba002/stage"
    ba002_adapt.adapt(ROOT, stage, debuggable=True)
    log(f"自检通过。当前版本 {current_version()}")
    log("下一步: python ba002/build.py")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="跟随上游更新")
    parser.add_argument("--check", action="store_true", help="只检查，不合并")
    args = parser.parse_args()
    sys.exit(check_only() if args.check else merge())


if __name__ == "__main__":
    main()
