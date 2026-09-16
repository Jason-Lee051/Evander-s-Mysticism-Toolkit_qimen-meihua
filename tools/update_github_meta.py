# -*- coding: utf-8 -*-
"""
tools/update_github_meta.py — 更新 GitHub 仓库的「描述」与「标签」

GitHub 的仓库描述 / Topics 只能通过 REST API 或网页设置，无法用 git 提交。
本脚本用 Python 标准库 urllib 调用 API（OpenSSL 栈，在 Schannel 受限环境下仍可用）。

用法：
    set GH_TOKEN=<token>          # Windows CMD
    $env:GH_TOKEN='<token>'       # PowerShell
    python tools/update_github_meta.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

REPO = os.environ.get(
    "GH_REPO",
    "Jason-Lee051/Evander-s-Fun-Little-Gadget_Evander-s-Mysticism-Tools")

DESCRIPTION = (
    "🔮 玄学排盘工具箱（PySide6）：奇门遁甲 · 梅花易数 · 塔罗牌，"
    "内置九宫/六爻/牌阵可视化与 LLM 智能解盘、多轮追问 | "
    "Cross-platform Chinese divination toolkit: Qi Men Dun Jia, "
    "Mei Hua Yi Shu & Tarot with AI analysis."
)

TOPICS = [
    "qimen-dunjia", "qimen", "meihua", "iching", "tarot", "tarot-cards",
    "divination", "metaphysics", "chinese-metaphysics",
    "pyside6", "qt", "python", "llm", "deepseek", "openai",
]


def api(method: str, path: str, payload=None, token: str = "", full_name: str = ""):
    """调用 GitHub REST API，返回 (状态码, 解析后的响应)

    注意：必须使用仓库的规范全名。GitHub 在仓库改名后会对旧名返回 307，
    而带请求体的 PATCH/PUT 不会被 urllib 自动跟随，故需先解析 full_name。
    """
    repo = full_name or REPO
    url = f"https://api.github.com/repos/{repo}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "mysticism-tools-meta")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=45) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body).get("message", body[:200])
        except Exception:
            msg = body[:200]
        return e.code, {"message": msg}
    except Exception as e:
        return 0, {"message": f"{type(e).__name__}: {e}"}


def resolve_full_name(token: str) -> str:
    """解析仓库规范全名（GET 会自动跟随改名产生的 307 重定向）"""
    status, res = api("GET", "", None, token)
    if status == 200 and res.get("full_name"):
        return res["full_name"]
    raise RuntimeError(f"无法解析仓库名（{status}：{res.get('message')}）")


def main() -> int:
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        print("错误：未提供 token（请先设置环境变量 GH_TOKEN）")
        return 1

    try:
        full_name = resolve_full_name(token)
    except Exception as e:
        print(f"错误：{e}")
        return 1

    print(f"仓库：{full_name}")
    if full_name != REPO:
        print(f"（已从旧名重定向：{REPO}）")

    status, res = api("PATCH", "", {"description": DESCRIPTION},
                      token, full_name)
    if status == 200:
        print("✓ 描述已更新：")
        print("  " + (res.get("description") or ""))
    else:
        print(f"✗ 描述更新失败 [{status}]：{res.get('message')}")

    status2, res2 = api("PUT", "/topics", {"names": TOPICS},
                        token, full_name)
    if status2 == 200:
        print("✓ 标签已更新：" + ", ".join(res2.get("names", [])))
    else:
        print(f"✗ 标签更新失败 [{status2}]：{res2.get('message')}")

    if status != 200 or status2 != 200:
        print()
        print("提示：若返回 403/404，说明当前凭据权限不足，")
        print("      需改用带 repo 权限的 Personal Access Token")
        print("      （GitHub → Settings → Developer settings → Tokens）。")
        return 1
    print()
    print(f"仓库地址：https://github.com/{full_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
