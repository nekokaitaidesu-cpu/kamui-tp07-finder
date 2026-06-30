# -*- coding: utf-8 -*-
"""カムイ タイフーンプロ TP-07「金ロフト・ガスのみ・爆音」ハンター。

中古ショップ（ゴルフパートナー）に“ただのTP-07”としてこっそり並ぶ
金ロフト個体を取りこぼさないための監視ツール。

やること:
  1. ゴルフパートナーの中古検索を「タイフーン」「カムイ」で巡回
  2. タイトルから TP-07 だけを抽出
  3. タイトル語＋写真で「金/赤/白/発泡/要確認」を仮判定
  4. 前回からの新着を検知（state.json で既知IDを記録）
  5. 写真サムネ付きの専用ページ index.html を生成

金/赤/白はショップのタイトルにほぼ書かれないので、最終判定は写真目視。
このツールは「候補を一覧に集め、新着を目立たせ、写真をすぐ見られる」ことに徹する。
"""

import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "state.json")
OUT_PATH = os.path.join(HERE, "index.html")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
GP_BASE = "https://www.golfpartner.jp"

# ゴルフドゥの手動検索リンク（JS描画のため自動取得はv1では対象外）
GOLFDO_SEARCH = ("https://www.golfdo.com/supplies/list?search="
                 + urllib.parse.quote("カムイ タイフーン TP-07") + "&sort=new")


def jst_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))


# ---------------------------------------------------------------- scraping ---

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"})
    return s


def _gp_search(sess: requests.Session, keyword: str, max_pages: int = 12) -> list[dict]:
    """ゴルフパートナー中古検索を全ページ巡回して生カードを返す。

    クエリは Shift_JIS でエンコードする必要がある（サイト仕様）。
    """
    out: list[dict] = []
    q = urllib.parse.quote(keyword.encode("shift_jis"))
    for page in range(1, max_pages + 1):
        url = f"{GP_BASE}/shop/usedgoods/?search=x&keyword={q}"
        if page > 1:
            url += f"&p={page}"
        try:
            r = sess.get(url, timeout=25)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.content.decode("shift_jis", "replace"), "html.parser")
        cards = soup.select("div.tile_elm_")
        if not cards:
            break
        for c in cards:
            rec = _parse_card(c)
            if rec:
                out.append(rec)
        if len(cards) < 20:
            break
        time.sleep(1.0)  # polite
    return out


def _parse_card(card) -> dict | None:
    name_el = card.select_one("a.goods_name_")
    if not name_el:
        return None
    title = name_el.get("title") or name_el.get_text(strip=True)
    href = name_el.get("href", "")
    m = re.search(r"/shop/g/g(\d+)/", href)
    if not m:
        return None
    gid = m.group(1)

    price_el = card.select_one("span.price_")
    price = None
    if price_el:
        digits = "".join(ch for ch in price_el.get_text() if ch.isdigit())
        price = int(digits) if digits else None

    state_el = card.select_one(".state_box_")
    year_el = card.select_one(".model_c_")
    shaft_el = card.select_one(".scratch_detail_")
    cond = state_el.get_text(strip=True) if state_el else ""
    year = year_el.get_text(strip=True) if year_el else ""
    shaft = shaft_el.get_text(strip=True) if shaft_el else ""

    return {
        "id": gid,
        "title": unicodedata.normalize("NFKC", title).strip(),
        "price": price,
        "cond": cond,
        "year": year,
        "shaft": unicodedata.normalize("NFKC", shaft).strip(),
        "url": f"{GP_BASE}/shop/g/g{gid}/",
        "img": f"{GP_BASE}/img/goods/L/item{gid}p1.jpg",
        "img2": f"{GP_BASE}/img/goods/S/item{gid}p2.jpg",
        "source": "ゴルフパートナー",
        "status": "active",   # 出品中（買える）
    }


# --------------------------------------------------------------- Yahoo ヤフオク -

