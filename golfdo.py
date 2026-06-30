# -*- coding: utf-8 -*-
"""ゴルフドゥ オンライン中古スクレイパー（Playwright）。

ゴルフドゥの商品リストは Vue/Laravel の描画＋フリーワード検索は別系統
（/club/model → /club/list/{id}）のため、実ブラウザでDOMを描画して取得する。

流れ:
  1. /club/model?search=カムイ タイフーン → モデル一覧（TP-07/05…）
  2. 名前が TP-07 のモデルの /club/list/{id} へ
  3. li.items_list_detail から個別中古品（タイトル/価格/ロフト/画像/URL）を抽出

Playwright 未導入や失敗時は呼び出し側で握りつぶす（requests 系の取得は継続）。
"""

import re
import urllib.parse

from bs4 import BeautifulSoup

GD = "https://www.golfdo.com"
SEARCHES = ("カムイ タイフーン", "カムイ TP-07")


def _compact(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s\-‐-―ｰ・]", "", s)


def _is_tp07(name: str) -> bool:
    c = _compact(name)
    return ("typhoonpro07" in c) or ("tp07" in c)


def _model_links(page, search: str) -> list[tuple[str, str]]:
    """モデル検索ページから (モデル名, /club/list URL) を返す（TP-07のみ）。"""
    url = f"{GD}/club/model?select=" + urllib.parse.quote("クラブ") \
        + "&search=" + urllib.parse.quote(search)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector('a[href*="/club/list/"]', timeout=20000)
    except Exception:
        return []
    page.wait_for_timeout(1200)
    out: list[tuple[str, str]] = []
    seen = set()
    cards = page.locator('a[href*="/club/list/"]')
    for i in range(cards.count()):
        c = cards.nth(i)
        href = c.get_attribute("href") or ""
        m = re.search(r"/club/list/(\d+)", href)
        if not m or m.group(1) in seen:
            continue
        name = " ".join(c.inner_text().split())
        if _is_tp07(name):
            seen.add(m.group(1))
            out.append((name, href if href.startswith("http") else GD + href))
    return out


def _parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for li in soup.select("li.items_list_detail"):
        a = li.select_one("a.detail_link") or li.select_one('a[href*="/club/detail/"]')
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/club/detail/(\w+)", href)
        if not m:
            continue
        pid = m.group(1)

        maker = li.select_one(".item_maker")
        cat = li.select_one(".item_category")
        model = li.select_one(".model_name")
        shaft = li.select_one(".shaft_name")
        title = " ".join(t.get_text(strip=True) for t in (maker, cat, model) if t)
        shaft_txt = shaft.get_text(strip=True) if shaft else ""

        loft = ""
        for dl in li.select(".item_detail_table dl"):
            dt = dl.select_one("dt")
            dd = dl.select_one("dd")
            if dt and dd and "ロフト" in dt.get_text():
                loft = dd.get_text(strip=True)

        price = None
        price_el = li.select_one(".price_block .price") or li.select_one(".price")
        if price_el:
            digits = "".join(ch for ch in price_el.get_text() if ch.isdigit())
            price = int(digits) if digits else None

        rank_el = li.select_one(".rank_mark span")
        shop_el = li.select_one(".zaiko_shop")
        img_el = li.select_one(".item_photo img")
        img = ""
        if img_el:
            img = img_el.get("data-src") or img_el.get("src") or ""

        out.append({
            "id": f"gd{pid}",
            "title": title,
            "price": price,
            "cond": (rank_el.get_text(strip=True) if rank_el else ""),
            "year": "",
            "shaft": shaft_txt + (f"  ロフト{loft}" if loft else ""),
            "url": href if href.startswith("http") else GD + href,
            "img": img, "img2": "",
            "source": "ゴルフドゥ",
            "status": "active",
        })
    return out


def collect(headless: bool = True) -> list[dict]:
    """TP-07 の中古品をゴルフドゥから取得。Playwright 未導入なら []。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
    items: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            models: dict[str, tuple[str, str]] = {}
            for search in SEARCHES:
                for name, link in _model_links(page, search):
                    mid = re.search(r"/club/list/(\d+)", link).group(1)
                    models.setdefault(mid, (name, link))
            for name, link in models.values():
                page.goto(link, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_selector("li.items_list_detail", timeout=20000)
                except Exception:
                    continue
                page.wait_for_timeout(800)
                for rec in _parse_list(page.content()):
                    items.setdefault(rec["id"], rec)
        finally:
            browser.close()
    return list(items.values())


if __name__ == "__main__":
    got = collect()
    print(f"ゴルフドゥ TP-07: {len(got)} 件")
    for g in got:
        print(f"  ¥{g['price']} | {g['title']} | {g['shaft']} | {g['url'][-22:]}")
