// Copyright (C) 2026 tinyhan9
// SPDX-License-Identifier: GPL-3.0-only
//
// 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
// GPL-3.0-only）新增的适配层，不含上游代码。
package com.pilipala.tvhome;

import android.app.Activity;
import android.app.Application;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

/**
 * 开机把前台抢回来，适配两种固件。
 *
 * <h3>极光盒子 7X（BA002 / Android 11）</h3>
 * 固件自带的 {@code com.xiaopaitech.wallpaperlauncher} 有一个 BootUpReceiver，
 * 在 {@code BOOT_COMPLETED} 之后约 14 秒以 uid 1000 调 {@code startActivity}，
 * 把自己的 LauncherActivity 顶到前台。本应用虽然是 HOME role 的持有者，前台仍被盖掉。
 * 这里的对策是重放 HOME 意图 —— 本应用就是 HOME，重放即等于把自己拉回前台。
 *
 * <h3>小米电视 4A（MiTV4A / Android 6.0.1）</h3>
 * 这台固件换不了默认桌面：{@code PackageManagerService.chooseBestActivity} 里
 * 小米加了钩子，第三方包要过关 {@code MitvSettings.isThirdpartyHomeAllowed} 白名单，
 * 而白名单文件 {@code /data/system/app_control.xml} 属于 system 且 SELinux 拦着。
 * 于是 HOME 意图永远解析到 {@code com.mitv.tvhome}。Android 6 还没有后台启动
 * Activity 的限制，所以这台走「显式启动自己」这条路，不碰 HOME。
 *
 * <p>两条路由 {@link #homeResolvesToUs} 在运行时选一次：HOME 解析到自己就重放 HOME，
 * 否则显式启动自己的入口 Activity。
 *
 * <p>开机窗口之外，小米这台还要持续盯前台：{@link Ba002ForegroundWatch} 轮询
 * 使用情况统计，一旦前台变成别人就再抢一次。两只手都要有 —— 开机时靠时点表，
 * 之后靠轮询。
 *
 * <p>判定规则见 {@link Ba002RelayPolicy}，那里抽成了不依赖 Android 的纯逻辑，
 * 由 {@code ba002/test_relay.py} 在 JVM 上跑全部分支。本类只负责接线。
 *
 * <p>为什么不用 {@code getRunningTasks()}：从 API 21 起它只返回调用者自己的任务，
 * 「是否已在前台」永远为真。为什么不用进程 importance：本应用绑定了无障碍服务，
 * 被盖住时进程仍是 {@code vis}（importance 200、oom_adj 100），也是误判。
 */
public final class Ba002BootRelay extends BroadcastReceiver {

    private static final String TAG = "MarcoTVBa002Relay";

    /** 本应用是否有 Activity 处于 resumed。只在主线程读写。 */
    private static volatile boolean resumed;
    private static boolean tracking;

    /** HOME 是否解析到本应用。null = 还没探过；探一次就定。 */
    private static Boolean homeResolvesToUs;

    /** 前台轮询器。开机后才起，抢不到就停。 */
    private static Ba002ForegroundWatch watch;

    /** 两次抢前台之间的最小间隔，避免和应用自己切页面打架。 */
    private static final long RECLAIM_COOLDOWN_MS = 800L;
    private static long lastReclaim;

    @Override public void onReceive(Context context, Intent intent) {
        if (context == null || intent == null) return;
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) return;

        final Context app = context.getApplicationContext() != null
                ? context.getApplicationContext() : context;
        trackForeground(app);

        Handler handler = new Handler(Looper.getMainLooper());
        for (int slot = 0; slot < Ba002RelayPolicy.SLOTS.length; slot++) {
            final int index = slot;
            handler.postDelayed(() -> fire(app, index), Ba002RelayPolicy.delayFor(index));
        }
        Log.i(TAG, "已排入 " + Ba002RelayPolicy.SLOTS.length + " 个抢回前台的时点");