def _yahoo_active(sess: requests.Session, keyword: str, per: int = 100) -> list[dict]:
    """ヤフオク出品中（買える）。検索結果HTMLの li.Product を解析。"""
    url = ("https://auctions.yahoo.co.jp/search/search?p="
           + urllib.parse.quote(keyword) + f"&n={per}")
    try:
        r = sess.get(url, timeout=25)
    except requests.RequestException:
        return []
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out: list[dict] = []
    for p in soup.select("li.Product"):
        a = p.select_one(".Product__titleLink") or p.select_one(".Product__title a")
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/auction/([\w-]+)", href)
        if not m:
            continue
        aid = m.group(1)
        price_el = p.select_one(".Product__price .Product__priceValue") or p.select_one(".Product__price")
        digits = "".join(ch for ch in (price_el.get_text() if price_el else "") if ch.isdigit())
        img_el = p.select_one(".Product__imageData") or p.select_one("img")
        img = (img_el.get("src") or img_el.get("data-auctionimg") or "") if img_el else ""
        out.append({
            "id": f"y{aid}",
            "title": unicodedata.normalize("NFKC", a.get_text(strip=True)).strip(),
            "price": int(digits) if digits else None,
            "cond": "", "year": "", "shaft": "",
            "url": href if href.startswith("http") else f"https://auctions.yahoo.co.jp{href}",
            "img": img, "img2": "",
            "source": "ヤフオク",
            "status": "active",
        })
    return out


def _yahoo_closed(sess: requests.Session, keyword: str, per: int = 100) -> list[dict]:
    """落札相場（売却済・参考）。ヤフオク落札＋Yahoo!フリマ売却を含む。

    結果は <script id="__NEXT_DATA__"> にJSON埋め込み。
    """
    url = ("https://auctions.yahoo.co.jp/closedsearch/closedsearch?p="
           + urllib.parse.quote(keyword) + f"&n={per}")
    try:
        r = sess.get(url, timeout=25)
    except requests.RequestException:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
        items = data["props"]["pageProps"]["initialState"]["search"]["items"]["listing"]["items"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return []
    out: list[dict] = []
    for raw in items:
        title = raw.get("title")
        price = raw.get("price")
        if not title or not price:
            continue
        aid = raw.get("auctionId", "")
        flea = bool(raw.get("isFleamarketItem"))
        end = (raw.get("endTime") or "")[:10]
        out.append({
            "id": f"yc{aid}",
            "title": unicodedata.normalize("NFKC", title).strip(),
            "price": int(price),
            "cond": end, "year": "", "shaft": "",
            "url": f"https://auctions.yahoo.co.jp/jp/auction/{aid}" if aid else "",
            "img": raw.get("imageUrl", "") or "", "img2": "",
            "source": "Yahoo!フリマ売却" if flea else "ヤフオク落札",
            "status": "sold",
        })
    return out


# ------------------------------------------------------------ classify TP-07 -

def _compact(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s\-‐-―ｰ・]", "", s)


def is_tp07(title: str) -> bool:
    c = _compact(title)
    return ("typhoonpro07" in c) or ("tp07" in c)


def is_non_driver(title: str) -> bool:
    """FW/UT/アイアン等を除外（探しているのはドライバーの金ロフト）。"""
    return bool(re.search(r"ＦＷ|ＵＴ|フェアウェイ|ユーティリ|アイアン|ウェッジ|ハイブリッド|[357]Ｗ|[0-9]+UT", title))


def classify_loft(rec: dict) -> tuple[str, str]:
    """(コード, 表示ラベル) を返す。コード: gold/foam/red/white/check。

    フリマ/オクは出品者が「ガスのみ」「発泡」「爆音」を明記するため
    キーワードで当たり/ハズレを高精度に振り分けられる。
    中古ショップ(タイトル無記載)は check に落ちて写真目視へ回す。
    """
    t = rec["title"] + " " + rec.get("shaft", "")
    # 発泡・窒素ガス充填系はハズレ（「発泡+ガス」両記載でもこちら優先）
    if re.search(r"発泡|発砲|nitro|ニトロ", t, re.I):
        return "foam", "発泡/NITRO（ハズレ）"
    if re.search(r"金ロフト|ロフト金|ゴールド|gold|ガスのみ|爆音", t, re.I):
        return "gold", "金ロフト・ガスのみ濃厚 ★"
    if re.search(r"赤ロフト|レッド", t, re.I):
        return "red", "赤ロフト（ハズレ）"
    if re.search(r"白ロフト|ホワイト", t, re.I):
        return "white", "白ロフト（ハズレ）"
    return "check", "要確認（写真で目視）"


# ---------------------------------------------------------------- ラクマ -----

def _rakuma(sess: requests.Session, keyword: str, pages: int = 2) -> list[dict]:
    """ラクマ(fril.jp)。商品カード `.item-box` のデータ属性から取得（requestsで可）。"""
    out: list[dict] = []
    for pg in range(1, pages + 1):
        url = ("https://fril.jp/s?query=" + urllib.parse.quote(keyword)
               + (f"&page={pg}" if pg > 1 else ""))
        try:
            r = sess.get(url, timeout=25)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        anchors = soup.select("a.link_search_image")
        if not anchors:
            break
        for a in anchors:
            name = a.get("data-rat-item_name") or ""
            href = a.get("href", "")
            if not name or not href:
                continue
            digits = "".join(ch for ch in (a.get("data-rat-price") or "") if ch.isdigit())
            box = a.find_parent(class_="item-box")
            sold = bool(box and (
                "sold" in (box.get("class") or [])
                or box.select_one('[class*=sold]')))
            img = ""
            if box:
                im = box.select_one("img")
                if im:
                    img = im.get("data-original") or im.get("src") or ""
            out.append({
                "id": "rk" + href.rstrip("/").split("/")[-1],
                "title": unicodedata.normalize("NFKC", name).strip(),
                "price": int(digits) if digits else None,
                "cond": "", "year": "", "shaft": "",
                "url": href,
                "img": img, "img2": "",
                "source": "ラクマ",
                "status": "sold" if sold else "active",
            })
    return out


# ----------------------------------------------------------------- pipeline --

def collect() -> list[dict]:
    sess = _session()
    raw: dict[str, dict] = {}
    # ① ゴルフパートナー中古（写真目視前提）
    for kw in ("タイフーン", "カムイ"):
        for rec in _gp_search(sess, kw):
            raw.setdefault(rec["id"], rec)
    # ② ヤフオク 出品中（買える）＋ ③ 落札相場（売却済・参考、フリマ含む）
    for kw in ("カムイ TP-07", "カムイ タイフーン"):
        for rec in _yahoo_active(sess, kw):
            raw.setdefault(rec["id"], rec)
        for rec in _yahoo_closed(sess, kw):
            raw.setdefault(rec["id"], rec)
        # ④ ラクマ（fril.jp、requestsで可）
        for rec in _rakuma(sess, kw):
            raw.setdefault(rec["id"], rec)
        time.sleep(1.0)
    # ⑤ ゴルフドゥ（Playwright描画。未導入/失敗時は静かにスキップ）
    try:
        import golfdo
        for rec in golfdo.collect():
            raw.setdefault(rec["id"], rec)
    except Exception as e:
        print(f"  ゴルフドゥ: スキップ（{type(e).__name__}: {e}）")
    tp07 = [r for r in raw.values()
            if is_tp07(r["title"]) and not is_non_driver(r["title"])]
    result: list[dict] = []
    for r in tp07:
        code, label = classify_loft(r)
        r["loft_code"] = code
        r["loft_label"] = label
        # 売却済のハズレ(発泡/赤/白)はノイズなので除外。出品中は全部残す。
        if r["status"] == "sold" and code in ("foam", "red", "white"):
            continue
        result.append(r)
    return result


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"seen": {}}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def mark_new(items: list[dict], state: dict, seeding: bool) -> int:
    """新着を判定。seeding=True（初回）の時は全件を既知登録するが新着扱いしない。"""
    seen = state.setdefault("seen", {})
    today = jst_now().strftime("%Y-%m-%d")
    new_count = 0
    for it in items:
        first = it["id"] not in seen
        if first:
            seen[it["id"]] = today
        it["is_new"] = first and not seeding
        if it["is_new"]:
            new_count += 1
        it["first_seen"] = seen[it["id"]]
    return new_count


