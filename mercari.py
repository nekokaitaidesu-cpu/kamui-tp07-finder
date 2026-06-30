# -*- coding: utf-8 -*-
"""メルカリ スクレイパー（Playwright）。

メルカリ検索は SPA＋bot対策が強いため、実ブラウザで描画して
`li[data-testid=item-cell]` から取得する。ログイン不要の公開検索を使う。

Playwright 未導入や失敗時は呼び出し側で握りつぶす。
"""

import re
import urllib.parse

from bs4 import BeautifulSoup

MERCARI = "https://jp.mercari.com"
SEARCHES = ("カムイ タイフーン TP-07", "カムイ TP-07 ガスのみ")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for li in soup.select("li[data-testid=item-cell]"):
        a = li.select_one('a[data-testid=thumbnail-link]') or li.select_one('a[href^="/item/m"]')
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/item/(m\d+)", href)
        if not m:
            continue
        mid = m.group(1)

        name_el = li.select_one('[data-testid=thumbnail-item-name]')
        title = name_el.get_text(strip=True) if name_el else ""
        if not title:
            thumb = li.select_one(".merItemThumbnail")
            if thumb and thumb.get("aria-label"):
                title = re.sub(r"の画像.*$", "", thumb["aria-label"]).strip()

        num = li.select_one(".merPrice .number__6b270ca7") or li.select_one(".merPrice .number")
        price = None
        if num:
            digits = "".join(ch for ch in num.get_text() if ch.isdigit())
            price = int(digits) if digits else None

        img_el = li.select_one("img")
        img = (img_el.get("src") or "") if img_el else ""
        if not img:
            img = f"https://static.mercdn.net/thumb/item/webp/{mid}_1.jpg"

        blob = (li.get_text(" ", strip=True) + " "
                + " ".join(x.get("aria-label", "") for x in li.select("[aria-label]")))
        sold = ("売り切れ" in blob) or ("SOLD" in blob.upper())

        out.append({
            "id": "mc" + mid,
            "title": title,
            "price": price,
            "cond": "", "year": "", "shaft": "",
            "url": MERCARI + href if href.startswith("/") else href,
            "img": img, "img2": "",
            "source": "メルカリ",
            "status": "sold" if sold else "active",
        })
    return out


def collect(headless: bool = True) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
    items: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ja-JP", user_agent=UA,
            viewport={"width": 1280, "height": 1800})
        # webdriver フラグを隠して headless 検知を緩和
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.new_page()
        try:
            for search in SEARCHES:
                url = (f"{MERCARI}/search?keyword=" + urllib.parse.quote(search)
                       + "&order=desc&sort=created_time")
                # 取得できないことがあるので最大2回試行
                ok = False
                for attempt in range(2):
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector("li[data-testid=item-cell]", timeout=30000)
                        ok = True
                        break
                    except Exception:
                        page.wait_for_timeout(2000)
                if not ok:
                    continue
                # メルカリは仮想スクロール（画面内の数件だけ href が埋まる）。
                # 少しずつスクロールしながら毎回パースして蓄積する。
                last_count = -1
                stagnant = 0
                for _ in range(40):
                    for rec in _parse(page.content()):
                        items.setdefault(rec["id"], rec)
                    page.mouse.wheel(0, 2200)
                    page.wait_for_timeout(700)
                    if len(items) == last_count:
                        stagnant += 1
                        if stagnant >= 6:        # これ以上増えなければ終了
                            break
                    else:
                        stagnant = 0
                    last_count = len(items)
                for rec in _parse(page.content()):
                    items.setdefault(rec["id"], rec)
        finally:
            browser.close()
    return list(items.values())


if __name__ == "__main__":
    got = collect()
    print(f"メルカリ TP-07候補(全カテゴリ): {len(got)} 件")
    for g in got[:30]:
        print(f"  [{'SOLD' if g['status']=='sold' else '売中'}] ¥{g['price']} | {g['title'][:50]}")
