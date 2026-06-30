# 🌀 カムイ TP-07 金ロフト・ガスのみ ハンター

カムイ タイフーンプロ **TP-07** の中で、特に珍しい
**「金ロフト＝ガスのみ＝金属バットのような爆音」モデル**を取りこぼさず探すための監視ツール。

中古ショップに“ただの TP-07”としてこっそり並ぶ金ロフト個体を、写真付きで一覧化する。

## 公開ページ（スマホ可）
https://nekokaitaidesu-cpu.github.io/kamui-tp07-finder/
（GitHub Actions が6時間ごとに自動スキャン→Pages 自動更新。PCの電源に依存しない）

## 仕組み

1. 複数ソースを巡回（ドライバーのみ。FW/UTは除外）：
   - **ゴルフパートナー**中古（「タイフーン」「カムイ」全ページ）＝写真目視前提
   - **ゴルフドゥ**中古（Playwrightで `/club/model`→`/club/list` を描画取得）
   - **ヤフオク 出品中**（買える）
   - **ヤフオク落札／Yahoo!フリマ売却**（相場の参考）
2. タイトルから **TP-07 だけ**を抽出（03/05 などは除外）
3. 判定：フリマ/オクは出品者が明記するので「ガスのみ/爆音/金→**金ロフト濃厚★**」「発泡/NITRO→**ハズレ**」を自動振り分け。中古ショップは無記載が多く「**要確認**」＝写真目視。
4. 前回スキャンからの **新着を検知**（`state.json` に既知IDを記録）
5. 写真サムネ付き **`index.html`**＋「要確認」だけ並べた金ロフト判定ボード **`contact_sheet.jpg`** を生成

### 金ロフトの見分け方（重要）
ショップのタイトルには「金/赤/白」はほぼ書かれない。だからこのツールは
**TP-07候補を全部集めて写真を並べる**ところまでをやり、最終判定は写真の目視で行う。

- サムネのロフト刻印（`LOFT 9` 等）が **金色** → 当たり（ガスのみ・爆音）★
- **赤 / 白** → ハズレ（ガス＋発泡の標準モデル）
- 別物注意：地金が丸ごと金色の **「NITROGEN」フィニッシュ**は探している黒ヘッド金ロフトとは別

## 使い方

```bash
cd C:\Users\User\Claude\kamui-tp07-finder
python finder.py
```

実行後、`index.html` をブラウザで開く。新着があればコンソールに
`★★ 新着 N 件あり！★★` と出て、ページ上部に ⭐NEW バッジが付く。

依存: `pip install -r requirements.txt` ＋ 初回のみ `python -m playwright install chromium`
（Playwright未導入でもゴルフドゥをスキップして他ソースは動く）

## 毎日自動でスキャンする（任意）

Windows タスクスケジューラに登録すると放置で監視できる：

```powershell
schtasks /create /tn "KamuiTP07Finder" /sc daily /st 07:30 ^
  /tr "python \"C:\Users\User\Claude\kamui-tp07-finder\finder.py\""
```

## メモ / 今後
- **ゴルフドゥ対応済**：フリーワード検索は `/club/model?search=` → `/club/list/{id}`（NaviPlus系UI）。`/supplies/list` 側にはフリーワード検索が無くカムイはメーカー一覧にも無いため、Playwright で実描画して取得（`golfdo.py`）。CI でも `playwright install chromium` 済。
- **メルカリ**は対策が強く未対応。ヤフオク／Yahoo!フリマ／ゴルフドゥ／ゴルフパートナーはカバー済み。
- 追加ソースも同じ item 辞書（`source`/`status`/`loft_code`）に合わせれば差し込める。