# ------------------------------------------------------------------- render --

CODE_ORDER = {"gold": 0, "check": 1, "white": 3, "red": 3, "foam": 4}
CODE_CLASS = {"gold": "gold", "check": "check", "white": "miss",
              "red": "miss", "foam": "miss"}


def render(items: list[dict], new_count: int) -> str:
    # 並び: 新着 → 出品中(買える)優先 → 金ロフト濃厚/要確認 → ハズレ。各内で価格安い順。
    items = sorted(
        items,
        key=lambda r: (not r.get("is_new"),
                       r["status"] != "active",
                       CODE_ORDER.get(r["loft_code"], 5),
                       r["price"] if r["price"] is not None else 10**9),
    )
    now = jst_now().strftime("%Y-%m-%d %H:%M")
    cards = []
    for r in items:
        badge_new = '<span class="b new">⭐NEW</span>' if r.get("is_new") else ""
        sold = r["status"] == "sold"
        badge_status = ('<span class="b sold">売却済</span>' if sold
                        else '<span class="b buy">買える</span>')
        cls = CODE_CLASS.get(r["loft_code"], "check")
        price = f"¥{r['price']:,}" if r["price"] is not None else "—"
        meta = " / ".join(x for x in [
            r["source"],
            f"状態{r['cond']}" if r["cond"] and r["source"] == "ゴルフパートナー" else "",
            r["cond"] if r["cond"] and sold else "",   # 売却済は終了日
            f"{r['year']}年式" if r["year"] else "",
        ] if x)
        shaft = html.escape(r["shaft"]) if r["shaft"] else ""
        cards.append(f"""
      <a class="card {cls}{' soldcard' if sold else ''}" href="{html.escape(r['url'])}" target="_blank" rel="noopener">
        <div class="imgwrap">
          <img loading="lazy" src="{html.escape(r['img'])}" alt=""
               onerror="this.style.opacity=.15;this.alt='画像なし'">
          {badge_new}{badge_status}
        </div>
        <div class="body">
          <div class="title">{html.escape(r['title'])}</div>
          <div class="loft {cls}">{html.escape(r['loft_label'])}</div>
          <div class="price">{price}</div>
          <div class="meta">{html.escape(meta)}</div>
          <div class="shaft">{shaft}</div>
        </div>
      </a>""")

    gold = sum(1 for r in items if r["loft_code"] == "gold")
    buyable = sum(1 for r in items if r["status"] == "active")
    return TEMPLATE.format(
        now=now, total=len(items), new=new_count, gold=gold, buyable=buyable,
        cards="\n".join(cards) or '<p class="empty">該当なし。次回スキャンをお待ちください。</p>',
        golfdo=html.escape(GOLFDO_SEARCH),
    )


