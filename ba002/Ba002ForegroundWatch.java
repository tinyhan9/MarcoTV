// Copyright (C) 2026 tinyhan9
// SPDX-License-Identifier: GPL-3.0-only
//
// 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
// GPL-3.0-only）新增的适配层，不含上游代码。
package com.pilipala.tvhome;

import android.app.ActivityManager;
import android.app.AppOpsManager;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Process;
import android.util.Log;

import java.util.List;

/**
 * 前台包名的轮询式探测，给收不到无障碍事件的固件兜底。
 *
 * <h3>为什么需要它</h3>
 * 小米电视 4A（MiTV4A / Android 6.0.1）上，{@code HomeKeyService} 的服务能被系统绑定，
 * {@code onServiceConnected} 也跑了（日志 {@code HOME key filter ready; capabilities=8}），
 * 但 {@code onAccessibilityEvent} 一次都没被回调 —— 系统的 {@code =vc=vas=} 只把
 * {@code TYPE_WINDOW_STATE_CHANGED} 分发给它自己的两个服务。于是「按 HOME 后发现前台
 * 变成原始桌面就抢回来」这套逻辑在这台机器上永远不会触发。
 *
 * <h3>为什么轮询跑在自己的线程上</h3>
 * 第一版把轮询放在主线程的 Handler 上，实测抢回要 5 秒：主线程正忙着重建桌面，
 * 每 150 ms 一次的 binder 调用跟着排队，真机日志里出现了 2.8 秒的空档
 * （{@code 21:41:54.057 → 21:41:56.903}）。检测本身是即时的 —— 从按下 HOME 到
 * 读到 {@code com.mitv.tvhome} 只用了 39 ms —— 拖慢的是「检测到之后发不出 startActivity」。
 * 换到 {@link HandlerThread} 后两者都不再和 UI 抢主线程。
 *
 * <h3>两条探测手段，按实时性排序</h3>
 * <ol>
 *   <li>{@code getRunningAppProcesses()} —— Android 6 上仍返回**全部**进程及其
 *       importance（收窄到「只看得到自己」是 Android 7.0 才开始的）。</li>
 *   <li>{@link UsageStatsManager} —— 兜底。它的 {@code lastTimeUsed} 由
 *       UsageStatsService 延迟落盘，实测 4 秒以上，只在前者拿不到时用。</li>
 * </ol>
 *
 * <p>{@code queryUsageStats} 需要 {@code PACKAGE_USAGE_STATS} 这个 appop：
 * <pre>
 *   adb shell appops set &lt;pkg&gt; GET_USAGE_STATS allow
 * </pre>
 */
final class Ba002ForegroundWatch {

    private static final String TAG = "MarcoTVBa002Watch";

    /** 轮询间隔。150 ms 让抢占看起来是「立刻」，老硬件也扛得住。 */
    private static final long INTERVAL_MS = 150L;

    /** UsageStats 兜底路径的时间窗；只认刚刚被带到前台的记录。 */
    private static final long RECENT_MS = 2_000L;

    private final Context context;
    private final String ownPackage;

    private HandlerThread thread;
    private Handler handler;
    private final Runnable tick = this::poll;

    private volatile boolean running;
    private String lastReported;
    private boolean warnedNoPermission;
    private boolean warnedNoProcesses;

    Ba002ForegroundWatch(Context context) {
        this.context = context.getApplicationContext() != null
                ? context.getApplicationContext() : context;
        this.ownPackage = this.context.getPackageName();
    }

    void start() {
        if (running) return;
        running = true;
        thread = new HandlerThread("MarcoTVForegroundWatch");
        thread.start();
        handler = new Handler(thread.getLooper());
        handler.postDelayed(tick, INTERVAL_MS);
        Log.i(TAG, "开始轮询前台包名（独立线程）");
    }

    void stop() {
        running = false;
        if (handler != null) handler.removeCallbacks(tick);
        if (thread != null) {
            thread.quitSafely();
            thread = null;
        }
        handler = null;
    }

