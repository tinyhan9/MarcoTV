# Copyright (C) 2026 tinyhan9
# SPDX-License-Identifier: GPL-3.0-only
#
# 极光盒子 7X（BA002）构建脚本
#
# 流程：adapt.py 造 stage → 调上游 scripts/build.py 编译 stage → 签名 → 输出到
#       dist-ba002/
#
# 环境变量（都有默认值，只在本机开发时才需要显式设）：
#   JAVA_HOME            JDK 根目录
#   ANDROID_SDK_ROOT     Android SDK 根目录
#   MARCOTV_BUILD_TOOLS  build-tools 版本目录名，默认 36.0.0
#   BA002_KEYSTORE       签名库路径，默认 private/ba002.p12
#   BA002_KEY_ALIAS      签名库别名，默认 marco
#   BA002_STORE_PASSWORD 签名库口令，默认 android（仅本地开发）
#
# 用法：
#   python ba002/build.py                 # 出适配版 APK
#   python ba002/build.py --no-debuggable # 出不带 debuggable 的正式版
#   python ba002/setup_signing.py         # 首次生成签名库（只需一次，之后要备份）

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ba002"))

import adapt as ba002_adapt  # noqa: E402

DEFAULT_KEYSTORE = "private/ba002.p12"
DEFAULT_ALIAS = "marco"
DEFAULT_PASSWORD = "android"


def log(message: str) -> None:
    print(f"[build] {message}")


def env_with_toolchain() -> dict:
    env = dict(os.environ)
    jdk = env.get("JAVA_HOME")
    sdk = env.get("ANDROID_SDK_ROOT") or env.get("ANDROID_HOME")
    if not jdk or not sdk:
        raise SystemExit(
            "[build] 需要 JAVA_HOME 与 ANDROID_SDK_ROOT。\n"
            "  这两个变量只用于构建，不会写进 APK。"
        )
    env["JAVA_HOME"] = jdk
    env["ANDROID_SDK_ROOT"] = sdk
    env["ANDROID_HOME"] = sdk
    env.setdefault("MARCOTV_BUILD_TOOLS", "36.0.0")
    env["PATH"] = str(Path(jdk) / "bin") + os.pathsep + env.get("PATH", "")

    # 签名库：固定用本仓库自己的，避免每次构建都现生成一把新钥匙
    # （新钥匙的指纹每次都变，用户就没法做增量升级）
    keystore = Path(env.get("BA002_KEYSTORE") or (ROOT / DEFAULT_KEYSTORE))
    if not keystore.is_absolute():
        keystore = (ROOT / keystore).resolve()
    env["MARCOTV_KEYSTORE"] = str(keystore)
    env["MARCOTV_KEY_ALIAS"] = env.get("BA002_KEY_ALIAS") or DEFAULT_ALIAS
    env.setdefault("MARCOTV_STORE_PASSWORD", env.get("BA002_STORE_PASSWORD") or DEFAULT_PASSWORD)
    if not keystore.is_file():
        log(f"警告：签名库 {keystore} 不存在，上游会生成一把一次性的开发钥匙")
        log("      正式发布前请先跑 python ba002/setup_signing.py 并备份私钥")
    else:
        log(f"签名库: {keystore}")
    return env


def run(args, cwd: Path, env: dict) -> None:
    log("执行: " + " ".join(str(a) for a in args))
    subprocess.run([str(a) for a in args], cwd=str(cwd), env=env, check=True)


def read_version(stage: Path) -> str:
    import xml.etree.ElementTree as ET

    manifest = stage / "app/src/main/AndroidManifest.xml"
    root = ET.parse(manifest).getroot()
    version = root.get("{http://schemas.android.com/apk/res/android}versionName")
    if not version:
        raise SystemExit("[build] manifest 里没有 versionName")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description="构建极光盒子 7X 适配版 Marco TV")
    parser.add_argument("--no-debuggable", action="store_true", help="不打开 android:debuggable")
    parser.add_argument("--stage", default="build_ba002/stage", help="stage 目录")
    parser.add_argument("--skip-adapt", action="store_true", help="复用已有 stage，不重新适配")
    args = parser.parse_args()

    env = env_with_toolchain()
    stage = (ROOT / args.stage).resolve()

    if args.skip_adapt:
        if not (stage / "app/src/main/AndroidManifest.xml").is_file():
            raise SystemExit(f"[build] --skip-adapt 但 {stage} 不是有效 stage")
        log("跳过适配，复用现有 stage")
    else:
        ba002_adapt.adapt(ROOT, stage, debuggable=not args.no_debuggable)

    version = read_version(stage)
    log(f"版本: {version}")

    # 复用上游的构建脚本：aapt2 → javac → d8 → zipalign → apksigner，逻辑一条不抄
    run([sys.executable, "scripts/build.py"], cwd=stage, env=env)

    built = stage / "dist" / f"MarcoTV-{version}.apk"
    if not built.is_file():
        raise SystemExit(f"[build] 上游构建没有产出 {built}")

    out_dir = ROOT / "dist-ba002"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"MarcoTV-{version}-BA002.apk"
    shutil.copy2(built, out)

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (out_dir / (out.name + ".sha256")).write_text(f"{digest}  {out.name}\n", encoding="utf-8")

    log("完成")
    log(f"  文件: {out}")
    log(f"  SHA256: {digest}")
    log(f"  大小: {out.stat().st_size:,} 字节")
    log("  安装: adb install -r " + out.name)


if __name__ == "__main__":
    main()
