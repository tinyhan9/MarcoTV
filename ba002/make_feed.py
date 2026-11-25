# SPDX-License-Identifier: GPL-3.0-only
#
# 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
# GPL-3.0-only）新增的适配层，不含上游代码。
#
# 生成更新源用的 feed 文件（docs/updates/ba002-stable.json）。
#
# 为什么要自己生成而不是复用上游的 make_update_feed.py：上游那个脚本把包名
# 写死成 com.pilipala.tvhome，并且强制要求 URL 是 Pilipala9919 的 release 路径，
# 本分支两者都不同，改了原脚本会破坏上游自己的发布流程。所以另写一份。
#
# 用法：
#   python ba002/make_feed.py --apk dist-ba002/MarcoTV-0.21.3-BA002.apk \
#                             --version 0.21.3 --notes release_notes.md
#
# 输出 docs/updates/ba002-stable.json。发布顺序很重要：
#   1. 先把 APK 传到 GitHub Release（tag v<版本>-ba002）
#   2. 再提交并推送这个 json
# 反过来的话，电视会先看到新版本号、下载 404。

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ba002"))

import adapt as ba002_adapt  # noqa: E402

MAX_NOTES = 8000


def log(message: str) -> None:
    print(f"[feed] {message}")


def aapt2() -> Path:
    import json as _json

    toolchain = ROOT / ".tools/toolchain.json"
    if not toolchain.is_file():
        raise SystemExit("[feed] 找不到 .tools/toolchain.json，先跑 python scripts/bootstrap.py")
    config = _json.loads(toolchain.read_text(encoding="utf-8"))
    path = Path(config["build_tools"]) / ("aapt2.exe" if sys.platform == "win32" else "aapt2")
    if not path.is_file():
        raise SystemExit(f"[feed] 找不到 aapt2: {path}")
    return path


def read_identity(apk: Path) -> tuple[str, int, int]:
    """读出包名、versionCode、minSdk，确认是本分支的包而不是官方包。"""
    output = subprocess.check_output(
        [str(aapt2()), "dump", "badging", str(apk)],
        text=True, encoding="utf-8", errors="replace",
    )
    package = re.search(r"package: name='([^']+)' versionCode='(\d+)'", output)
    sdk = re.search(r"(?:minSdkVersion|sdkVersion):'(\d+)'", output)
    if not package or not sdk:
        raise SystemExit("[feed] 读不出 APK 身份")
    name, code = package.group(1), int(package.group(2))
    if name != ba002_adapt.NEW_PKG:
        raise SystemExit(
            f"[feed] 包名是 {name}，不是本分支的 {ba002_adapt.NEW_PKG}。\n"
            "       别把官方包喂进来 —— 官方包签名不同，电视端会拒绝安装。"
        )
    return name, code, int(sdk.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(description="生成本分支的更新 feed")
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--version", required=True, help="版本号，与上游对齐，例如 0.21.3")
    parser.add_argument("--notes", type=Path, required=True, help="发布说明 markdown")
    parser.add_argument("--preview", action="store_true", help="生成 preview 频道而不是 stable")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.]+)?", args.version):
        raise SystemExit(f"[feed] 版本号格式不对: {args.version}")

    apk = args.apk.resolve()
    if not apk.is_file():
        raise SystemExit(f"[feed] 找不到 {apk}")

    name, code, min_sdk = read_identity(apk)
    notes = args.notes.read_text(encoding="utf-8")
    if len(notes) > MAX_NOTES:
        log(f"说明 {len(notes)} 字符，截到 {MAX_NOTES}")
        notes = notes[:MAX_NOTES]

    filename = f"MarcoTV-{args.version}-BA002.apk"
    if apk.name != filename:
        raise SystemExit(f"[feed] APK 文件名应为 {filename}，实际是 {apk.name}")

    url = (f"https://github.com/{ba002_adapt.REPO_OWNER}/{ba002_adapt.REPO_NAME}"
           f"/releases/download/v{args.version}-ba002/{filename}")
    sha = hashlib.sha256(apk.read_bytes()).hexdigest()

    channel = "preview" if args.preview else "stable"
    output = args.output or (ROOT / "docs/updates" / f"ba002-{channel}.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": 1,
        # 上游 UpdateManager 用它判断 feed 是否属于本版本；空值等同于 standard
        "edition": "standard",
        "versionCode": code,
        "versionName": args.version,
        "minSdk": min_sdk,
        "size": apk.stat().st_size,
        "sha256": sha,
        "url": url,
        "prerelease": args.preview,
        "notes": notes,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log(f"已写 {output.relative_to(ROOT)}")
    log(f"  包名       {name}")
    log(f"  版本       {args.version} (code {code})")
    log(f"  大小       {payload['size']:,} 字节")
    log(f"  SHA256     {sha}")
    log(f"  下载地址   {url}")
    log("")
    log("发布顺序：先传 APK 到 Release，再提交这个 json。")


if __name__ == "__main__":
    main()
