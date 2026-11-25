# SPDX-License-Identifier: GPL-3.0-only
#
# 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
# GPL-3.0-only）新增的适配层，不含上游代码。
#
# 离线检查更新源适配，不需要电视，也不需要网络。
#
# 为什么要有：换源要同时改五处，漏一处的表现分别是
#   feed 拉不到 / APK 地址被 apkUrl 拒绝 / 重定向被 transferUrl 拒绝，
# 三种都只有装到电视上点「检查更新」才暴露。这里在 JVM 上全跑一遍。
#
# 用法：python ba002/test_update_source.py
#
# 关键点：检查对象是**改过之后**的 UpdatePolicy，所以先让 adapt.py 造出 stage，
# 再编译 stage 里的那份源码。检查类自身也要换成新包名，否则它在
# com.pilipala.tvhome 下找不到同名包的 UpdatePolicy。

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ba002"))

import adapt as ba002_adapt  # noqa: E402


def log(message: str) -> None:
    print(f"[test] {message}")


def main() -> None:
    toolchain = ROOT / ".tools/toolchain.json"
    if not toolchain.is_file():
        raise SystemExit("[test] 找不到 .tools/toolchain.json，先跑 python scripts/bootstrap.py")

    config = json.loads(toolchain.read_text(encoding="utf-8"))
    jdk = Path(config["jdk"])
    javac = jdk / "bin" / ("javac.exe" if os.name == "nt" else "javac")
    java = jdk / "bin" / ("java.exe" if os.name == "nt" else "java")
    android_jar = Path(config["android_jar"])

    stage = (ROOT / "build_ba002/stage").resolve()
    if not (stage / "app/src/main/AndroidManifest.xml").is_file():
        log("stage 不存在，先适配")
        ba002_adapt.adapt(ROOT, stage, debuggable=True)

    pkg_dir = stage / "app/src/main/java" / ba002_adapt.NEW_PKG.replace(".", "/")
    if not (pkg_dir / "UpdatePolicy.java").is_file():
        raise SystemExit(f"[test] stage 里没有 UpdatePolicy.java: {pkg_dir}")

    # 检查类复制到临时目录并改成新包名：它要调用 New_PKG 包里的 UpdatePolicy
    out = ROOT / "build_ba002/update-checks"
    out.mkdir(parents=True, exist_ok=True)
    checks_dir = out / "src" / ba002_adapt.NEW_PKG.replace(".", "/")
    checks_dir.mkdir(parents=True, exist_ok=True)
    checks = checks_dir / "Ba002UpdateChecks.java"
    text = io.open(ROOT / "ba002/Ba002UpdateChecks.java", encoding="utf-8").read()
    text = text.replace(f"package {ba002_adapt.OLD_PKG};", f"package {ba002_adapt.NEW_PKG};")
    io.open(checks, "w", encoding="utf-8", newline="").write(text)

    sources = [
        pkg_dir / "BuildEdition.java",
        pkg_dir / "UpdatePolicy.java",
        checks,
    ]

    log("编译（用 stage 里改过的 UpdatePolicy）")
    subprocess.run(
        [str(javac), "-encoding", "UTF-8", "-classpath", str(android_jar),
         "-d", str(out / "classes"), *[str(s) for s in sources]],
        check=True,
    )

    log("运行")
    result = subprocess.run(
        [str(java), "-classpath", str(out / "classes"),
         f"{ba002_adapt.NEW_PKG}.Ba002UpdateChecks"],
        check=True, capture_output=True, text=True, timeout=60,
    )
    print(result.stdout.rstrip())

    passes = sum(1 for line in result.stdout.splitlines() if line.startswith("PASS "))
    log(f"{passes} 项通过")


if __name__ == "__main__":
    main()
