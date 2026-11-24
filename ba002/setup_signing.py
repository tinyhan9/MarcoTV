# Copyright (C) 2026 tinyhan9
# SPDX-License-Identifier: GPL-3.0-only
#
# 生成本仓库固定的签名库。只需跑一次，之后请把 private/ 整个备份到离线介质。
#
# 为什么仓库不直接带一把现成的钥匙：
#   Android 的增量升级依赖「同一包名 + 同一签名」。如果签名库丢了或者每次重建，
#   已经装过的用户就再也收不到覆盖升级，只能卸载重装（会丢壁纸和设置）。
#   仓库里不放私钥，是为了不让任何人都能签出冒充本分支的 APK。
#
# 用法：
#   python ba002/setup_signing.py
#   python ba002/setup_signing.py --dname "CN=Someone, OU=Marco TV BA002"
#
# 生成后设置口令（可选，默认 android）：
#   set BA002_STORE_PASSWORD=你的口令

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYSTORE = ROOT / "private" / "ba002.p12"
ALIAS = os.environ.get("BA002_KEY_ALIAS", "marco")
PASSWORD = os.environ.get("BA002_STORE_PASSWORD", "android")


def main() -> None:
    jdk = os.environ.get("JAVA_HOME")
    if not jdk:
        raise SystemExit("需要 JAVA_HOME")
    keytool = Path(jdk) / "bin" / ("keytool.exe" if os.name == "nt" else "keytool")
    if not keytool.is_file():
        raise SystemExit(f"找不到 {keytool}")

    if KEYSTORE.is_file():
        print(f"签名库已存在，保持不动：{KEYSTORE}")
        print("如果确认要重建，请先删掉它 —— 但重建后已有用户无法覆盖升级。")
        return

    dname = "CN=Marco TV BA002, OU=Marco TV, O=tinyhan9"
    if "--dname" in sys.argv:
        dname = sys.argv[sys.argv.index("--dname") + 1]

    KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(keytool), "-genkeypair",
            "-keystore", str(KEYSTORE),
            "-storetype", "PKCS12",
            "-alias", ALIAS,
            "-storepass", PASSWORD,
            "-keypass", PASSWORD,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-dname", dname,
        ],
        check=True,
    )
    print(f"已生成 {KEYSTORE}")
    print(f"  别名: {ALIAS}")
    print(f"  口令: {PASSWORD}    （用 BA002_STORE_PASSWORD 覆盖默认值）")
    print()
    print("下一步：把 private/ 备份到离线介质。丢了就无法给已装用户发升级。")


if __name__ == "__main__":
    main()
