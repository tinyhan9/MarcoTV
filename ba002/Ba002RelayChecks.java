// Copyright (C) 2026 tinyhan9
// SPDX-License-Identifier: GPL-3.0-only
//
// 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
// GPL-3.0-only）新增的适配层，不含上游代码。
package com.pilipala.tvhome;

/**
 * 离线检查 Ba002RelayPolicy 的判定规则。不需要电视、不需要 Android 运行时。
 *
 * <p>这两次真机上才暴露的 bug 都属于「逻辑本身错了」，本该在这里被抓住：
 * <ol>
 *   <li>用 getRunningTasks 判定前台 —— 永远返回自己，需保证「不在前台时必须重放」
 *   <li>用 importance 判定前台 —— 无障碭服务让进程保持 vis，需保证不看这个值也能判对
 * </ol>
 */
public final class Ba002RelayChecks {

    static int passed;

    static void check(String label, boolean good) {
        if (!good) throw new AssertionError(label);
        passed++;
        System.out.println("PASS " + label);
    }

    public static void main(String[] args) {
        // ---- 核心判据：只有「真的在前台」才跳过 ----
        check("resumed_skips_replay", !Ba002RelayPolicy.shouldReplay(true, true));
        check("paused_replays_home", Ba002RelayPolicy.shouldReplay(false, true));

        // 监听没注册上时必须无条件重放 —— 这是第一版 getRunningTasks 那种
        // 「拿不到可靠信号却当成已经在前台」的反面。
        check("no_tracking_always_replays", Ba002RelayPolicy.shouldReplay(true, false));
        check("no_tracking_replays_when_paused", Ba002RelayPolicy.shouldReplay(false, false));

        // ---- importance 只作为交叉参考，不能单独决定跳过 ----
        check("importance_foreground", Ba002RelayPolicy.foregroundByImportance(100));
        check("importance_visible_is_foreground", Ba002RelayPolicy.foregroundByImportance(200));
        check("importance_service_is_not_foreground", !Ba002RelayPolicy.foregroundByImportance(300));
        check("importance_cached_is_not_foreground", !Ba002RelayPolicy.foregroundByImportance(900));
        check("importance_unknown_is_not_foreground", !Ba002RelayPolicy.foregroundByImportance(0));

        // ---- 时点表必须覆盖厂商抢前台的时间窗 ----
        // 实测 BA002 上 BootUpReceiver 在 BOOT_COMPLETED 后约 14 秒抢前台。
        check("covers_measured_vendor_steal_14s", Ba002RelayPolicy.coversVendorSteal(14_000L));
        check("covers_early_vendor_steal_3s", Ba002RelayPolicy.coversVendorSteal(3_000L));
        check("covers_late_vendor_steal_40s", Ba002RelayPolicy.coversVendorSteal(40_000L));
        check("rejects_steal_after_last_slot", !Ba002RelayPolicy.coversVendorSteal(60_000L));
        check("rejects_invalid_steal_time", !Ba002RelayPolicy.coversVendorSteal(0));

        // ---- 时点表本身 ----
        check("slots_non_empty", Ba002RelayPolicy.SLOTS.length > 0);
        check("slots_ascending", ascending(Ba002RelayPolicy.SLOTS));
        check("first_slot_is_early", Ba002RelayPolicy.SLOTS[0] <= 3_000L);
        check("last_slot_late_enough", Ba002RelayPolicy.SLOTS[Ba002RelayPolicy.SLOTS.length - 1] >= 45_000L);
        check("slot_index_in_range", Ba002RelayPolicy.delayFor(0) == Ba002RelayPolicy.SLOTS[0]);
        check("slot_index_out_of_range", Ba002RelayPolicy.delayFor(-1) == -1L);
        check("slot_index_past_end", Ba002RelayPolicy.delayFor(Ba002RelayPolicy.SLOTS.length) == -1L);

        // 每个时点都必须晚于开机完成，否则会在 BOOT_COMPLETED 之前白跑
        boolean allPositive = true;
        for (long slot : Ba002RelayPolicy.SLOTS) if (slot <= 0) allPositive = false;
        check("all_slots_positive", allPositive);

        System.out.println("OK " + passed + " BA002 relay policy checks");
    }

    static boolean ascending(long[] values) {
        for (int i = 1; i < values.length; i++) if (values[i] <= values[i - 1]) return false;
        return true;
    }
}
