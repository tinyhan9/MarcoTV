// Copyright (C) 2026 tinyhan9
// SPDX-License-Identifier: GPL-3.0-only
//
// 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
// GPL-3.0-only）新增的适配层，不含上游代码。
package com.pilipala.tvhome;

import android.app.Activity;
import android.app.Application;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

/**
 * 极光盒子 7X（BA002 / Skyworth 系固件）适配：开机把前台抢回来。
 *
 * <p>为什么要这个类：固件自带的 {@code com.xiaopaitech.wallpaperlauncher} 有一个
 * BootUpReceiver，在收到 {@code BOOT_COMPLETED} 之后约 14 秒，以 uid 1000 的身份
 * 调 {@code startActivity}，把自己的 LauncherActivity 顶到前台。系统把这当成普通
 * 启动，不会拒绝，于是本应用（虽然是 HOME role 的持有者）的前台就被盖掉了。
 *
 * <p>实测时间线（BA002，Android 11）：
 * <pre>
 *   17:12:17  注册生命周期监听，排入 7 个重放时点
 *   17:12:32  厂商桌面 START ... from uid 1000
 *   17:12:35  slot 3 重放 HOME —— 前台抢回
 *   17:12:42  之后各时点均判定「仍在本应用」，不再打扰
 * </pre>
 *
 * <p>判定规则见 {@link Ba002RelayPolicy}，那里抽成了不依赖 Android 的纯逻辑，
 * 由 {@code ba002/test_relay.py} 在 JVM 上跑全部分支。本类只负责接线。
 *
 * <p>为什么不用 {@code getRunningTasks()}：从 API 21 起它只返回调用者自己的任务，
 * 「是否已在前台」永远为真。为什么不用进程 importance：本应用绑定了无障碍服务，
 * 被盖住时进程仍是 {@code vis}（importance 200、oom_adj 100），也是误判。
 * 可靠信号是 Activity 生命周期，它在应用内部，不需要权限也不需要隐藏 API。
 */
public final class Ba002BootRelay extends BroadcastReceiver {

    private static final String TAG = "MarcoTVBa002Relay";

    /** 开机后多久触发一次更新检查（毫秒）。放在抢前台窗口之后。 */
    private static final long EXIT_UPDATE_DELAY = 60_000L;

    /** 网络未就绪时的重试间隔（毫秒）。 */
    private static final long UPDATE_CHECK_RETRY_DELAY = 20_000L;

    /** 最多重试次数，约 3 分钟。 */
    private static final int UPDATE_CHECK_RETRIES = 10;

    /** 本应用是否有 Activity 处于 resumed。只在主线程读写。 */
    private static volatile boolean resumed;
    private static boolean tracking;

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

        // 顺带触发一次更新检查。
        //
        // 上游只在「设置 → 软件更新」这一页被打开时才检查（UpdatePanel.resume()
        // 里排那个 30 分钟的定时器）。对本适配版来说那样不够：本分支的更新源是
        // 自己的仓库，用户不会天天去翻设置页，等于自动更新失效。
        //
        // 放到开机 60 秒后：避开开机时的抢前台窗口，也不和 BOOT_COMPLETED 的
        // 广播链抢主线程。UpdateManager 内部有 6 小时的节流，重复触发是安全的。
        // 首次检查推迟到网络就绪之后。
        //
        // 为什么不能直接 60 秒就叫：UpdateManager.check() 一进入就写 last_attempt，
        // 失败也不清。开机时网络常常还没通，第一次拉 feed 失败就把 6 小时节流
        // 额度烧掉了，用户接下来 6 小时都看不到更新。实测就是这样丢的。
        //
        // 不修改上游代码，改在这里做探测：能连上 443 才触发，连不上就 20 秒后
        // 再试，最多 10 次（约 3 分钟），之后放弃，等下一次开机。
        scheduleUpdateCheck(app, handler, 0);
    }

    /** 开机后等网络就绪再触发一次更新检查；最多重试 10 次。 */
    private static void scheduleUpdateCheck(Context context, Handler handler,
                                            int attempt) {
        if (attempt >= UPDATE_CHECK_RETRIES) {
            Log.i(TAG, "网络一直不可达，放弃本次开机检查");
            return;
        }
        long delay = attempt == 0 ? EXIT_UPDATE_DELAY : UPDATE_CHECK_RETRY_DELAY;
        handler.postDelayed(() -> {
            // 探测要在后台做：主线程不允许网络 IO（NetworkOnMainThreadException），
            // 而且 5 秒超时会卡住桌面。
            new Thread(() -> {
                if (!networkReady()) {
                    Log.i(TAG, "网络未就绪，稍后重试更新检查（" + (attempt + 1) + "）");
                    handler.post(() -> scheduleUpdateCheck(context, handler, attempt + 1));
                    return;
                }
                try {
                    Log.i(TAG, "网络就绪，触发更新检查");
                    // 直接调 check(false)，不要 automatic()。
                    // automatic() = 「距上次检查满 6 小时」+ check()；开机这一次
                    // 若被节流挡掉，用户装完就永远看不到第一次更新。
                    // 每个开机周期查一次是合理频率，check() 本身没有节流。
                    UpdateManager.get(context).check(false);
                } catch (Throwable e) {
                    Log.w(TAG, "开机更新检查未触发", e);
                }
            }, "ba002-update-probe").start();
        }, delay);
    }

    /** 能不能连上更新源所在的 443 端口。连不上就说明网络还没就绪。 */
    private static boolean networkReady() {
        java.net.Socket socket = new java.net.Socket();
        try {
            socket.connect(new java.net.InetSocketAddress("raw.githubusercontent.com", 443), 5000);
            return true;
        } catch (Throwable e) {
            return false;
        } finally {
            try { socket.close(); } catch (Throwable ignored) { }
        }
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

    private static void fire(Context context, int slot) {
        try {
            if (!Ba002RelayPolicy.shouldReplay(resumed, tracking)) {
                Log.i(TAG, "slot " + slot + " 跳过：本应用仍在前台");
                return;
            }
            Intent home = new Intent(Intent.ACTION_MAIN);
            home.addCategory(Intent.CATEGORY_HOME);
            home.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            context.startActivity(home);
            Log.i(TAG, "slot " + slot + " 已重放 HOME");
        } catch (Throwable e) {
            Log.w(TAG, "slot " + slot + " 重放失败", e);
        }
    }
}
