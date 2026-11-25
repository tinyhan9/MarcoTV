# Copyright (C) 2026 tinyhan9
# SPDX-License-Identifier: GPL-3.0-only
#
# 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
# GPL-3.0-only）新增的适配层，不含上游代码。
#
# 离线检查 ba002 适配层的判定规则，不需要电视。
#
# 存在的理由：relay 的「是否已在前台」判定写错过两次，两次都只有装到真机上
# 打 logcat 才暴露 —— 第一次用 getRunningTasks（API 21 起只返回自己的任务，
# 永远为真），第二次用 importance（绑了无障碍服务，被盖住仍是 vis）。
# 这类逻辑错误本该在离线阶段拦住，所以把规则抽到 Ba002RelayPolicy 并在这里跑完。
#
# 用法：python ba002/test_relay.py

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ba002"))

import build as ba002_build  # noqa: E402


def log(message: str) -> None:
    print(f"[test] {message}")


def main() -> None:
    env = ba002_build.env_with_toolchain()

    from pathlib import Path as _P
    import json

    toolchain = ROOT / ".tools/toolchain.json"
    if not toolchain.is_file():
        raise SystemExit(
            "[test] 找不到 .tools/toolchain.json，先跑 python scripts/bootstrap.py"
        )
    config = json.loads(toolchain.read_text(encoding="utf-8"))
    jdk = Path(config["jdk"])
    javac = jdk / "bin" / ("javac.exe" if os.name == "nt" else "javac")
    java = jdk / "bin" / ("java.exe" if os.name == "nt" else "java")
    android_jar = Path(config["android_jar"])

    out = ROOT / "build_ba002/relay-checks"
    out.mkdir(parents=True, exist_ok=True)

    sources = [
        ROOT / "ba002/Ba002RelayPolicy.java",
        ROOT / "ba002/Ba002RelayChecks.java",
    ]
    log("编译")
    subprocess.run(
        [str(javac), "-encoding", "UTF-8", "-classpath", str(android_jar),
         "-d", str(out), *[str(s) for s in sources]],
        check=True, env=env,
    )

    log("运行")
    result = subprocess.run(
        [str(java), "-classpath", str(out), "com.pilipala.tvhome.Ba002RelayChecks"],
        check=True, capture_output=True, text=True, timeout=60, env=env,
    )
    print(result.stdout.rstrip())

    passes = sum(1 for line in result.stdout.splitlines() if line.startswith("PASS "))
    log(f"{passes} 项通过")


if __name__ == "__main__":
    main()
