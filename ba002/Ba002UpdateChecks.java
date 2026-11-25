// Copyright (C) 2026 tinyhan9
// SPDX-License-Identifier: GPL-3.0-only
//
// 本文件是本分支为 Marco TV（作者 Pilipala，https://github.com/Pilipala9919/MarcoTV，
// GPL-3.0-only）新增的适配层，不含上游代码。
package com.pilipala.tvhome;

/**
 * 离线检查更新源的适配：本分支必须指向自己的仓库，且不能把上游地址漏回来。
 *
 * <p>为什么要单独检查：换源要同时改五处（FEED/MIRROR 常量、feeds()、downloads()、
 * apkUrl() 的主机白名单、transferUrl() 的主机白名单）。漏任意一处，运行时的表现分别是
 * 「feed 拉不到」「APK 下载被 apkUrl 拒绝」「重定向被 transferUrl 拒绝」——
 * 都只有装到电视上点「检查更新」才会发现。
 *
 * <p>这些检查只依赖 UpdatePolicy 的静态方法，不需要网络也不需要 Android 运行时。
 */
public final class Ba002UpdateChecks {

    static int passed;

    static void check(String label, boolean good) {
        if (!good) throw new AssertionError(label);
        passed++;
        System.out.println("PASS " + label);
    }

    public static void main(String[] args) {
        // ---- feed 指向本仓库，且频道文件与上游分开 ----
        String[] feeds = UpdatePolicy.feeds("stable");
        boolean ownFeed = false;
        boolean hasUpstream = false;
        for (String feed : feeds) {
            if (feed.contains("tinyhan9/MarcoTV")) ownFeed = true;
            if (feed.contains("Pilipala9919") || feed.contains("wlj9919.top")) hasUpstream = true;
        }
        check("feed_points_at_own_repo", ownFeed);
        check("feed_has_no_upstream_host", !hasUpstream);
        check("feed_uses_ba002_channel_file", feeds[0].endsWith("ba002-stable.json"));

        String[] preview = UpdatePolicy.feeds("preview");
        check("preview_uses_ba002_channel_file", preview[0].endsWith("ba002-preview.json"));

        // 未知频道必须拒绝，避免拼出任意文件名
        boolean rejected = false;
        try {
            UpdatePolicy.feeds("../etc/passwd");
        } catch (IllegalArgumentException e) {
            rejected = true;
        }
        check("unknown_channel_rejected", rejected);

        // ---- 下载地址指向本仓库的 release，文件名带 -BA002 ----
        String[] downloads = UpdatePolicy.downloads("0.21.3");
        boolean ownDownload = false;
        for (String url : downloads) {
            if (url.contains("github.com/tinyhan9/MarcoTV/releases/download/v0.21.3-ba002/")) ownDownload = true;
        }
        check("download_points_at_own_release", ownDownload);
        check("download_filename_has_ba002_suffix", downloads[0].endsWith("MarcoTV-0.21.3-BA002.apk"));

        // 版本号注入必须拒绝
        boolean badVersion = false;
        try {
            UpdatePolicy.downloads("../../evil");
        } catch (IllegalArgumentException e) {
            badVersion = true;
        }
        check("download_version_injection_rejected", badVersion);

        // ---- apkUrl 只认本仓库的 release 资产 ----
        String good = "https://github.com/tinyhan9/MarcoTV/releases/download/v0.21.3-ba002/MarcoTV-0.21.3-BA002.apk";
        String upstreamApk = "https://github.com/Pilipala9919/MarcoTV/releases/download/v0.21.3/MarcoTV-0.21.3.apk";
        String otherRepo = "https://github.com/attacker/MarcoTV/releases/download/v1/x.apk";
        check("apk_url_accepts_own_release", UpdatePolicy.apkUrl(good));
        check("apk_url_rejects_upstream_release", !UpdatePolicy.apkUrl(upstreamApk));
        check("apk_url_rejects_other_repo", !UpdatePolicy.apkUrl(otherRepo));
        check("apk_url_rejects_http", !UpdatePolicy.apkUrl(good.replace("https://", "http://")));
        check("apk_url_rejects_query", !UpdatePolicy.apkUrl(good + "?x=1"));
        check("apk_url_rejects_traversal",
                !UpdatePolicy.apkUrl("https://github.com/tinyhan9/MarcoTV/releases/download/../../x.apk"));

        // ---- transferUrl 允许 feed 与重定向所需的主机 ----
        check("transfer_allows_raw_github",
                UpdatePolicy.transferUrl("https://raw.githubusercontent.com/tinyhan9/MarcoTV/ba002/docs/updates/ba002-stable.json"));
        check("transfer_allows_jsdelivr",
                UpdatePolicy.transferUrl("https://cdn.jsdelivr.net/gh/tinyhan9/MarcoTV@ba002/docs/updates/ba002-stable.json"));
        check("transfer_allows_github_asset_host",
                UpdatePolicy.transferUrl("https://release-assets.githubusercontent.com/x"));
        check("transfer_rejects_unknown_host",
                !UpdatePolicy.transferUrl("https://example.com/x"));
        check("transfer_rejects_http",
                !UpdatePolicy.transferUrl("http://raw.githubusercontent.com/x"));

        // ---- 完整元数据校验：feed 的内容必须能通过 ----
        String sha = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        UpdatePolicy.validate(47, "0.21.4", 23, 1579905L, sha, good, false, "stable");
        passed++;
        System.out.println("PASS validate_accepts_own_metadata");

        boolean rejectedUpstream = false;
        try {
            UpdatePolicy.validate(46, "0.21.3", 23, 1579905L, sha, upstreamApk, false, "stable");
        } catch (IllegalArgumentException e) {
            rejectedUpstream = true;
        }
        check("validate_rejects_upstream_apk_url", rejectedUpstream);

        // ---- 版本比较 ----
        check("newer_code_wins", UpdatePolicy.newer(47, 46));
        check("same_code_not_newer", !UpdatePolicy.newer(46, 46));
        check("older_code_not_newer", !UpdatePolicy.newer(45, 46));

        System.out.println("OK " + passed + " BA002 update source checks");
    }
}