        // HOME 不是自己时才需要一直盯：是自己的话，重放 HOME 就能回来，
        // 而固件也不会让别人来抢。
        if (!homeIsOurs(app)) startWatch(app);
    }

    /**
     * 应用进程起来了就调一次：HOME 不是自己时开始盯前台。
     *
     * <p>为什么不能只靠 BOOT_COMPLETED：{@code am broadcast} 发不进系统广播，
     * 真机验证时只能重启；而用户重装、应用被系统回收后重启进程，都不再走
     * 开机广播。放在 Application.onCreate 里，任何一次进程启动都会接上。
     */
    static void maybeStartWatch(Context context) {
        if (context == null) return;
        Context app = context.getApplicationContext() != null
                ? context.getApplicationContext() : context;
        trackForeground(app);
        if (!homeIsOurs(app)) startWatch(app);
    }

    /** 注册一次即可；进程重启后重新注册。 */
    private static void trackForeground(Context context) {
        if (tracking) return;
        try {
            Context base = context.getApplicationContext();
            if (!(base instanceof Application)) base = context;
            if (!(base instanceof Application)) return;
            ((Application) base).registerActivityLifecycleCallbacks(
                    new Application.ActivityLifecycleCallbacks() {
                        @Override public void onActivityCreated(Activity activity, Bundle state) { }
                        @Override public void onActivityStarted(Activity activity) { }
                        @Override public void onActivityResumed(Activity activity) { resumed = true; }
                        @Override public void onActivityPaused(Activity activity) { resumed = false; }
                        @Override public void onActivityStopped(Activity activity) { }
                        @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) { }
                        @Override public void onActivityDestroyed(Activity activity) { }
                    });
            tracking = true;
            Log.i(TAG, "已注册生命周期监听");
        } catch (Throwable e) {
            // 注册失败时 tracking 保持 false，Ba002RelayPolicy 会要求无条件重放
            Log.w(TAG, "注册生命周期监听失败，将无条件重放 HOME", e);
        }
    }

    private static void startWatch(Context context) {
        if (watch != null) return;
        watch = new Ba002ForegroundWatch(context);
        watch.start();
    }

    /**
     * HOME 意图是否解析到本应用。
     *
     * <p>只探一次：安装、换桌面都会重建 ResolveInfo，但本进程的这一判断在
     * 开机窗口内不会变，反复探只会多花时间。探不到就按「不是自己」处理。
     */
    private static boolean homeIsOurs(Context context) {
        Boolean known = homeResolvesToUs;
        if (known != null) return known;
        boolean ours = false;
        try {
            Intent home = new Intent(Intent.ACTION_MAIN);
            home.addCategory(Intent.CATEGORY_HOME);
            ResolveInfo ri = context.getPackageManager()
                    .resolveActivity(home, PackageManager.MATCH_DEFAULT_ONLY);
            if (ri != null && ri.activityInfo != null) {
                ours = context.getPackageName().equals(ri.activityInfo.packageName);
                Log.i(TAG, "HOME 解析到 " + ri.activityInfo.packageName
                        + (ours ? "（本应用）" : "（不是本应用，改用显式启动）"));
            } else {
                Log.i(TAG, "HOME 解析不到任何 Activity，改用显式启动");
            }
        } catch (Throwable e) {
            Log.w(TAG, "解析 HOME 失败，改用显式启动", e);
        }
        homeResolvesToUs = ours;
        return ours;
    }

    private static void fire(Context context, int slot) {
        try {
            if (!Ba002RelayPolicy.shouldReplay(resumed, tracking)) {
                Log.i(TAG, "slot " + slot + " 跳过：本应用仍在前台");
                return;
            }
            if (homeIsOurs(context)) {
                Intent home = new Intent(Intent.ACTION_MAIN);
                home.addCategory(Intent.CATEGORY_HOME);
                home.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                context.startActivity(home);
                Log.i(TAG, "slot " + slot + " 已重放 HOME");
            } else {
                startSelf(context, "slot " + slot);
            }
        } catch (Throwable e) {
            Log.w(TAG, "slot " + slot + " 抢前台失败", e);
        }
    }

    /**
     * 轮询发现前台被别家占了。只在「本应用不在前台」且冷却已过时动作，
     * 免得用户正用着别的应用（比如播放器）也被抢回桌面。
     *
     * <p>这里刻意只把原始桌面认作要抢的目标：用户在别的应用里时不该被打断。
     */
    static void onForeignForeground(Context context, String foreignPackage) {
        if (foreignPackage == null) return;
        if (!isStockHome(context, foreignPackage)) return;
        long now = System.currentTimeMillis();
        if (now - lastReclaim < RECLAIM_COOLDOWN_MS) return;
        if (resumed) return;
        lastReclaim = now;
        startSelf(context, "watch:" + foreignPackage);
    }

    /** 这个包是不是系统原本的桌面（只有它才值得抢回来）。 */
    private static boolean isStockHome(Context context, String pkg) {
        String tracked = SystemIntegration.trackedHome(context);
        if (tracked == null || tracked.isEmpty()) return false;
        ComponentName c = ComponentName.unflattenFromString(tracked);
        return c != null && c.getPackageName().equals(pkg);
    }

    /**
     * 显式启动本应用的入口 Activity。
     *
     * <p>用 MainActivity 而不是 HomeActivity：后者是只在「本应用是 HOME」时
     * 才启用的 activity-alias，在这台固件上启用它没有意义，而且会多出一个
     * HOME 候选 —— {@code discoverUniqueOtherHome} 要求原始桌面是唯一的，
     * 多一个候选就记不下 {@code original_home}，整套兼容逻辑随之失效。
     */
    private static void startSelf(Context context, String source) {
        try {
            Intent self = new Intent(Intent.ACTION_MAIN);
            self.setComponent(new ComponentName(context.getPackageName(),
                    context.getPackageName() + ".MainActivity"));
            self.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            context.startActivity(self);
            Log.i(TAG, source + " 已显式启动本应用");
        } catch (Throwable e) {
            Log.w(TAG, source + " 显式启动失败", e);
        }
    }
}
