# Copyright (C) 2026 tinyhan9
# SPDX-License-Identifier: GPL-3.0-only
# Marco TV 由 Pilipala 开发（https://github.com/Pilipala9919/MarcoTV）；本文件是本分支新增的适配层。
#
# 极光盒子 7X（BA002）设备侧部署脚本
#
# 只做一件事：把已经装好的 APK 设成能长期生效的默认桌面。**不改 APK**，
# 全部是设备上的设置与角色授予。
#
# 为什么需要这一层：BA002 的固件把「设置默认桌面」这条路堵得很死，
#   - pm set-home-activity / pm enable / pm disable-user：硬编码拒绝非 uid 2000，
#     应用和 adb shell 都会被 "Error: User no Permission !" 顶回来
#   - 没有可用的系统桌面选择页（部分固件版本），应用内「一键启用」走不通
#   - com.skyworthdigital.skycommonpropertymanager 每次开机把
#     enable_launcher_components / homewhitelist / com.forestdata.* 写回出厂值
#   - PhoneWindowManager 的 DisplayHomeButtonHandler 在
#     persist.sys.launcher.mode=plauncher 时会主动 clearPackagePreferredActivities，
#     把默认桌面抢回厂商桌面
#
# 能长期生效的四层（缺任一层都会退化，实测过）：
#   1. 包名命中 enable_launcher_components 的前缀白名单 —— 编译期决定（见 adapt.py）
#   2. cmd role add-role-holder android.app.role.HOME <pkg>
#      这条路没有被 uid 门拦住，且写入 /data/system/roles.xml，重启不丢
#   3. setprop persist.sys.launcher.mode custom
#      persist 属性，跨重启；让看门狗不再抢
#   4. 无障碍服务 <pkg>/.HomeKeyService
#      HOME 键在系统解析之前的拦截层
#
# 用法：
#   python ba002/device.py status            # 只看现状，不改任何东西
#   python ba002/device.py apply             # 把四层全部装上
#   python ba002/device.py repair            # 只补掉队的层（开机后用）
#   python ba002/device.py test              # 压测 HOME 键，输出失败次数

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

PACKAGE = "com.xiaopaitech.plauncher.marcotv"
HOME_ALIAS = f"{PACKAGE}/.HomeActivity"
ACCESSIBILITY = f"{PACKAGE}/{PACKAGE}.HomeKeyService"
COMPAT_ACCESSIBILITY = "com.ktcp.aiagent/com.ktcp.tvagent.service.VoiceAccessibilityService"
HOME_INTENT_QUERY = "-a android.intent.action.MAIN -c android.intent.category.HOME"


def adb(*args: str, serial: str | None = None, check: bool = False) -> str:
    command = ["adb"]
    if serial:
        command += ["-s", serial]
    command += list(args)
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise SystemExit(f"adb 失败: {' '.join(command)}\n{result.stderr}")
    return (result.stdout or "").strip()


def shell(command: str, serial: str | None = None) -> str:
    return adb("shell", command, serial=serial)


def log(message: str) -> None:
    print(f"[device] {message}")


def resolve_serial(explicit: str | None) -> str:
    if explicit:
        return explicit
    devices = adb("devices")
    serials = [line.split("\t")[0] for line in devices.splitlines()[1:] if "\tdevice" in line]
    if not serials:
        raise SystemExit(
            "[device] 没有已连接的设备。\n"
            "  USB: 直接插线即可。\n"
            "  网络: adb connect <盒子IP>:5555  （BA002 的 IP 每次重启可能变，按 MAC 找）"
        )
    return serials[0]


# ---------------------------------------------------------------- 各层读写

def layer_role(serial: str) -> str:
    return shell("dumpsys role", serial=serial)


def role_held(serial: str) -> bool:
    return f"holders={PACKAGE}" in layer_role(serial)


def grant_role(serial: str) -> None:
    shell(f"cmd role add-role-holder android.app.role.HOME {PACKAGE}", serial=serial)


def layer_mode(serial: str) -> str:
    return shell("getprop persist.sys.launcher.mode", serial=serial)


def set_mode(serial: str) -> None:
    # custom 让 PhoneWindowManager 的看门狗不接管 HOME；其它值（尤其 plauncher）
    # 会触发 clearPackagePreferredActivities，把默认桌面抢回厂商桌面
    shell("setprop persist.sys.launcher.mode custom", serial=serial)


def layer_accessibility(serial: str) -> str:
    return shell("cmd settings get secure enabled_accessibility_services", serial=serial)


def set_accessibility(serial: str) -> None:
    current = layer_accessibility(serial)
    if current in ("", "null"):
        value = ACCESSIBILITY
    elif ACCESSIBILITY in current:
        value = current
    else:
        value = f"{current}:{ACCESSIBILITY}"
    shell(f"cmd settings put secure enabled_accessibility_services '{value}'", serial=serial)
    shell("cmd settings put secure accessibility_enabled 1", serial=serial)


