// Copyright (C) 2026 tinyhan9
// SPDX-License-Identifier: GPL-3.0-only
//
// 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
// GPL-3.0-only）新增的适配层，不含上游代码。
package com.pilipala.tvhome;

import android.app.ActivityManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import java.util.List;

/**
 * 极光盒子 7X（BA002 / Skyworth 系固件）适配：开机抢回前台。
 *
 * <p>为什么要这个类：
 *
 * <p>固件自带的 {@code com.xiaopaitech.wallpaperlauncher} 有一个 BootUpReceiver，
 * 在收到 {@code BOOT_COMPLETED} 后以 uid 1000 的身份调 {@code startActivity}，
 * 把自己的 LauncherActivity 顶到前台。系统只把这个动作当作普通启动，不会拒绝，
 * 于是本应用（虽然是 HOME role 的持有者）的前台就被盖掉了，用户看到的是厂商桌面。
 *
 * <p>本类在开机后的若干个时间点重放一次系统 HOME，把前台抢回来。重放前先查当前
 * 前台是不是自己，是就跳过 —— 这样不会打断用户已经进入的其它应用，也不会白跑。
 *
 * <p>只在 {@code BOOT_COMPLETED} 触发。{@code LOCKED_BOOT_COMPLETED} 阶段应用
 * 私有数据尚未解密，任何显式组件启动都会抛 NullPointerException，所以刻意不处理。
 */
public final class Ba002BootRelay extends BroadcastReceiver {

    private static final String TAG = "MarcoTVBa002Relay";

    /** 开机后的重放时间点（毫秒）。覆盖厂商桌面在 ~20s 抢前台那个窗口。 */
    private static final long[] SLOTS = {2_000L, 6_000L, 12_000L, 20_000L, 30_000L, 45_000L};

    @Override public void onReceive(Context context, Intent intent) {
        if (context == null || intent == null) return;
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) return;

        final Context app = context.getApplicationContext() != null
                ? context.getApplicationContext() : context;
        Handler handler = new Handler(Looper.getMainLooper());
        for (int i = 0; i < SLOTS.length; i++) {
            final int slot = i;
            handler.postDelayed(() -> fire(app, slot), SLOTS[i]);
        }
        Log.i(TAG, "已排入 " + SLOTS.length + " 个抢回前台的时点");
    }

    private static void fire(Context context, int slot) {
        try {
            if (oursOnTop(context)) {
                Log.i(TAG, "slot " + slot + " 跳过：已经在前台");
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

    /** 当前前台是不是本应用。取不到信息时返回 false（宁可多抢一次）。 */
    private static boolean oursOnTop(Context context) {
        try {
            ActivityManager am = (ActivityManager) context.getSystemService(Context.ACTIVITY_SERVICE);
            if (am == null) return false;
            List<ActivityManager.RunningTaskInfo> tasks = am.getRunningTasks(1);
            if (tasks == null || tasks.isEmpty()) return false;
            ComponentName top = tasks.get(0).topActivity;
            if (top == null) return false;
            return context.getPackageName().equals(top.getPackageName());
        } catch (Throwable e) {
            return false;
        }
    }
}
