// Copyright (C) 2026 tinyhan9
// SPDX-License-Identifier: GPL-3.0-only
//
// 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
// GPL-3.0-only）新增的适配层，不含上游代码。
package com.pilipala.tvhome;

/**
 * 开机抢前台的判定规则，抽成不依赖 Android 的纯逻辑，供离线检查直接调用。
 *
 * <p>为什么要抽出来：这套判定第一版用了 {@code getRunningTasks(1)}，从 API 21 起它
 * 只返回调用者自己的任务，于是「是否已在前台」永远为真，relay 一次都没真正重放过。
 * 第二版换了 {@code getRunningAppProcesses()} 的 importance，又因为本应用绑定了无障碍
 * 服务，被盖住时进程仍是 {@code vis}（importance 200、oom_adj 100），还是误判。
 *
 * <p>两次都是靠真机 logcat 才发现的 —— 这种「只有换到硬件上才暴露」的判定不该这么验。
 * 把规则抽成本类之后，{@code Ba002RelayChecks} 可以在 JVM 上把所有分支跑一遍，
 * 真机只用来确认最终效果。
 *
 * <p>注意：判定输入是「本应用有没有 Activity 处于 resumed」，这个信号来自
 * {@code Application.ActivityLifecycleCallbacks}，不依赖任何权限或隐藏 API。
 */
final class Ba002RelayPolicy {

    /** 开机后的重放时点（毫秒）。厂商桌面在 BOOT_COMPLETED 后约 14 秒抢前台。 */
    static final long[] SLOTS = {2_000L, 6_000L, 12_000L, 18_000L, 25_000L, 35_000L, 50_000L};

    /** importance 在这个值以内算「自己在前台」。保留给调用方做交叉判断。 */
    static final int FOREGROUND_IMPORTANCE_LIMIT = 200;

    private Ba002RelayPolicy() { }

    /**
     * 该不该重放 HOME。
     *
     * @param oursResumed 本应用当前是否有 Activity 处于 resumed
     * @param lifecycleTracking 生命周期监听是否注册成功
     * @return true = 需要重放；false = 跳过
     */
    static boolean shouldReplay(boolean oursResumed, boolean lifecycleTracking) {
        // 监听没注册上就拿不到可靠信号，此时宁可多抢一次：
        // 多按一次 HOME 的代价（桌面闪一下）远小于「开机停在厂商桌面」。
        if (!lifecycleTracking) return true;
        return !oursResumed;
    }

    /** 应用是否在前台：importance 数值越小越靠前，<= 200 表示可见或更好。 */
    static boolean foregroundByImportance(int importance) {
        return importance > 0 && importance <= FOREGROUND_IMPORTANCE_LIMIT;
    }

    /** 第 slot 个时点距 BOOT_COMPLETED 的毫秒数。越界返回 -1。 */
    static long delayFor(int slot) {
        if (slot < 0 || slot >= SLOTS.length) return -1;
        return SLOTS[slot];
    }

    /** 时点表是否覆盖了厂商抢前台的时间窗（+14s 附近）。 */
    static boolean coversVendorSteal(long vendorStealMillis) {
        if (vendorStealMillis <= 0) return false;
        long last = SLOTS[SLOTS.length - 1];
        if (last <= vendorStealMillis) return false;
        // 抢走之后至少还要有一个时点能把它抢回来
        for (long slot : SLOTS) {
            if (slot > vendorStealMillis) return true;
        }
        return false;
    }
}
