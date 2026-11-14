#!/usr/bin/env python
"""发布 GitHub Release 并上传构建产物。

用法（token 从环境变量读，不要写进命令行历史）：
    set GITHUB_TOKEN=ghp_xxx
    python tools/publish_release.py --tag v1.8.2 --notes-file RELEASE_NOTES.md

token 也可以是只含一行 token 的文本文件，用 --token-file 指定。
脚本幂等：已存在同 tag 的 release 就复用，同名 asset 先删再传。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"
REPO = "yuanjundi/AuroraARGB"


def log(msg: str) -> None:
    print(msg, flush=True)


def api(method: str, url: str, token: str, **kw) -> requests.Response:
    headers = kw.pop("headers", {})
    headers.update({
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    last = None
    for attempt in range(4):
        try:
            r = requests.request(method, url, headers=headers, timeout=(30, 120), **kw)
        except requests.RequestException as e:
            last = e
            log("  网络异常（第 %d 次）：%s" % (attempt + 1, e))
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code in (502, 503, 504):
            last = RuntimeError("HTTP %d" % r.status_code)
            log("  服务端 %d，重试…" % r.status_code)
            time.sleep(3 * (attempt + 1))
            continue
        return r
    raise SystemExit("请求失败：%s" % last)


def read_token(args) -> str:
    if args.token_file:
        t = Path(args.token_file).read_text(encoding="utf-8").strip()
        if t:
            return t
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        t = os.environ.get(key, "").strip()
        if t:
            return t
    raise SystemExit("缺少 token：设置环境变量 GITHUB_TOKEN，或传 --token-file")


def ensure_release(token: str, tag: str, name: str, notes: str) -> dict:
    r = api("GET", "%s/repos/%s/releases/tags/%s" % (API, REPO, tag), token)
    if r.status_code == 200:
        rel = r.json()
        log("已存在 release %s（id=%s），更新说明" % (tag, rel["id"]))
        r2 = api("PATCH", "%s/repos/%s/releases/%s" % (API, REPO, rel["id"]), token,
                 json={"name": name, "body": notes, "draft": False, "prerelease": False})
        if r2.status_code != 200:
            log("  更新说明失败：%s %s" % (r2.status_code, r2.text[:200]))
        return rel
    if r.status_code != 404:
        raise SystemExit("查询 release 失败：%s %s" % (r.status_code, r.text[:300]))

    log("创建 release %s" % tag)
    r = api("POST", "%s/repos/%s/releases" % (API, REPO), token, json={
        "tag_name": tag, "name": name, "body": notes,
        "draft": False, "prerelease": False,
    })
    if r.status_code not in (200, 201):
        raise SystemExit("创建 release 失败：%s %s" % (r.status_code, r.text[:400]))
    return r.json()


def delete_asset(token: str, rel: dict, name: str) -> None:
    for a in rel.get("assets", []):
        if a["name"] == name:
            log("  删除旧资产 %s" % name)
            api("DELETE", "%s/repos/%s/releases/assets/%s" % (API, REPO, a["id"]), token)


def upload(token: str, rel: dict, path: Path) -> None:
    size = path.stat().st_size
    url = "%s/repos/%s/releases/%s/assets?name=%s" % (
        UPLOAD, REPO, rel["id"], requests.utils.quote(path.name))
    log("上传 %s（%.1f MB）…" % (path.name, size / 1048576))

    with open(path, "rb") as fh:
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/octet-stream",
            "Content-Length": str(size),
        }
        for attempt in range(3):
            try:
                fh.seek(0)
                r = requests.post(url, headers=headers, data=fh,
                                  timeout=(30, 1800))
            except requests.RequestException as e:
                log("  上传异常（第 %d 次）：%s" % (attempt + 1, e))
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (200, 201):
                info = r.json()
                log("  完成：%s（%s bytes）" % (info.get("name"), info.get("size")))
                return
            log("  失败 HTTP %s：%s" % (r.status_code, r.text[:300]))
            if r.status_code in (422, 401, 403):
                raise SystemExit("上传被拒绝，停止")
            time.sleep(5 * (attempt + 1))
    raise SystemExit("上传 %s 失败" % path.name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--notes-file", default=None)
    ap.add_argument("--notes", default="")
    ap.add_argument("--token-file", default=None)
    ap.add_argument("--asset", action="append", default=[])
    args = ap.parse_args()

    token = read_token(args)
    name = args.name or args.tag
    notes = args.notes
    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8")

    assets = [Path(p) for p in args.asset]
    for p in assets:
        if not p.exists():
            raise SystemExit("找不到文件：%s" % p)

    rel = ensure_release(token, args.tag, name, notes)
    for p in assets:
        delete_asset(token, rel, p.name)
        upload(token, rel, p)

    log("全部完成 → https://github.com/%s/releases/tag/%s" % (REPO, args.tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
