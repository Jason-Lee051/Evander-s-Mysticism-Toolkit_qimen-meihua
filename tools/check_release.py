# -*- coding: utf-8 -*-
"""检查 v3.0.0 Release 的资产列表（供上传脚本维护用）"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upload_release import token_from_git_credential, api  # noqa: E402

token = os.environ.get("GH_TOKEN", "").strip() or token_from_git_credential()
base = "https://api.github.com/repos/Jason-Lee051/Evander-s-Mysticism-Toolkit_qimen-meihua"

status, rel = api("GET", f"{base}/releases/tags/v3.0.0", token=token)
if status != 200:
    print(f"查询失败 [{status}]：{rel.get('message')}")
    sys.exit(1)

print(f"Release: {rel['name']} | tag: {rel['tag_name']} | url: {rel['html_url']}")
for a in rel["assets"]:
    print(f"  asset id={a['id']}  name={a['name']!r}  "
          f"size={a['size']/1e6:.1f}MB  downloads={a['download_count']}")

# 支持: python check_release.py delete <asset_id>
if len(sys.argv) >= 3 and sys.argv[1] == "delete":
    aid = sys.argv[2]
    status, _ = api("DELETE", f"{base}/releases/assets/{aid}", token=token)
    print(f"删除资产 {aid}: {'✓ 成功' if status == 204 else f'✗ 失败[{status}]'}")