def grant_secure_settings(serial: str) -> None:
    # 应用需要这个权限才能在自己的「Home 兼容」页面里自愈无障碍设置
    adb("shell", f"pm grant {PACKAGE} android.permission.WRITE_SECURE_SETTINGS", serial=serial)


def resolved_home(serial: str) -> str:
    out = shell(f"cmd package resolve-activity --brief {HOME_INTENT_QUERY}", serial=serial)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def focused_window(serial: str) -> str:
    out = shell("dumpsys window", serial=serial)
    for line in out.splitlines():
        if "mCurrentFocus" in line:
            return line.strip()
    return ""


def home_candidates(serial: str) -> list[str]:
    out = shell(f"pm query-activities {HOME_INTENT_QUERY}", serial=serial)
    return [line.strip() for line in out.splitlines() if line.strip().startswith("packageName=")]


# ---------------------------------------------------------------- 子命令

def cmd_status(serial: str) -> int:
    print("=== 版本 ===")
    for line in shell(f"dumpsys package {PACKAGE}", serial=serial).splitlines():
        if "versionName" in line or "versionCode" in line:
            print("  " + line.strip())
            break

    print("=== 四层状态 ===")
    held = role_held(serial)
    mode = layer_mode(serial)
    a11y = layer_accessibility(serial)
    print(f"  HOME role        {'OK' if held else '缺失'}  ({'holders=' + PACKAGE if held else '没有持有'})")
    print(f"  launcher.mode    {'OK' if mode == 'custom' else '异常'}  ({mode or '空'})")
    print(f"  HomeKeyService   {'OK' if ACCESSIBILITY in a11y else '缺失'}")
    print(f"  包名前缀白名单    OK（编译期固定为 com.xiaopaitech.plauncher.*）")

    print("=== 当前解析 ===")
    print(f"  resolve  {resolved_home(serial)}")
    print(f"  前台     {focused_window(serial)}")

    print("=== HOME 候选 ===")
    for c in home_candidates(serial):
        print("  " + c)
    members = [c for c in home_candidates(serial) if PACKAGE in c]
    if len(members) > 1:
        print("  ⚠ 本包声明了多个 HOME 组件 —— 会让每次按 HOME 都弹选择框")

    healthy = held and mode == "custom" and ACCESSIBILITY in a11y and len(members) == 1
    return 0 if healthy else 1


def cmd_apply(serial: str) -> int:
    log("授予 HOME 角色")
    grant_role(serial)
    log("设置 persist.sys.launcher.mode=custom")
    set_mode(serial)
    log("授予 WRITE_SECURE_SETTINGS（应用自愈用）")
    grant_secure_settings(serial)
    log("启用 HomeKeyService 无障碍服务")
    set_accessibility(serial)
    time.sleep(3)
    log("把桌面拉到前台")
    shell(f"am start -n {HOME_ALIAS}", serial=serial)
    time.sleep(2)
    return cmd_status(serial)


def cmd_repair(serial: str) -> int:
    """开机后补掉队的层。每次都做，幂等。"""
    changed = []

    if not role_held(serial):
        grant_role(serial)
        changed.append("HOME role")

    if layer_mode(serial) != "custom":
        set_mode(serial)
        changed.append("launcher.mode")

    if ACCESSIBILITY not in layer_accessibility(serial):
        set_accessibility(serial)
        changed.append("HomeKeyService")

    if changed:
        log("已修复: " + ", ".join(changed))
        time.sleep(3)
    else:
        log("四层都在，无需修复")
    return cmd_status(serial)


def cmd_test(serial: str, rounds: int) -> int:
    log(f"连按 HOME {rounds} 次")
    failures = 0
    for index in range(1, rounds + 1):
        shell("input keyevent KEYCODE_HOME", serial=serial)
        time.sleep(0.7)
        focus = focused_window(serial)
        if PACKAGE not in focus:
            failures += 1
            print(f"  [{index}] 失败: {focus}")
    print(f"结果: {rounds} 次里失败 {failures} 次")
    return 0 if failures == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="极光盒子 7X（BA002）设备侧部署")
    parser.add_argument("action", choices=["status", "apply", "repair", "test"])
    parser.add_argument("--serial", help="adb 序列号，多台设备时必填")
    parser.add_argument("--rounds", type=int, default=20, help="test 的按键次数，默认 20")
    args = parser.parse_args()

    serial = resolve_serial(args.serial)
    log(f"设备: {serial}")

    if args.action == "status":
        sys.exit(cmd_status(serial))
    if args.action == "apply":
        sys.exit(cmd_apply(serial))
    if args.action == "repair":
        sys.exit(cmd_repair(serial))
    if args.action == "test":
        sys.exit(cmd_test(serial, args.rounds))


if __name__ == "__main__":
    main()