    private void poll() {
        if (!running) return;
        try {
            String front = foregroundPackage();
            if (front != null && !front.equals(lastReported)) {
                lastReported = front;
                if (!ownPackage.equals(front)) {
                    Log.i(TAG, "前台变成 " + front);
                    Ba002BootRelay.onForeignForeground(context, front);
                }
            }
        } catch (Throwable e) {
            Log.w(TAG, "轮询失败", e);
        } finally {
            if (running && handler != null) handler.postDelayed(tick, INTERVAL_MS);
        }
    }

    /** 当前前台的包名；两条路都判断不出来时返回 null。 */
    private String foregroundPackage() {
        String byProcesses = foregroundByImportance();
        if (byProcesses != null) return byProcesses;
        return foregroundByUsageStats();
    }

    /**
     * 用进程 importance 判断前台。
     *
     * <p>取 importance 最小的那个应用主进程。本应用绑了无障碍服务，被盖住时仍是
     * {@code IMPORTANCE_VISIBLE}（200），所以判据不是「自己够不够靠前」，而是
     * 「有没有别家比自己更靠前」—— 直接取全局最小的那个即可。
     */
    private String foregroundByImportance() {
        ActivityManager am = (ActivityManager) context.getSystemService(Context.ACTIVITY_SERVICE);
        if (am == null) return null;
        List<ActivityManager.RunningAppProcessInfo> processes;
        try {
            processes = am.getRunningAppProcesses();
        } catch (Throwable e) {
            if (!warnedNoProcesses) {
                warnedNoProcesses = true;
                Log.w(TAG, "getRunningAppProcesses 不可用，改用 UsageStats", e);
            }
            return null;
        }
        if (processes == null || processes.isEmpty()) return null;

        int bestImportance = Integer.MAX_VALUE;
        String best = null;
        for (ActivityManager.RunningAppProcessInfo p : processes) {
            if (p == null || p.processName == null) continue;
            if (p.processName.indexOf(':') >= 0) continue;  // 跳过 :remote 之类的子进程
            if (p.importance < bestImportance) {
                bestImportance = p.importance;
                best = p.processName;
            }
        }
        if (best == null) return null;
        // 连可见都没有的主进程说明这台机器上没有值得抢的前台，交给兜底路径。
        if (bestImportance > ActivityManager.RunningAppProcessInfo.IMPORTANCE_VISIBLE) return null;
        return best;
    }

    /**
     * 用 UsageStats 判断前台。只在进程列表拿不到时用：它的 lastTimeUsed
     * 落盘有延迟，不适合作为首选。
     */
    private String foregroundByUsageStats() {
        UsageStatsManager usm = (UsageStatsManager) context.getSystemService(
                Context.USAGE_STATS_SERVICE);
        if (usm == null) return null;
        if (!hasUsageAccess()) {
            if (!warnedNoPermission) {
                warnedNoPermission = true;
                Log.w(TAG, "没有使用情况访问权限，UsageStats 兜底也不可用。"
                        + "授予方式: adb shell appops set " + ownPackage
                        + " GET_USAGE_STATS allow");
            }
            return null;
        }
        long now = System.currentTimeMillis();
        List<UsageStats> stats;
        try {
            stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY,
                    now - 60_000L, now);
        } catch (Throwable e) {
            Log.w(TAG, "queryUsageStats 失败", e);
            return null;
        }
        if (stats == null || stats.isEmpty()) return null;

        String best = null;
        long bestTime = 0L;
        for (UsageStats s : stats) {
            if (s == null || s.getPackageName() == null) continue;
            long used = s.getLastTimeUsed();
            if (used > bestTime) {
                bestTime = used;
                best = s.getPackageName();
            }
        }
        if (best == null) return null;
        if (now - bestTime > RECENT_MS) return null;
        return best;
    }

    /** {@code GET_USAGE_STATS} 是否已授予。没有它 queryUsageStats 只会返回空。 */
    private boolean hasUsageAccess() {
        AppOpsManager ops = (AppOpsManager) context.getSystemService(Context.APP_OPS_SERVICE);
        if (ops == null) return false;
        try {
            // checkOpNoThrow 从 API 19 就在；unsafeCheckOpNoThrow 是 API 29 才加的，
            // 而本工程 compileSdk 是 28。
            int mode = ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS,
                    Process.myUid(), ownPackage);
            return mode == AppOpsManager.MODE_ALLOWED;
        } catch (Throwable e) {
            return false;
        }
    }
}
