# -*- coding: utf-8 -*-
"""探测 AIPortal 站点 EngageMessages / EngageSyncRuns 列表结构。

认证：MSAL 设备码流程，使用 Microsoft Graph Command Line Tools 公共客户端。
token 缓存放 %USERPROFILE% 下，不进入 Git。
"""
import json
import os
import sys

import msal
import requests

TENANT = "organizations"
# Microsoft Graph Command Line Tools（Connect-MgGraph -UseDeviceAuthentication 同款公共客户端）
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
SCOPES = ["User.Read", "Sites.Read.All"]
CACHE = os.path.join(os.path.expanduser("~"), ".engage_graph_cache.bin")
HOST = "faurecia.sharepoint.com"
SITE_PATH = "/sites/AIPortal"
TARGET_LISTS = ["EngageMessages", "EngageSyncRuns"]
GRAPH = "https://graph.microsoft.com/v1.0"
OUT = os.path.join(os.path.dirname(__file__), "list_schema_report.json")

SESSION = requests.Session()


def get_token():
    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT}",
        token_cache=msal.SerializableTokenCache(),
    )
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            app.token_cache.deserialize(f.read())

    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            sys.exit(f"设备流启动失败: {flow}")
        print("=== 请完成设备登录 ===", flush=True)
        print(flow["message"], flush=True)
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        sys.exit(f"认证失败: {json.dumps(result, ensure_ascii=False, indent=2)}")

    if app.token_cache.has_state_changed:
        with open(CACHE, "w", encoding="utf-8") as f:
            f.write(app.token_cache.serialize())
    return result["access_token"]


def api(token, url, params=None):
    r = SESSION.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=60)
    if r.status_code != 200:
        print(f"[HTTP {r.status_code}] {url}\n{r.text[:800]}", flush=True)
        return None
    return r.json()


def main():
    token = get_token()
    print("认证成功", flush=True)

    site = api(token, f"{GRAPH}/sites/{HOST}:{SITE_PATH}")
    if not site:
        sys.exit("无法解析站点")
    site_id = site["id"]
    print(f"站点: {site['displayName']}  id={site_id}", flush=True)

    report = {"site": {"id": site_id, "name": site["displayName"]}, "lists": {}}

    lists = []
    url = f"{GRAPH}/sites/{site_id}/lists"
    while url:
        data = api(token, url) or {}
        lists.extend(data.get("value", []))
        url = data.get("@odata.nextLink")

    for lst in lists:
        name = lst.get("name", "")
        if name in TARGET_LISTS:
            cols = []
            curl = f"{GRAPH}/sites/{site_id}/lists/{lst['id']}/columns"
            while curl:
                cdata = api(token, curl) or {}
                cols.extend(cdata.get("value", []))
                curl = cdata.get("@odata.nextLink")

            items = api(
                token,
                f"{GRAPH}/sites/{site_id}/lists/{lst['id']}/items",
                params={"$top": 5, "$expand": "fields($select=*)"},
            )
            report["lists"][name] = {
                "id": lst["id"],
                "displayName": lst.get("displayName"),
                "created": lst.get("createdDateTime"),
                "item_count": lst.get("list", {}).get("itemCount") or lst.get("sharepointIds"),
                "columns": cols,
                "sample_items": (items or {}).get("value", []),
            }
            print(f"列表 {name}: id={lst['id']} 列数={len(cols)}", flush=True)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"完整报告已写入 {OUT}", flush=True)

    for name, info in report["lists"].items():
        print(f"\n===== {name} 列结构 =====", flush=True)
        for c in info["columns"]:
            ctype = c.get("columnGroup") and "" or ""
            t = c.get("text") or c.get("choice") or c.get("dateTime") or c.get("number") or c.get("boolean")
            kind = (t or {}).get("type") if isinstance(t, dict) else None
            if c.get("choice"):
                kind = "choice"
            print(
                f"  {c['name']:<28} {kind or '':<12} display='{c.get('displayName','')}'"
                f"{' [indexed]' if c.get('indexed') else ''}"
                f"{' [required]' if c.get('required') else ''}",
                flush=True,
            )


if __name__ == "__main__":
    main()