TEMPLATE = """<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>カムイ TP-07 金ロフト・ガスのみ ハンター</title>
<style>
  :root{{color-scheme:dark}}
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
    background:#0d1117;color:#e6edf3}}
  header{{padding:18px 16px;background:linear-gradient(135deg,#1a2330,#0d1117);
    border-bottom:1px solid #30363d;position:sticky;top:0;z-index:5}}
  h1{{margin:0 0 4px;font-size:18px}}
  .sub{{font-size:12px;color:#8b949e}}
  .stats{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}
  .stat{{background:#161b22;border:1px solid #30363d;border-radius:8px;
    padding:6px 10px;font-size:12px}}
  .stat b{{font-size:16px}}
  .note{{font-size:12px;color:#8b949e;margin:10px 16px 0;line-height:1.6}}
  .note a{{color:#58a6ff}}
  .grid{{display:grid;gap:12px;padding:16px;
    grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}}
  .card{{display:flex;flex-direction:column;background:#161b22;
    border:1px solid #30363d;border-radius:12px;overflow:hidden;
    text-decoration:none;color:inherit;transition:.15s}}
  .card:hover{{transform:translateY(-2px);border-color:#58a6ff}}
  .card.gold{{border-color:#d4af37;box-shadow:0 0 0 1px #d4af37 inset}}
  .imgwrap{{position:relative;aspect-ratio:1/1;background:#0d1117}}
  .imgwrap img{{width:100%;height:100%;object-fit:cover}}
  .b{{position:absolute;font-size:11px;font-weight:700;padding:3px 7px;border-radius:6px}}
  .b.new{{top:8px;left:8px;background:#f85149;color:#fff}}
  .b.buy{{top:8px;right:8px;background:#238636;color:#fff}}
  .b.sold{{top:8px;right:8px;background:#6e7681;color:#fff}}
  .soldcard{{opacity:.6}}
  .body{{padding:10px 12px 12px}}
  .title{{font-size:13px;font-weight:600;line-height:1.4;margin-bottom:6px}}
  .loft{{display:inline-block;font-size:11px;padding:3px 8px;border-radius:6px;
    margin-bottom:6px}}
  .loft.gold{{background:#3a2f00;color:#ffd54a;border:1px solid #d4af37}}
  .loft.check{{background:#1c2733;color:#79c0ff;border:1px solid #1f6feb}}
  .loft.miss{{background:#21262d;color:#8b949e;border:1px solid #30363d}}
  .price{{font-size:16px;font-weight:700}}
  .meta{{font-size:11px;color:#8b949e;margin-top:2px}}
  .shaft{{font-size:11px;color:#6e7681;margin-top:4px;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .empty{{padding:40px;text-align:center;color:#8b949e}}
  footer{{padding:24px 16px;color:#6e7681;font-size:11px;text-align:center}}
</style></head><body>
<header>
  <h1>🌀 カムイ TP-07 金ロフト・ガスのみ ハンター</h1>
  <div class="sub">最終スキャン {now}（JST）・GP／ゴルフドゥ／ヤフオク／Yahoo!フリマ／ラクマ</div>
  <div class="stats">
    <div class="stat">候補 <b>{total}</b></div>
    <div class="stat">🟢買える <b>{buyable}</b></div>
    <div class="stat">⭐新着 <b>{new}</b></div>
    <div class="stat">金ロフト濃厚 <b>{gold}</b></div>
  </div>
</header>
<p class="note">
  <b>🟢買える</b>＝出品中（ゴルフパートナー／ヤフオク）。<b>売却済</b>＝相場の参考。<br>
  フリマ／オクは出品者が「ガスのみ／発泡／爆音」を明記するので
  <b>金ロフト・ガスのみ濃厚 ★</b>か<b>発泡（ハズレ）</b>を自動判定。
  中古ショップ（ゴルフパートナー／ゴルフドゥ）は無記載が多く<b>「要確認」</b>＝
  サムネのロフト刻印（LOFT 9 等）が<b>金色</b>なら当たり、赤/白ならハズレ。
  カードをタップで商品ページへ。<br>
  <a href="contact_sheet.jpg" target="_blank" rel="noopener">▶ 要確認の全候補を1枚で見る（ピンチズーム可）</a>
  ／<a href="{golfdo}" target="_blank" rel="noopener">ゴルフドゥで手動検索</a>
</p>
<div class="grid">
{cards}
</div>
<footer>自動生成 / 個人用ツール</footer>
</body></html>"""


