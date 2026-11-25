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
 *   17:07:38  BOOT_COMPLETED，本类排入 6 个重放时点
 *   17:07:52  厂商桌面 START ... from uid 1000
 *   17:07:58  slot 3 触发 —— 此时前台已经是厂商桌面
 * </pre>
 *
 * <p>怎么判断「自己还在不在前台」：<b>不能用</b> {@code getRunningTasks()}，从
 * API 21 起它只返回调用者自己的任务，判定永远为真；也<b>不能用</b>
 * {@code getRunningAppProcesses()} 的 importance —— 本应用绑定了无障碍服务，
 * 被盖住时进程仍是 {@code vis}（importance 200），实测 oom_adj 就是 100。
 *
 * <p>可靠的做法是 Activity 生命周期：注册
 * {@link Application.ActivityLifecycleCallbacks}，本应用任何一个 Activity 被暂停
 * 就说明前台被别人占了。这个信号在应用内部，不依赖任何权限或隐藏 API。
 */
public final class Ba002BootRelay extends BroadcastReceiver {

    private static final String TAG = "MarcoTVBa002Relay";

    /**
     * 开机后的重放时点（毫秒）。厂商桌面在 +14s 左右抢前台，所以重点覆盖
     * 14s 之后；前面的时点是给「厂商抢得更早」的固件留的余量。
     */
    private static final long[] SLOTS = {2_000L, 6_000L, 12_000L, 18_000L, 25_000L, 35_000L, 50_000L};

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
        for (int i = 0; i < SLOTS.length; i++) {
            final int slot = i;
            handler.postDelayed(() -> fire(app, slot), SLOTS[i]);
        }
        Log.i(TAG, "已排入 " + SLOTS.length + " 个抢回前台的时点");
    }

    /** 注册一次即可；进程重启后重新注册。 */
    private static void trackForeground(Context context) {
        if (tracking) return;
        try {
            Context base = context.getApplicationContext();
            if (!(base instanceof Application)) {
                base = context;
            }
            if (!(base instanceof Application)) return;
            ((Application) base).registerActivityLifecycleCallbacks(new Application.ActivityLifecycleCallbacks() {
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
            Log.w(TAG, "注册生命周期监听失败，将无条件重放 HOME", e);
        }
    }

    private static void fire(Context context, int slot) {
        try {
            if (resumed) {
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
