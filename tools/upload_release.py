# -*- coding: utf-8 -*-
"""
tools/upload_release.py — 创建 GitHub Release 并上传资产（如打包好的 zip）

用法：
    set GH_TOKEN=<token>                    # 或留空，自动从 git 凭据管理器读取
    python tools/upload_release.py v3.0.0 "release\玄学工具箱-windows-x64.zip" ^
        --title "v3.0.0 免安装版" --notes-file release_notes.md

依赖：仅 Python 标准库（urllib）。Token 权限需包含 repo（Classic）或
Contents: write（Fine-grained）。
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_REPO = "Jason-Lee051/Evander-s-Mysticism-Toolkit_qimen-meihua"


def token_from_git_credential() -> str:
    """从 git 凭据管理器读取 github.com 的凭据（通常为 PAT/OAuth token）"""
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, timeout=30,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("password="):
                return line[len("password="):].strip()
    except Exception:
        pass
    return ""


def api(method: str, url: str, payload=None, token: str = "",
        content_type: str = "application/json", timeout: int = 60):
    """调用 GitHub API，返回 (状态码, 解析后的响应)"""
    data = None
    if payload is not None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "mysticism-tools-release")
    if data:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"message": body[:300]}
    except Exception as e:
        return 0, {"message": f"{type(e).__name__}: {e}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="创建 GitHub Release 并上传资产")
    parser.add_argument("tag", help="标签名，如 v3.0.0")
    parser.add_argument("assets", nargs="*", help="要上传的文件路径")
    parser.add_argument("--title", default=None, help="Release 标题（默认同 tag）")
    parser.add_argument("--notes", default="", help="Release 说明正文")
    parser.add_argument("--notes-file", default=None, help="从文件读取说明正文")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--update", action="store_true",
                        help="Release 已存在时向上传资产/改说明，而不是报错退出")
    parser.add_argument("--delete-asset", default=None,
                        help="删除已有 Release 中指定名称的资产后继续")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN", "").strip()
    from_git = False
    if not token:
        token = token_from_git_credential()
        from_git = True
    if not token:
        print("错误：未提供 token（设置 GH_TOKEN，或确保 git 凭据管理器已保存 github.com 凭据）")
        return 1
    print(f"token 来源：{'git 凭据管理器' if from_git else '环境变量 GH_TOKEN'}")

    base = f"https://api.github.com/repos/{args.repo}"

    # 1. 解析仓库规范全名（自动跟随改名重定向）
    status, res = api("GET", base, token=token)
    if status != 200:
        print(f"错误：无法访问仓库 [{status}]：{res.get('message')}")
        return 1
    full_name = res["full_name"]
    default_branch = res.get("default_branch", "main")
    print(f"仓库：{full_name}（默认分支 {default_branch}）")
    base = f"https://api.github.com/repos/{full_name}"

    # 2. 检查 tag/release 是否已存在
    status, res = api("GET", f"{base}/releases/tags/{args.tag}", token=token)
    release_id = None
    upload_url = None
    if status == 200:
        if not args.update and not args.delete_asset:
            print(f"错误：Release {args.tag} 已存在（id={res.get('id')}）。"
                  f"加 --update 可向其上传资产。")
            return 1
        release_id = res["id"]
        upload_url = res["upload_url"].split("{")[0]
        print(f"已存在 Release {args.tag}（id={release_id}），执行更新模式")
    elif status == 404 and args.delete_asset:
        print(f"错误：Release {args.tag} 不存在，无法删除资产")
        return 1

    # 3. 删除指定资产（可选）
    if args.delete_asset:
        status, res = api("GET", f"{base}/releases/{release_id}/assets", token=token)
        target = None
        if status == 200:
            for asset in res:
                if asset.get("name") == args.delete_asset:
                    target = asset
                    break
        if target is None:
            print(f"提示：未找到名为 {args.delete_asset} 的资产，跳过删除")
        else:
            status, _ = api("DELETE", f"{base}/releases/assets/{target['id']}",
                            token=token)
            print(f"{'✓ 已删除' if status == 204 else '✗ 删除失败[' + str(status) + ']'}"
                  f" 旧资产：{args.delete_asset}")

    # 4. 读取并更新说明正文（可选）
    body = args.notes
    if args.notes_file:
        with open(args.notes_file, "r", encoding="utf-8") as f:
            body = f.read()
    if args.notes_file and release_id is not None:
        status, res = api("PATCH", f"{base}/releases/{release_id}",
                          {"body": body}, token)
        print(f"{'✓ 说明已更新' if status == 200 else '✗ 说明更新失败[' + str(status) + ']'}")

    # 5. 新建 Release（tag 不存在时自动在默认分支 HEAD 创建）
    if release_id is None:
        payload = {
            "tag_name": args.tag,
            "target_commitish": default_branch,
            "name": args.title or args.tag,
            "body": body,
            "draft": False,
            "prerelease": False,
        }
        status, res = api("POST", f"{base}/releases", payload, token)
        if status != 201:
            print(f"错误：创建 Release 失败 [{status}]：{res.get('message')}")
            return 1
        release_id = res["id"]
        upload_url = res["upload_url"].split("{")[0]
        html_url = res["html_url"]
        print(f"✓ Release 已创建：{html_url}")

    # 6. 逐个上传资产
    ok = True
    for path in args.assets:
        name = os.path.basename(path)
        size = os.path.getsize(path)
        quoted = urllib.parse.quote(name)
        url = f"{upload_url}?name={quoted}"
        print(f"上传资产：{name}（{size / 1e6:.1f} MB）...", flush=True)
        with open(path, "rb") as f:
            status, res = api("POST", url, f.read(), token,
                              content_type="application/zip", timeout=900)
        if status == 201:
            print(f"  ✓ 上传完成：{res.get('browser_download_url')}")
        else:
            print(f"  ✗ 上传失败 [{status}]：{res.get('message')}")
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