def build_contact_sheet(items: list[dict], path: str, cols: int = 6, th: int = 230) -> bool:
    """全候補のヘッド写真を1枚に並べる（金ロフトを一目で探すため）。

    PIL未導入や取得失敗時は静かにスキップ。価格安い順で並べる。
    """
    try:
        import io
        import math
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    # 写真目視が要る「要確認(check)」だけを並べる＝金ロフト判定ボード
    check = [r for r in items if r["loft_code"] == "check"]
    ordered = sorted(check, key=lambda r: (r["price"] if r["price"] is not None else 10**9))
    if not ordered:
        return False
    sess = _session()
    pad = 22
    rows = math.ceil(len(ordered) / cols)
    sheet = Image.new("RGB", (cols * th, rows * (th + pad)), (20, 24, 30))
    draw = ImageDraw.Draw(sheet)
    for i, it in enumerate(ordered):
        try:
            data = sess.get(it["img"], timeout=20).content
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((th, th))
        except Exception:
            im = Image.new("RGB", (th, th), (40, 40, 40))
        x = (i % cols) * th
        y = (i // cols) * (th + pad)
        sheet.paste(im, (x, y + pad))
        tag = "NEW " if it.get("is_new") else ""
        price = f"Y{it['price']:,}" if it["price"] is not None else ""
        draw.text((x + 4, y + 5), f"{tag}#{i:02d} {price}", fill=(255, 255, 255))
    sheet.save(path, quality=85)
    return True


def publish(new_count: int) -> None:
    """生成物を GitHub Pages 用リポジトリに push（外出先からスマホで閲覧）。"""
    stamp = jst_now().strftime("%Y-%m-%d %H:%M")
    msg = f"scan {stamp}" + (f" / 新着{new_count}件" if new_count else "")
    files = ["index.html", "contact_sheet.jpg", "state.json"]
    files = [f for f in files if os.path.exists(os.path.join(HERE, f))]
    try:
        subprocess.run(["git", "-C", HERE, "add", *files], check=True)
        # 変更が無ければ commit はスキップ
        diff = subprocess.run(["git", "-C", HERE, "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            print("  公開: 変更なし（push省略）")
            return
        subprocess.run(["git", "-C", HERE, "commit", "-m", msg], check=True)
        subprocess.run(["git", "-C", HERE, "push"], check=True)
        print("  公開: push 完了")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  公開: スキップ（git未設定？） {e}")


def main() -> None:
    do_publish = "--publish" in sys.argv
    print("スキャン開始 …")
    items = collect()
    print(f"  TP-07 候補: {len(items)} 件")
    seeding = not os.path.exists(STATE_PATH)
    state = load_state()
    new_count = mark_new(items, state, seeding)
    save_state(state)
    out = render(items, new_count)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(out)
    sheet_path = os.path.join(HERE, "contact_sheet.jpg")
    if build_contact_sheet(items, sheet_path):
        print(f"  一覧画像: {sheet_path}")
    print(f"  新着: {new_count} 件")
    print(f"  生成: {OUT_PATH}")
    if new_count:
        print(f"  ★★ 新着 {new_count} 件あり！ページを確認してください ★★")
    if do_publish:
        publish(new_count)


if __name__ == "__main__":
    main()
