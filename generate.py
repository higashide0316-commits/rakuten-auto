# -*- coding: utf-8 -*-
"""
=====================================================================
 楽天アフィリエイト 記事 自動作成システム（全部入り1ファイル版）
=====================================================================

 このファイル1つだけで動きます。

 使い方:
   python generate.py           … 本番（楽天から商品を取ってきて記事を作る）
   python generate.py --demo    … お試し（にせ物データで見た目だけ確認）
   python generate.py --check   … 楽天APIにつながるかテストする
   python generate.py --post    … Xに1件つぶやく（未投稿のものから順に）

 ★ 設定を変えたいときは、下の「設定エリア」だけ書き換えてください。
   それより下は、意味が分からなければ触らなくて大丈夫です。
"""

import datetime
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


# #####################################################################
#
#   ここから設定エリア（ここだけ書き換えればOK）
#
# #####################################################################

# --- ブログの名前と説明 ---------------------------------------------
SITE_TITLE = "RankLab"
SITE_DESCRIPTION = "楽天市場の売れ筋を、価格・評価・レビュー数で毎日データ集計。買う前の下調べに。"

# サイトのアドレス（sitemap.xml を作るのに使います）
SITE_URL = "https://k-ranklab.github.io/"

# トップページに並べる記事の数
TOP_PAGE_ARTICLE_COUNT = 30


# --- どんな記事を作るか ---------------------------------------------
# 1回の実行で、下の { } のかたまり1つにつき記事が1本できます。
#
#   "kind"      : "ranking"（売れ筋ランキング） / "search"（キーワード検索）
#   "slug"      : ファイル名に使う英数字（他とかぶらないように）
#   "title"     : 記事の見出し。{date}=日付 {n}=商品数 {kw}=キーワード に置き換わる
#   "genre_id"  : 楽天のジャンル番号（0 = 全ジャンル）
#   "hits"      : 記事に載せる商品数（最大30）
#
THEMES = [
    {
        "kind": "ranking",
        "slug": "sougou",
        "category": "総合ランキング",
        "title": "【{date}】楽天市場 総合ランキング TOP{n}｜今いちばん売れている商品",
        "lead": (
            "楽天市場でいま実際によく売れている商品を、リアルタイムの総合ランキングから"
            "上位{n}件ピックアップしました。ジャンルを問わず売れているものが並ぶので、"
            "「世の中で何が流行っているか」がひと目で分かります。"
        ),
        "genre_id": 0,
        "hits": 10,
    },
    {
        "kind": "ranking",
        "slug": "golf",
        "category": "ゴルフ用品",
        "title": "【{date}】ゴルフ用品 売れ筋ランキング TOP{n}｜クラブ・ボール・ウェア",
        "lead": (
            "楽天市場のゴルフカテゴリで、いま実際によく売れている商品を上位{n}件まとめました。"
            "クラブ、ボール、シューズ、ウェアまでジャンル横断で並ぶので、"
            "「今シーズン何が支持されているか」がひと目で分かります。"
        ),
        # 101077 = ゴルフ（スポーツ・アウトドア配下）
        "genre_id": 101077,
        "hits": 10,
    },
    {
        "kind": "search",
        "slug": "harley",
        "category": "ハーレー用品",
        "title": "【{date}】ハーレー用品 人気ランキング TOP{n}｜{kw} のおすすめ",
        "lead": (
            "楽天市場で買えるハーレーダビッドソン向けのパーツ・用品の中から、"
            "「{kw}」でレビュー評価の高い商品を{n}件集めました。"
            "カスタムやメンテナンスの参考にどうぞ。"
        ),
        # 200305 = バイク用品（楽天のジャンル番号）
        "genre_id": 200305,
        "hits": 10,
        # 毎日ちがう記事になるよう、キーワードを日替わりで切り替えます
        "keyword_rotation": [
            "ハーレー マフラー",
            "ハーレー シート",
            "ハーレー ハンドル",
            "ハーレー エアクリーナー",
            "ハーレー ミラー",
            "ハーレー サドルバッグ",
            "ハーレーダビッドソン グッズ",
        ],
        # -reviewCount = レビューが多い順（＝売れている目安）
        "sort": "-reviewCount",
    },
]


# --- 記事の先頭に出す写真（任意）--------------------------------------
# カテゴリ名 → 画像ファイルの場所。docs/img/ に置いた自分の写真を指定します。
# 自分で撮った写真を載せると「実物を持っている人が運営しているサイト」に見え、
# 他の自動生成サイトとの違いが出ます。
# 使わないカテゴリは書かなければ、写真なしで表示されます。
#
#   ★写真は「何枚でも」並べて書けます。[ ] の中にカンマ区切りで足すだけです。
#     日付が変わるたびに、上から順に自動で切り替わります。
#     （例：3枚なら 3日で一周して、また1枚目に戻ります）
#     毎日同じ写真にならないので、何度も来る読者にも飽きられません。
#   ★1枚だけにしたいときは、1行だけ書けばOKです。

CATEGORY_IMAGES = {
    "ハーレー用品": [
        "img/harley.jpg",    # 外に出したチョッパーの横向き
        "img/harley2.jpg",   # お店でのリア周りの寄り
        "img/harley3.jpg",   # 林道のツーリング
        "img/harley4.jpg",   # サスペンションの採寸
    ],
    "ゴルフ用品": [
        "img/golf.jpg",      # ゴルフ場
    ],
    "総合ランキング": [
        "img/life1.jpg",     # 猫
        "img/life2.jpg",     # 屋外のカフェ
    ],
}

# 写真の下に出す小さな説明（空にすると出ません）
PHOTO_CREDIT = "写真：当サイト運営者が撮影"


# --- SNSでリンクを貼ったときに出る大きな画像（OGP画像）----------------
# X や LINE に記事のURLを貼ると、この画像が大きなカードで表示されます。
# ここが空っぽだと味気ないリンクになるので、1枚用意しておくと効果的です。
# 画像は docs/img/ に置き、1200×630ピクセルで作るのが標準です。
# 空（""）にすると、この機能は使いません。

OG_IMAGE = "img/ogp.png"


# --- フッターに出すバナー（任意）-------------------------------------
# 楽天アフィリエイトで発行したバナーのHTMLを、そのまま貼り付けてください。
# 全ページのフッターに、小さく1枚だけ表示されます。
#
#   ★AMP用のコード（<amp-img> で始まるもの）を貼っても大丈夫です。
#     普通のHTML用に自動で直してから表示します。
#   ★空（""）にすると、バナーは表示されません。
#
# おすすめは「お買い物マラソン」「スーパーSALE」などの
# 期間限定キャンペーンのバナーです。読者にとって「いま買うと得」という
# 情報になるので、ただの広告より嫌がられにくく、クリックもされやすいです。
# セールが終わったら、新しいバナーのコードに貼り替えてください。

FOOTER_BANNER = """
<a href="https://hb.afl.rakuten.co.jp/hsc/56abac8a.d0a8ffd6.56aba98d.e1143982/?link_type=pict&ut=eyJwYWdlIjoic2hvcCIsInR5cGUiOiJwaWN0IiwiY29sIjoxLCJjYXQiOiI0NCIsImJhbiI6Mjc5NDkyMSwiYW1wIjp0cnVlfQ%3D%3D" target="_blank" rel="nofollow sponsored noopener"><amp-img src="https://hbb.afl.rakuten.co.jp/hsb/56abac8a.d0a8ffd6.56aba98d.e1143982/?me_id=1&me_adv_id=2794921&t=pict" alt="" layout="fixed" height="60" width="234"></amp-img></a>
"""

# バナーの上に出す小さな見出し（空にすると出ません）
FOOTER_BANNER_LABEL = "楽天市場のキャンペーン"


# --- SNS（X）への自動投稿 ---------------------------------------------
# 1回の実行で何件つぶやくか。X APIは1投稿あたり約1.5円かかります。
#   1件 × 1日6回実行 = 1日6投稿 → 月およそ270円
# 減らしたいときは、投稿用ワークフローの実行間隔を広げてください。
SNS_POSTS_PER_RUN = 1


# --- 楽天APIの細かい設定（基本さわらなくてOK）------------------------
REQUEST_INTERVAL_SEC = 2.0   # 連続アクセスの間隔（秒）。短すぎると怒られます
MAX_RETRY = 3                # 失敗したときのやり直し回数
AVAILABILITY = 1             # 1 = 在庫のある商品だけ
IMAGE_FLAG = 1               # 1 = 画像のある商品だけ


# #####################################################################
#
#   ここから下はプログラム本体です
#
# #####################################################################

# 楽天APIの住所（2026年5月の新仕様）
RANKING_URL = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"

# このファイルが置いてある場所を基準にする
ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(ROOT, "docs")
POSTS_DIR = os.path.join(DOCS_DIR, "posts")
DATA_FILE = os.path.join(ROOT, "data", "posts.json")

# 日本時間（GitHubのサーバーは世界標準時なのでズレを直す）
JST = datetime.timezone(datetime.timedelta(hours=9))

# ★ 景品表示法（ステマ規制）対応。この表記は消さないでください。
PR_NOTICE = "本ページはプロモーションを含みます（楽天アフィリエイト）"


class RakutenApiError(Exception):
    """楽天APIでエラーが起きたときに使う、専用のエラーの型"""


# ---------------------------------------------------------------------
#  1. 楽天APIとの通信
# ---------------------------------------------------------------------

def get_credentials():
    """GitHubのSecrets（環境変数）から、秘密の値を取り出す"""
    app_id = os.environ.get("RAKUTEN_APP_ID", "").strip()
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY", "").strip()
    affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID", "").strip()

    if not app_id:
        raise RakutenApiError(
            "RAKUTEN_APP_ID が設定されていません。\n"
            "GitHub の Settings > Secrets and variables > Actions で登録してください。"
        )
    if not access_key:
        raise RakutenApiError(
            "RAKUTEN_ACCESS_KEY が設定されていません。\n"
            "2026年5月の新仕様から必須になりました。楽天ウェブサービスの管理画面で確認できます。"
        )
    if not affiliate_id:
        raise RakutenApiError(
            "RAKUTEN_AFFILIATE_ID が設定されていません。\n"
            "https://webservice.rakuten.co.jp/account_affiliate_id で確認できます。\n"
            "これが無いと、商品が売れても報酬が発生しません。"
        )
    return app_id, access_key, affiliate_id


def build_headers(access_key):
    """
    楽天に送る「送り状」を作る。

    Referer / Origin は、楽天のアプリ登録で入れた「許可ウェブサイト」と
    そろえる必要があります（IPが毎回変わるGitHub Actionsから呼ぶための工夫）。
    """
    headers = {
        "User-Agent": "rakuten-auto-blog/1.0",
        "Accept": "application/json",
        "accessKey": access_key,
    }
    referer = os.environ.get("RAKUTEN_REFERER", "").strip()
    if referer:
        headers["Referer"] = referer
        parsed = urllib.parse.urlparse(referer)
        if parsed.scheme and parsed.netloc:
            headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    return headers


def call_api(url, params):
    """楽天APIを呼ぶ。失敗したらやり直す。"""
    app_id, access_key, affiliate_id = get_credentials()

    base = dict(params)
    base["applicationId"] = app_id
    base["affiliateId"] = affiliate_id
    base["format"] = "json"
    base["formatVersion"] = 2

    headers = build_headers(access_key)
    last_error = None

    for attempt in range(1, MAX_RETRY + 1):
        p = dict(base)
        # 1回目はヘッダーで、2回目以降はクエリでもキーを送ってみる
        if attempt > 1:
            p["accessKey"] = access_key

        try:
            full_url = url + "?" + urllib.parse.urlencode(p)
            req = urllib.request.Request(full_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read().decode("utf-8"))

        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            last_error = f"HTTP {e.code}: {detail}"

            if e.code == 403 and "CLIENT_IP_NOT_ALLOWED" in detail:
                last_error += (
                    "\n\n【原因】アプリを「API/バックエンドサービス」型で登録すると、"
                    "登録したIPアドレスからしかアクセスできません。"
                    "GitHub ActionsはIPが毎回変わるので弾かれます。\n"
                    "【対処】楽天ウェブサービスの管理画面でアプリのタイプを"
                    "「ウェブフロントエンド」系に変え、「許可ウェブサイト」に"
                    "GitHub Pagesのドメインを登録し、Secretsに RAKUTEN_REFERER を設定してください。"
                )
            elif e.code in (400, 401):
                last_error += (
                    "\n\n【原因】アプリIDかアクセスキーが違う可能性があります。"
                    "2026年5月以降は両方が必須で、形式も変わっています。古いIDは使えません。"
                )
            elif e.code == 429:
                last_error += "\n\n【原因】アクセスしすぎです。REQUEST_INTERVAL_SEC を増やしてください。"

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"

        if attempt < MAX_RETRY:
            wait = REQUEST_INTERVAL_SEC * attempt
            print(f"  ! 失敗しました（{attempt}回目）。{wait:.1f}秒待って再試行します。")
            time.sleep(wait)

    raise RakutenApiError(f"楽天APIの呼び出しに{MAX_RETRY}回失敗しました。\n{last_error}")


def as_int(v, default=0):
    """どんな形で来ても整数にする（ダメなら default）"""
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def as_float(v, default=0.0):
    """どんな形で来ても小数にする（ダメなら default）"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def normalize(raw_items):
    """楽天から返ってきたデータを、記事に使いやすい形に整える"""
    result = []
    for raw in raw_items:
        item = raw.get("Item", raw) if isinstance(raw, dict) else {}

        image_urls = item.get("mediumImageUrls") or item.get("smallImageUrls") or []
        image_url = ""
        if image_urls:
            first = image_urls[0]
            image_url = first.get("imageUrl", "") if isinstance(first, dict) else str(first)
            image_url = image_url.split("?")[0] + "?_ex=400x400"

        link = item.get("affiliateUrl") or item.get("itemUrl") or ""
        if not link:
            continue

        # ★重要★ 楽天のAPIは、同じ項目でも「数値」で返ってきたり
        # 「文字列」で返ってきたりします（ランキングAPIと検索APIで違う）。
        # 型が混ざったまま大小を比べるとプログラムが止まるので、ここでそろえます。
        result.append({
            "rank": as_int(item.get("rank"), 0) or None,
            "name": (item.get("itemName") or "").strip(),
            "price": as_int(item.get("itemPrice")),
            "url": link,
            "image": image_url,
            "shop": (item.get("shopName") or "").strip(),
            "review_count": as_int(item.get("reviewCount")),
            "review_average": as_float(item.get("reviewAverage")),
            "caption": (item.get("itemCaption") or "").strip(),
            "point_rate": as_int(item.get("pointRate"), 1) or 1,
            # 0 = 送料込み / 1 = 送料別 / -1 = 情報なし
            "postage_flag": as_int(item.get("postageFlag"), -1),
        })
    return result


def fetch_ranking(genre_id=0, hits=10):
    """売れ筋ランキングを取ってくる"""
    params = {"period": "realtime"}
    if genre_id:
        params["genreId"] = genre_id
    data = call_api(RANKING_URL, params)
    time.sleep(REQUEST_INTERVAL_SEC)
    items = normalize(data.get("Items", []))

    # ★重要★ 楽天のランキングAPIは、順位が降順（30位→1位）で返ってくることがあります。
    # そのまま先頭10件を取ると「30位〜21位」になってしまうので、
    # 必ず1位が先頭に来るよう並べ直してから上位を取り出します。
    items.sort(key=lambda x: x["rank"] if isinstance(x.get("rank"), int) else 9999)
    return items[:hits]


def fetch_search(keyword, genre_id=0, hits=10, sort="-reviewCount"):
    """キーワードで商品を検索する"""
    params = {
        "keyword": keyword,
        "hits": min(int(hits), 30),
        "sort": sort,
        "imageFlag": IMAGE_FLAG,
        "availability": AVAILABILITY,
    }
    if genre_id:
        params["genreId"] = genre_id
    data = call_api(SEARCH_URL, params)
    time.sleep(REQUEST_INTERVAL_SEC)
    return normalize(data.get("Items", []))[:hits]


# ---------------------------------------------------------------------
#  2. 見た目（HTMLとCSS）
# ---------------------------------------------------------------------

CSS = """
:root{
  --bg:#f4f6f8; --card:#ffffff; --line:#e2e7ee; --line2:#eef2f6;
  --text:#1b2027; --muted:#5d6874; --price:#c62828;
  --link:#1462b8; --gold:#b8860b; --ok:#0f7b52;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.10);
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",
              "Yu Gothic UI",Meiryo,sans-serif;
  line-height:1.8; font-size:16px; -webkit-text-size-adjust:100%;
}
a{color:var(--link);}
.wrap{max-width:900px; margin:0 auto; padding:0 16px 72px;}

/* ---- ヘッダー ---- */
header.site{background:#fff; border-bottom:1px solid var(--line); padding:16px;}
header.site .inner{max-width:900px; margin:0 auto;
  display:flex; align-items:center; gap:12px; flex-wrap:wrap;}
header.site .logo{font-size:19px; font-weight:800; letter-spacing:.01em;
  color:var(--text); text-decoration:none; margin:0;}
header.site .tag{font-size:12px; color:var(--muted); margin:0; width:100%;}
.pr-bar{background:#fff8e1; border-bottom:1px solid #f0e2b6;
  color:#7a5b00; font-size:11.5px; padding:6px 16px; text-align:center;}

/* ---- パンくず ---- */
.crumbs{font-size:12px; color:var(--muted); margin:16px 0 10px;}
.crumbs a{color:var(--muted); text-decoration:none;}
.crumbs a:hover{color:var(--link); text-decoration:underline;}

/* ---- 見出し ---- */
figure.hero{margin:12px 0 18px; border-radius:14px; overflow:hidden;
  border:1px solid var(--line); box-shadow:var(--shadow); background:#fff;}
figure.hero img{display:block; width:100%; height:auto;}
figure.hero figcaption{font-size:11.5px; color:var(--muted);
  padding:7px 12px; background:#fbfcfd; border-top:1px solid var(--line2);}
h1.article-title{font-size:25px; line-height:1.5; margin:6px 0 10px; font-weight:800;
  letter-spacing:-.01em;}
h2.sec{font-size:19px; margin:38px 0 14px; padding-left:11px;
  border-left:4px solid var(--link); line-height:1.5;}
.meta{color:var(--muted); font-size:12.5px; margin:0 0 22px;
  display:flex; gap:10px; flex-wrap:wrap; align-items:center;}
.chip{display:inline-block; padding:2px 9px; border-radius:99px;
  background:#eaf1fb; color:#1a5fae; font-size:11.5px; font-weight:700;}

/* ---- 結論ボックス ---- */
.verdict{background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:18px 18px 6px; box-shadow:var(--shadow); margin-bottom:26px;}
.verdict h2{font-size:16px; margin:0 0 14px; padding:0; border:0;
  display:flex; align-items:center; gap:8px;}
.verdict h2::before{content:"✓"; display:inline-flex; align-items:center;
  justify-content:center; width:20px; height:20px; border-radius:50%;
  background:var(--ok); color:#fff; font-size:12px; font-weight:700;}
.vrow{display:flex; gap:12px; padding:11px 0; border-top:1px solid var(--line2);
  font-size:14px; align-items:flex-start;}
.vrow:first-of-type{border-top:0;}
.vlabel{flex:0 0 108px; color:var(--muted); font-size:12.5px; font-weight:700;
  padding-top:2px;}
.vbody{flex:1 1 auto; min-width:0;}
.vbody a{font-weight:700; text-decoration:none;}
.vbody a:hover{text-decoration:underline;}
.vbody .p{color:var(--price); font-weight:800; margin-left:6px; white-space:nowrap;}

/* ---- 目次 ---- */
.toc{background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:14px 18px; margin-bottom:28px; box-shadow:var(--shadow);}
.toc p{margin:0 0 8px; font-weight:800; font-size:14px;}
.toc ol{margin:0; padding-left:20px; font-size:14px;}
.toc li{margin:3px 0;}
.toc a{text-decoration:none;}
.toc a:hover{text-decoration:underline;}

/* ---- データサマリー ---- */
.stats{display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:8px;}
@media (max-width:560px){ .stats{grid-template-columns:repeat(2,1fr);} }
.stat{background:#fff; border:1px solid var(--line); border-radius:10px;
  padding:13px 12px; text-align:center; box-shadow:var(--shadow);}
.stat .k{font-size:11px; color:var(--muted); margin:0 0 4px; font-weight:700;}
.stat .v{font-size:18px; font-weight:800; margin:0; letter-spacing:-.02em;}
.stat .s{font-size:10.5px; color:var(--muted); margin:2px 0 0;}
.note{font-size:12px; color:var(--muted); margin:10px 0 0;}

/* ---- 比較表 ---- */
.tablewrap{overflow-x:auto; -webkit-overflow-scrolling:touch;
  border:1px solid var(--line); border-radius:12px; background:#fff;
  box-shadow:var(--shadow);}
table.cmp{border-collapse:collapse; width:100%; font-size:13.5px; min-width:560px;}
table.cmp th,table.cmp td{padding:11px 12px; text-align:left;
  border-bottom:1px solid var(--line2); vertical-align:middle;}
table.cmp thead th{background:#f7f9fc; font-size:12px; color:var(--muted);
  font-weight:700; white-space:nowrap;}
table.cmp tbody tr:last-child td{border-bottom:0;}
table.cmp td.name{min-width:230px;}
table.cmp td.name a{color:var(--text); text-decoration:none; font-weight:600;}
table.cmp td.name a:hover{color:var(--link); text-decoration:underline;}
table.cmp td.pr{color:var(--price); font-weight:800; white-space:nowrap;}
table.cmp td.num{white-space:nowrap;}

/* ---- 商品カード ---- */
.item{background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:18px; margin-bottom:16px; box-shadow:var(--shadow);}
.ihead{display:flex; gap:10px; align-items:flex-start; margin-bottom:12px;}
.rank{flex:0 0 auto; display:inline-flex; align-items:center; justify-content:center;
  min-width:30px; height:30px; padding:0 9px; border-radius:8px;
  background:#eef2f7; color:#3d4a5c; font-weight:800; font-size:14px;}
.rank.gold{background:linear-gradient(135deg,#f7d774,#d4a017); color:#4a3500;}
.rank.silver{background:linear-gradient(135deg,#dfe4ea,#adb5bd); color:#2f3640;}
.rank.bronze{background:linear-gradient(135deg,#e0aa7e,#b07642); color:#3b2408;}
.ihead h3{font-size:16px; margin:2px 0 0; line-height:1.55; font-weight:700;}
.ihead h3 a{color:var(--text); text-decoration:none;}
.ihead h3 a:hover{color:var(--link); text-decoration:underline;}
.ibody{display:flex; gap:16px;}
@media (max-width:560px){ .ibody{flex-direction:column;} }
.thumb{flex:0 0 150px; width:150px; height:150px; border-radius:10px;
  border:1px solid var(--line2); background:#fafbfc; overflow:hidden;
  display:flex; align-items:center; justify-content:center;}
@media (max-width:560px){ .thumb{width:100%; height:210px; flex:none;} }
.thumb img{width:100%; height:100%; object-fit:contain;}
.info{flex:1 1 auto; min-width:0;}
.badges{display:flex; flex-wrap:wrap; gap:6px; margin:0 0 10px;}
.badge{font-size:11px; font-weight:700; padding:3px 9px; border-radius:5px;
  border:1px solid transparent; white-space:nowrap;}
.b-cheap{background:#e8f6ef; color:#0f7b52; border-color:#bfe6d5;}
.b-star{background:#fff5e0; color:#a06800; border-color:#f2dfae;}
.b-rev{background:#eaf1fb; color:#1a5fae; border-color:#cadff5;}
.b-ship{background:#f2f0fb; color:#5b47b5; border-color:#ddd7f3;}
.b-pt{background:#fdeef0; color:#b3283a; border-color:#f7ccd3;}
.price{font-size:23px; font-weight:800; color:var(--price); margin:0 0 8px;
  letter-spacing:-.02em;}
.price .tax{font-size:12px; font-weight:600; color:var(--muted); margin-left:5px;}
.spec{list-style:none; margin:0 0 12px; padding:0; font-size:13px;}
.spec li{display:flex; gap:8px; padding:4px 0; border-bottom:1px dashed var(--line2);}
.spec li:last-child{border-bottom:0;}
.spec .sk{flex:0 0 78px; color:var(--muted); font-size:12px;}
.spec .sv{flex:1 1 auto; min-width:0;}
.stars{color:#f0a500; letter-spacing:.5px;}
.desc{font-size:13px; color:var(--muted); margin:0 0 14px; line-height:1.75;}
.btn{display:inline-block; padding:12px 26px; border-radius:8px;
  background:var(--price); color:#fff !important; text-decoration:none;
  font-weight:800; font-size:15px; box-shadow:0 2px 5px rgba(198,40,40,.28);}
.btn:hover{filter:brightness(1.07);}
.btnnote{font-size:11px; color:var(--muted); margin:8px 0 0;}

/* ---- 一覧 ---- */
.hero{background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:22px; margin:18px 0 26px; box-shadow:var(--shadow);}
.hero h1{margin:0 0 8px; font-size:21px; line-height:1.5;}
.hero p{margin:0; font-size:14px; color:var(--muted);}
ul.posts{list-style:none; padding:0; margin:0;}
ul.posts li{background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:16px 18px; margin-bottom:12px; box-shadow:var(--shadow);}
ul.posts a{color:var(--text); text-decoration:none; font-weight:700; font-size:15.5px;
  line-height:1.55; display:block;}
ul.posts a:hover{color:var(--link); text-decoration:underline;}
ul.posts .meta{margin:8px 0 0;}

/* ---- フッター ---- */
footer.site{margin-top:56px; padding:22px 0 0; border-top:1px solid var(--line);
  color:var(--muted); font-size:12.5px; line-height:1.85;}
footer.site a{color:var(--muted);}
footer.site .fnav{margin:0 0 12px;}
footer.site .fnav a{margin-right:14px;}
/* ---- トップページのカード ---- */
.lede{font-size:14px; color:var(--muted); margin:20px 0 4px;}
ul.cards{list-style:none; padding:0; margin:0;
  display:grid; grid-template-columns:repeat(2,1fr); gap:16px;}
@media (max-width:640px){ ul.cards{grid-template-columns:1fr;} }
.card{background:#fff; border:1px solid var(--line); border-radius:14px;
  overflow:hidden; box-shadow:var(--shadow); transition:transform .12s, box-shadow .12s;}
.card:hover{transform:translateY(-2px);
  box-shadow:0 6px 16px rgba(16,24,40,.12);}
.card a{display:block; text-decoration:none; color:inherit;}
.cthumb{height:150px; display:flex; align-items:stretch; gap:2px;
  background:#eef2f6; border-bottom:1px solid var(--line2); overflow:hidden;}
.cthumb .sh{position:relative; flex:1 1 0; min-width:0; background:#fff;
  display:flex; align-items:center; justify-content:center; overflow:hidden;}
.cthumb .sh img{width:100%; height:100%; object-fit:contain; padding:6px;}
.cthumb .sh i{position:absolute; left:5px; top:5px; font-style:normal;
  width:19px; height:19px; border-radius:5px; font-size:11px; font-weight:800;
  display:flex; align-items:center; justify-content:center;
  background:rgba(27,32,39,.72); color:#fff;}
.cthumb .sh:first-child i{background:linear-gradient(135deg,#f7d774,#d4a017); color:#4a3500;}
.cthumb .sh:first-child{flex:1.35 1 0;}
.cthumb .noimg{margin:auto; font-size:15px; font-weight:800;}
.cthumb .noimg{font-size:15px; font-weight:800; color:#fff; opacity:.9;}
.cbody{padding:14px 16px 16px;}
.cbadge{display:inline-block; padding:2px 9px; border-radius:99px;
  font-size:11px; font-weight:800; color:#fff; margin-bottom:8px;}
.card h3{margin:0 0 10px; font-size:15px; line-height:1.55; font-weight:700;}
.card:hover h3{color:var(--link);}
.cstat{margin:0 0 6px; font-size:12.5px; color:var(--muted);
  display:flex; gap:12px; flex-wrap:wrap; align-items:baseline;}
.cstat .pfrom b{color:var(--price); font-size:14px; font-weight:800;}
.cstat .prate{color:#a06800;}
.cdate{margin:0; font-size:11.5px; color:#9aa3af;}
/* カテゴリごとの色 */
.c-a{background:#1462b8;} .c-b{background:#0f7b52;} .c-c{background:#b3461e;}
.c-d{background:#6b3fa0;} .c-e{background:#a0761e;}
.cthumb.c-a,.cthumb.c-b,.cthumb.c-c,.cthumb.c-d,.cthumb.c-e{background:#f7f9fc;}
.cthumb.c-a .noimg{color:#1462b8;} .cthumb.c-b .noimg{color:#0f7b52;}
.cthumb.c-c .noimg{color:#b3461e;} .cthumb.c-d .noimg{color:#6b3fa0;}
.cthumb.c-e .noimg{color:#a0761e;}

.fbanner{text-align:center; margin:0 0 20px; padding:16px 0 18px;
  border-bottom:1px solid var(--line);}
.fbanner .fblabel{margin:0 0 8px; font-size:11.5px; color:var(--muted);
  letter-spacing:.04em;}
.fbanner a{display:inline-block; line-height:0;}
.prose h2{font-size:18px; margin:30px 0 10px; padding-left:11px;
  border-left:4px solid var(--link);}
.prose p,.prose li{font-size:14px; color:#333b45;}
"""


def esc(text):
    return html.escape(str(text if text is not None else ""))


def yen(n):
    try:
        return f"{int(n):,}円"
    except (TypeError, ValueError):
        return "―"


def stars(average):
    """4.3 → ★★★★☆ のような文字にする"""
    try:
        a = float(average)
    except (TypeError, ValueError):
        return ""
    if a <= 0:
        return ""
    full = int(a)
    half = 1 if a - full >= 0.5 else 0
    return "★" * full + ("☆" if half else "") + "☆" * (5 - full - half)


def rank_class(i):
    return {1: "rank gold", 2: "rank silver", 3: "rank bronze"}.get(i, "rank")


def shorten(text, n):
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + "…"


# =====================================================================
#  データ分析（ここが「独自の付加価値」になる部分）
# =====================================================================

def analyze(items):
    """
    取得した商品データを集計して、読者の判断材料を作る。

    単に商品を並べるだけでなく、「価格帯はどのあたりか」
    「どれが一番安いか」「どれが一番評価されているか」を
    数字で示すことで、ページに独自の意味が生まれます。
    """
    prices = sorted([int(i["price"]) for i in items if i.get("price")])
    reviewed = [i for i in items if (i.get("review_count") or 0) >= 3
                and (i.get("review_average") or 0) > 0]

    median = 0
    if prices:
        m = len(prices) // 2
        median = prices[m] if len(prices) % 2 else (prices[m - 1] + prices[m]) // 2

    avg_rating = 0.0
    if reviewed:
        avg_rating = round(sum(float(i["review_average"]) for i in reviewed) / len(reviewed), 2)

    free_ship = sum(1 for i in items if i.get("postage_flag") == 0)

    def pick(seq, key, reverse=True):
        seq = [x for x in seq if x.get(key)]
        return sorted(seq, key=lambda x: x[key], reverse=reverse)[0] if seq else None

    return {
        "count": len(items),
        "min_price": prices[0] if prices else 0,
        "max_price": prices[-1] if prices else 0,
        "median_price": median,
        "avg_rating": avg_rating,
        "rated_count": len(reviewed),
        "free_ship": free_ship,
        "cheapest": pick(items, "price", reverse=False),
        "best_rated": pick(reviewed, "review_average"),
        "most_reviewed": pick(items, "review_count"),
    }


def make_badges(item, stats):
    """データから機械的に判断できるバッジを付ける"""
    out = []
    # 「is」で比べているのは、同じ商品オブジェクトかどうかを厳密に見るためです。
    # URLや商品名で比べると、似た商品に同じバッジが付いてしまいます。
    if item is stats["cheapest"]:
        out.append(('b-cheap', 'この中で最安'))
    if item is stats["best_rated"]:
        out.append(('b-star', 'レビュー評価が最高'))
    if item is stats["most_reviewed"]:
        out.append(('b-rev', 'レビュー数が最多'))
    if item.get("postage_flag") == 0:
        out.append(('b-ship', '送料込み'))
    try:
        if int(item.get("point_rate") or 1) > 1:
            out.append(('b-pt', f'ポイント{int(item["point_rate"])}倍'))
    except (TypeError, ValueError):
        pass
    return out


# =====================================================================
#  ページ組み立て
# =====================================================================

def build_footer_banner():
    """
    設定に貼られたバナーHTMLを、普通のページで表示できる形に直す。

    楽天のリンク作成画面で「AMP対応」を選ぶと <amp-img> というタグで
    発行されますが、これはAMP専用のページでしか表示されません。
    普通の <img> に置き換えて、どのページでも出るようにします。
    """
    code = (FOOTER_BANNER or "").strip()
    if not code:
        return ""

    # <amp-img ...></amp-img> を <img ...> に置き換える
    code = re.sub(r"<amp-img\b", "<img", code)
    code = re.sub(r"</amp-img\s*>", "", code)
    # AMP専用の属性を消す
    code = re.sub(r'\s+layout="[^"]*"', "", code)
    # 画像の枠線を消して中央に置く
    code = re.sub(r"<img\b", '<img style="border:0;max-width:100%;height:auto" ', code, count=1)

    # 広告リンクとして正しい属性が付いているか念のため補う
    if "rel=" not in code:
        code = code.replace("<a ", '<a rel="nofollow sponsored noopener" ', 1)

    label = (FOOTER_BANNER_LABEL or "").strip()
    label_html = f'<p class="fblabel">{esc(label)}</p>' if label else ""
    return f'<div class="fbanner">{label_html}{code}</div>'


def pick_photo(category, date_key=None):
    """そのカテゴリに使う写真を1枚だけ選ぶ。

    CATEGORY_IMAGES に何枚書いてあっても、日付をもとに順ぐりに選びます。
    同じ日付なら必ず同じ写真になるので、記事を作り直しても写真は変わりません。
    """
    v = CATEGORY_IMAGES.get(category)
    if not v:
        return None
    # 昔の書き方（1枚を文字列で書いたもの）でも動くようにしておく
    if isinstance(v, str):
        return v
    photos = [p for p in v if p]
    if not photos:
        return None
    if len(photos) == 1:
        return photos[0]
    # 日付の中の数字をぜんぶ足して、その余りで写真を決める。
    # 1日進むと足し算の結果も1増えるので、写真が1枚ずつずれていきます。
    n = 0
    if date_key:
        for x in re.findall(r"\d+", str(date_key))[:3]:   # 年・月・日まで
            n += int(x)
    return photos[n % len(photos)]


def page_shell(title, body_html, is_top=False, description=None, extra_head=""):
    prefix = "" if is_top else "../"
    desc = description or SITE_DESCRIPTION
    # SNS用の大きな画像（OGP）。設定してあるときだけ入れる。
    og = ""
    if (OG_IMAGE or "").strip():
        og_url = SITE_URL.rstrip("/") + "/" + OG_IMAGE.lstrip("/")
        og = (f'<meta property="og:image" content="{esc(og_url)}">\n'
              f'<meta name="twitter:card" content="summary_large_image">\n'
              f'<meta name="twitter:image" content="{esc(og_url)}">')
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(shorten(desc, 120))}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(shorten(desc, 120))}">
<meta property="og:type" content="{'website' if is_top else 'article'}">
<meta property="og:site_name" content="{esc(SITE_TITLE)}">
{og}
<link rel="stylesheet" href="{prefix}style.css">\n<link rel="alternate" type="application/rss+xml" title="{esc(SITE_TITLE)}" href="{prefix}feed.xml">
{extra_head}
</head>
<body>
<div class="pr-bar">{esc(PR_NOTICE)}</div>
<header class="site">
  <div class="inner">
    <a class="logo" href="{prefix}index.html">{esc(SITE_TITLE)}</a>
    <p class="tag">{esc(SITE_DESCRIPTION)}</p>
  </div>
</header>
<div class="wrap">
{body_html}
<footer class="site">
{build_footer_banner()}
  <p class="fnav">
    <a href="{prefix}index.html">ホーム</a>
    <a href="{prefix}about.html">このサイトについて</a>
  </p>
  <p>{esc(PR_NOTICE)}当サイトは楽天ウェブサービスのAPIを利用して、
     楽天市場の公開データを自動で集計・掲載しています。</p>
  <p>掲載している価格・ポイント・送料・在庫状況は、記事の作成時点のものです。
     商品の購入前には、必ずリンク先の楽天市場の商品ページで最新の情報をご確認ください。</p>
  <p>&copy; {esc(SITE_TITLE)}</p>
</footer>
</div>
</body>
</html>
"""


def render_article(post, items):
    """記事1本分のHTMLを作る"""
    st = analyze(items)
    p = []

    p.append('<nav class="crumbs"><a href="../index.html">ホーム</a> ／ '
             f'{esc(post["category"])}</nav>')
    # カテゴリに写真が設定されていれば、記事の先頭に出す
    photo = pick_photo(post["category"], post.get("created_at"))
    if photo:
        cap = (f'<figcaption>{esc(PHOTO_CREDIT)}</figcaption>'
               if PHOTO_CREDIT else "")
        p.append(f'<figure class="hero"><img src="../{esc(photo)}" '
                 f'alt="{esc(post["category"])}" loading="lazy">{cap}</figure>')

    p.append(f'<h1 class="article-title">{esc(post["title"])}</h1>')
    p.append(f'<p class="meta"><span class="chip">{esc(post["category"])}</span>'
             f'<span>{esc(post["created_at"])} 時点のデータ</span>'
             f'<span>掲載 {st["count"]}件</span></p>')

    # --- 結論ボックス（このページの要点を先に示す）---
    def vrow(label, it, extra=""):
        if not it:
            return ""
        return (f'<div class="vrow"><div class="vlabel">{label}</div>'
                f'<div class="vbody"><a href="{esc(it["url"])}" target="_blank" '
                f'rel="nofollow sponsored noopener">{esc(shorten(it["name"], 46))}</a>'
                f'<span class="p">{esc(yen(it["price"]))}</span>{extra}</div></div>')

    br = st["best_rated"]
    mr = st["most_reviewed"]
    p.append('<div class="verdict"><h2>このページの要点</h2>'
             + vrow("いちばん安い", st["cheapest"])
             + vrow("評価がいちばん高い", br,
                    f'<span style="color:#a06800;font-size:12.5px;margin-left:6px">'
                    f'★{esc(br["review_average"])}</span>' if br else "")
             + vrow("レビューが最多", mr,
                    f'<span style="color:var(--muted);font-size:12.5px;margin-left:6px">'
                    f'{int(mr["review_count"]):,}件</span>' if mr else "")
             + '</div>')

    # --- 目次 ---
    p.append('<div class="toc"><p>目次</p><ol>'
             '<li><a href="#data">データで見る価格帯と評価</a></li>'
             '<li><a href="#cmp">上位商品の比較表</a></li>'
             '<li><a href="#list">商品ごとの詳細</a></li>'
             '<li><a href="#howto">このページの見方・注意点</a></li>'
             '</ol></div>')

    # --- データサマリー ---
    p.append('<h2 class="sec" id="data">データで見る価格帯と評価</h2>')
    p.append(f"""<div class="stats">
  <div class="stat"><p class="k">最安値</p><p class="v">{esc(yen(st["min_price"]))}</p></div>
  <div class="stat"><p class="k">中央値</p><p class="v">{esc(yen(st["median_price"]))}</p>
    <p class="s">ちょうど真ん中の価格</p></div>
  <div class="stat"><p class="k">最高値</p><p class="v">{esc(yen(st["max_price"]))}</p></div>
  <div class="stat"><p class="k">平均評価</p>
    <p class="v">{esc(st["avg_rating"]) if st["avg_rating"] else "―"}</p>
    <p class="s">レビュー3件以上 {st["rated_count"]}商品</p></div>
</div>""")
    p.append(f'<p class="note">掲載{st["count"]}件のうち、'
             f'<strong>{st["free_ship"]}件が送料込み</strong>です。'
             f'価格の中央値は{esc(yen(st["median_price"]))}なので、'
             f'これより安ければ「この中では割安」、高ければ「上位モデル寄り」と判断できます。</p>')

    # --- 比較表 ---
    p.append('<h2 class="sec" id="cmp">上位商品の比較表</h2>')
    rows = []
    for i, it in enumerate(items[:5], start=1):
        rv = (f'<span class="stars">{stars(it["review_average"])}</span> {esc(it["review_average"])}'
              if it.get("review_count") else '<span style="color:#9aa3af">―</span>')
        rc = f'{int(it["review_count"]):,}件' if it.get("review_count") else "―"
        sp = "込み" if it.get("postage_flag") == 0 else "別"
        rows.append(f'<tr><td class="num"><strong>{i}</strong></td>'
                    f'<td class="name"><a href="{esc(it["url"])}" target="_blank" '
                    f'rel="nofollow sponsored noopener">{esc(shorten(it["name"], 42))}</a></td>'
                    f'<td class="pr">{esc(yen(it["price"]))}</td>'
                    f'<td class="num">{rv}</td><td class="num">{rc}</td>'
                    f'<td class="num">{sp}</td></tr>')
    p.append('<div class="tablewrap"><table class="cmp"><thead><tr>'
             '<th>順位</th><th>商品名</th><th>価格</th><th>評価</th>'
             '<th>レビュー</th><th>送料</th></tr></thead><tbody>'
             + "".join(rows) + '</tbody></table></div>')
    p.append('<p class="note">※ 横にスクロールできます。順位は楽天市場のランキング／'
             'レビュー数にもとづく並び順です。</p>')

    # --- 商品詳細 ---
    p.append('<h2 class="sec" id="list">商品ごとの詳細</h2>')
    for i, it in enumerate(items, start=1):
        rank_no = it.get("rank") or i
        img = (f'<div class="thumb"><img src="{esc(it["image"])}" '
               f'alt="{esc(shorten(it["name"], 60))}" loading="lazy"></div>'
               if it.get("image") else '<div class="thumb"></div>')

        badges = "".join(f'<span class="badge {c}">{esc(t)}</span>'
                         for c, t in make_badges(it, st))
        badges = f'<div class="badges">{badges}</div>' if badges else ""

        specs = []
        if it.get("review_count"):
            specs.append('<li><span class="sk">レビュー</span><span class="sv">'
                         f'<span class="stars">{stars(it["review_average"])}</span> '
                         f'{esc(it["review_average"])}（{int(it["review_count"]):,}件）</span></li>')
        specs.append(f'<li><span class="sk">ショップ</span>'
                     f'<span class="sv">{esc(it["shop"])}</span></li>')
        specs.append('<li><span class="sk">送料</span><span class="sv">'
                     + ("商品価格に含まれています" if it.get("postage_flag") == 0
                        else "別途かかります（商品ページで確認）") + '</span></li>')
        if st["median_price"] and it.get("price"):
            diff = int(it["price"]) - st["median_price"]
            judge = ("この中では割安" if diff < 0 else
                     "この中では高め" if diff > 0 else "ちょうど中央値")
            specs.append(f'<li><span class="sk">価格の位置</span><span class="sv">'
                         f'{judge}（中央値との差 {"+" if diff>0 else ""}{diff:,}円）</span></li>')

        parts_html = f"""<div class="item">
  <div class="ihead"><span class="{rank_class(i)}">{esc(rank_no)}</span>
    <h3><a href="{esc(it["url"])}" target="_blank"
        rel="nofollow sponsored noopener">{esc(it["name"])}</a></h3></div>
  <div class="ibody">
    {img}
    <div class="info">
      {badges}
      <p class="price">{esc(yen(it["price"]))}<span class="tax">税込・楽天市場</span></p>
      <ul class="spec">{"".join(specs)}</ul>
      <p class="desc">{esc(shorten(it.get("caption", ""), 130))}</p>
      <a class="btn" href="{esc(it["url"])}" target="_blank"
         rel="nofollow sponsored noopener">楽天市場で価格を見る</a>
      <p class="btnnote">※ 楽天市場の商品ページが開きます（アフィリエイトリンク）</p>
    </div>
  </div>
</div>"""
        p.append(parts_html)

    # --- 見方・注意点 ---
    p.append('<h2 class="sec" id="howto">このページの見方・注意点</h2>')
    p.append(f"""<div class="prose">
<p>このページは、<strong>楽天ウェブサービスが提供する公式データ</strong>をもとに、
{esc(post["created_at"])}時点の情報を自動で集計して作成しています。
掲載順は楽天市場のランキング、またはレビュー数の多い順です。</p>
<p><strong>バッジの意味</strong>：「この中で最安」「レビュー評価が最高」「レビュー数が最多」は、
このページに掲載している{st["count"]}件の中での比較です。楽天市場全体での比較ではありません。
評価の比較は、判断の精度を上げるためレビューが3件以上ある商品のみを対象にしています。</p>
<p><strong>価格について</strong>：楽天市場の価格は頻繁に変動します。クーポンやポイント還元、
セール期間によって実質的な負担額も変わります。表示価格はあくまで取得時点のもので、
購入前に必ずリンク先でご確認ください。</p>
<p><strong>送料について</strong>：「送料込み」はデータ上の表記であり、
地域や配送方法によって異なる場合があります。</p>
</div>""")

    # --- 構造化データ（Googleに内容を正しく伝える）---
    ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": post["title"],
        "numberOfItems": len(items),
        "itemListElement": [
            {"@type": "ListItem", "position": i,
             "name": shorten(it["name"], 90), "url": it["url"]}
            for i, it in enumerate(items, start=1)
        ],
    }
    head = ('<script type="application/ld+json">'
            + json.dumps(ld, ensure_ascii=False) + '</script>')

    return page_shell(post["title"], "\n".join(p),
                      description=post["lead"], extra_head=head)


def render_index(posts):
    """トップページ（記事一覧）— 商品画像つきのカードを並べる"""
    if not posts:
        return page_shell(SITE_TITLE, "<p>まだ記事がありません。</p>", is_top=True)

    # カテゴリごとに色を変えて、ひと目で見分けられるようにする
    colors = {}
    palette = ["c-a", "c-b", "c-c", "c-d", "c-e"]
    for p in posts:
        colors.setdefault(p["category"], palette[len(colors) % len(palette)])

    cards = []
    for p in posts[:TOP_PAGE_ARTICLE_COUNT]:
        cls = colors.get(p["category"], "c-a")
        # 上位3商品の写真を並べて「ランキングらしさ」を出す
        shots = p.get("thumbs") or ([p["thumb"]] if p.get("thumb") else [])
        if shots:
            img = "".join(
                f'<span class="sh"><img src="{esc(u)}" alt="" loading="lazy">'
                f'<i>{n}</i></span>'
                for n, u in enumerate(shots, start=1))
        else:
            img = f'<span class="noimg">{esc(p["category"])}</span>' 

        price = ""
        if p.get("min_price"):
            price = f'<span class="pfrom">最安 <b>{esc(yen(p["min_price"]))}</b></span>'
        rating = ""
        if p.get("avg_rating"):
            rating = f'<span class="prate">平均 ★{esc(p["avg_rating"])}</span>'

        title = p.get("short_title") or p["title"]
        cards.append(f"""<li class="card">
  <a href="posts/{esc(p["filename"])}">
    <div class="cthumb {cls}">{img}</div>
    <div class="cbody">
      <span class="cbadge {cls}">{esc(p["category"])}</span>
      <h3>{esc(title)}</h3>
      <p class="cstat">{price}{rating}<span class="pn">{esc(p.get("item_count",""))}件</span></p>
      <p class="cdate">{esc(p["created_at"])}</p>
    </div>
  </a>
</li>""")

    body = (f'<h2 class="sec">最新のランキング</h2>'
            f'<ul class="cards">{"".join(cards)}</ul>')
    return page_shell(SITE_TITLE, body, is_top=True)


def render_about():
    """このサイトについて（運営方針・免責・データ出典）"""
    body = f"""<nav class="crumbs"><a href="index.html">ホーム</a> ／ このサイトについて</nav>
<h1 class="article-title">このサイトについて</h1>
<div class="prose">
<h2>サイトの目的</h2>
<p>{esc(SITE_TITLE)}は、楽天市場でいま実際によく売れている商品と、
そのジャンルの価格帯・評価の傾向を、データにもとづいて分かりやすくまとめるサイトです。
「なんとなく高い・安い」ではなく、最安値・中央値・平均評価といった数字で
判断できる形にすることを目指しています。</p>

<h2>データの出典と更新頻度</h2>
<p>掲載している商品情報（商品名・価格・レビュー評価・レビュー件数・送料区分・
ポイント倍率・画像）は、すべて楽天グループが提供する
<a href="https://webservice.rakuten.co.jp/" target="_blank" rel="noopener">楽天ウェブサービス</a>
の公式APIから取得しています。データは毎日自動で更新しています。</p>

<h2>掲載順の基準</h2>
<p>ランキング記事は楽天市場のリアルタイムランキングの順位、
キーワード別の記事はレビュー件数の多い順で掲載しています。
順位を金銭で操作することは一切ありません。</p>

<h2>広告について</h2>
<p>当サイトは楽天アフィリエイトを利用しており、
リンク経由で商品が購入された場合、運営者に紹介料が支払われます。
紹介料の有無や料率が、掲載順や商品の選定に影響することはありません。</p>

<h2>免責事項</h2>
<p>掲載情報の正確性には努めていますが、価格・在庫・送料・ポイント倍率は
記事作成時点のものであり、変動します。購入の判断は、必ずリンク先の
楽天市場の商品ページで最新情報をご確認のうえ、ご自身の責任で行ってください。
当サイトの情報にもとづく損害について、運営者は責任を負いかねます。</p>

<h2>お問い合わせ</h2>
<p>掲載内容に関するご指摘は、GitHub のリポジトリ経由でお願いします。</p>
</div>"""
    return page_shell(f"このサイトについて｜{SITE_TITLE}", body, is_top=True,
                      description=f"{SITE_TITLE}の運営方針・データ出典・免責事項について。")


# ---------------------------------------------------------------------
#  3. 記事を組み立てる
# ---------------------------------------------------------------------

def load_posts():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("! posts.json が読めなかったので、空の状態から始めます。")
        return []


def save_posts(posts):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def pick_keyword(theme, now):
    """日替わりでキーワードを選ぶ（同じ記事が続かないように）"""
    rotation = theme.get("keyword_rotation")
    if not rotation:
        return theme.get("keyword", "")
    return rotation[now.timetuple().tm_yday % len(rotation)]


def make_demo_items(n, label):
    """--demo のときに使う、にせ物の商品データ"""
    return [{
        "rank": i,
        "name": f"【サンプル】{label} おすすめ商品 その{i}（これはテスト表示です）",
        "price": 3980 + i * 1200,
        "url": f"https://example.com/item{i}",
        "image": "",
        "shop": f"サンプルショップ{i}",
        "review_count": 120 - i * 7,
        "review_average": round(4.8 - i * 0.1, 1),
        "caption": "これはデモ用のダミー説明文です。実際には楽天から取得した商品説明が入ります。",
        "point_rate": 1 if i % 2 else 5,
    } for i in range(1, n + 1)]


def build_one(theme, now, demo=False):
    """テーマ1つ分の記事を作る"""
    date_str = now.strftime("%Y年%m月%d日")
    date_slug = now.strftime("%Y%m%d")
    hits = int(theme.get("hits", 10))
    keyword = pick_keyword(theme, now)

    print(f"\n▼ 記事を作ります: {theme['category']}"
          + (f"（キーワード: {keyword}）" if keyword else ""))

    if demo:
        items = make_demo_items(hits, theme["category"])
    elif theme["kind"] == "ranking":
        items = fetch_ranking(genre_id=theme.get("genre_id", 0), hits=hits)
    else:
        items = fetch_search(keyword=keyword, genre_id=theme.get("genre_id", 0),
                             hits=hits, sort=theme.get("sort", "-reviewCount"))

    if not items:
        print("  ! 商品が1件も取れなかったので、この記事はスキップします。")
        return None, []

    n = len(items)
    # トップページのカードに出すための情報も一緒に持たせておく
    st = analyze(items)
    thumb = next((i["image"] for i in items if i.get("image")), "")
    thumbs = [i["image"] for i in items if i.get("image")][:3]

    post = {
        "filename": f"{date_slug}-{theme['slug']}.html",
        "slug": theme["slug"],
        "title": theme["title"].format(date=date_str, n=n, kw=keyword),
        # 一覧では日付を別枠で出すので、見出しから「【日付】」を外したものも用意
        "short_title": theme["title"].format(date=date_str, n=n, kw=keyword)
                       .replace(f"【{date_str}】", "").strip(),
        "lead": theme["lead"].format(date=date_str, n=n, kw=keyword),
        "category": theme["category"],
        "keyword": keyword,
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "item_count": n,
        "thumb": thumb,
        "thumbs": thumbs,
        "min_price": st["min_price"],
        "max_price": st["max_price"],
        "avg_rating": st["avg_rating"],
        "top_name": shorten(items[0]["name"], 40) if items else "",
    }

    # 先にHTMLを完成させてから書き込みます。書きながら作ると、
    # 途中で失敗したときに「中身が空のページ」が公開されてしまうためです。
    html_text = render_article(post, items)

    os.makedirs(POSTS_DIR, exist_ok=True)
    with open(os.path.join(POSTS_DIR, post["filename"]), "w", encoding="utf-8") as f:
        f.write(html_text)

    print(f"  ✓ {n}件の商品で記事を作りました → docs/posts/{post['filename']}")
    # 記事情報だけでなく商品データも返します（SNS用フィードで使うため）
    return post, items


# ---------------------------------------------------------------------
#  3.5 X（旧Twitter）への自動投稿
# ---------------------------------------------------------------------

POSTED_FILE = os.path.join(ROOT, "data", "posted.json")
X_POST_URL = "https://api.x.com/2/tweets"


def _pcts(text):
    """OAuthの決まりに従って文字をエンコードする（記号の扱いが独特）"""
    return urllib.parse.quote(str(text), safe="~-._")


def _oauth_header(method, url, keys):
    """
    Xに「これは本人からの投稿です」と証明するための署名を作る。

    OAuth 1.0a という古い仕組みですが、サーバーから自動投稿するには
    いまでもこれが一番確実です。外部ライブラリなしで実装しています。
    """
    import base64
    import hashlib
    import hmac
    import secrets

    params = {
        "oauth_consumer_key": keys["api_key"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": keys["access_token"],
        "oauth_version": "1.0",
    }
    # 署名のもとになる文字列を、決められた順番で組み立てる
    joined = "&".join(f"{_pcts(k)}={_pcts(params[k])}" for k in sorted(params))
    base = f"{method.upper()}&{_pcts(url)}&{_pcts(joined)}"
    signing_key = f'{_pcts(keys["api_secret"])}&{_pcts(keys["access_secret"])}'
    sig = base64.b64encode(
        hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()

    params["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pcts(k)}="{_pcts(params[k])}"'
                                for k in sorted(params))


def get_x_keys():
    """GitHubのSecretsからXの鍵を取り出す。1つでも欠けていたら None"""
    keys = {
        "api_key": os.environ.get("X_API_KEY", "").strip(),
        "api_secret": os.environ.get("X_API_SECRET", "").strip(),
        "access_token": os.environ.get("X_ACCESS_TOKEN", "").strip(),
        "access_secret": os.environ.get("X_ACCESS_SECRET", "").strip(),
    }
    return keys if all(keys.values()) else None


def post_to_x(text, keys):
    """Xに1件つぶやく。成功したら True"""
    body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        X_POST_URL, data=body, method="POST",
        headers={
            "Authorization": _oauth_header("POST", X_POST_URL, keys),
            "Content-Type": "application/json",
            "User-Agent": "rakuten-auto-blog/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            json.loads(res.read().decode("utf-8"))
        return True
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        print(f"  ✗ 投稿に失敗しました HTTP {e.code}: {detail}")
        if e.code == 403:
            print("     【原因】アプリの権限が「Read」のままの可能性があります。")
            print("     X Developer Portal で「Read and write」に変更し、")
            print("     そのあと Access Token を再発行してください。")
        elif e.code == 401:
            print("     【原因】4つの鍵のどれかが間違っています。")
        elif e.code == 429:
            print("     【原因】投稿しすぎです。しばらく待ってください。")
        return False
    except Exception as e:
        print(f"  ✗ 投稿に失敗しました: {type(e).__name__}: {e}")
        return False


def read_social_items():
    """social.xml から、投稿する文面とURLの組を読み取る"""
    path = os.path.join(DOCS_DIR, "social.xml")
    if not os.path.exists(path):
        return []
    xml = open(path, encoding="utf-8").read()
    out = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def grab(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            if not m:
                return ""
            return (m.group(1).replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&quot;", '"').replace("&amp;", "&").strip())
        out.append({"text": grab("title"), "url": grab("link"),
                    "guid": grab("guid")})
    return out


def run_post():
    """--post で呼ばれる。まだ投稿していない項目を順に投稿する"""
    print("=" * 56)
    print(" X（旧Twitter）への自動投稿")
    print("=" * 56)

    keys = get_x_keys()
    if not keys:
        print("\n! Xの鍵が設定されていないので、投稿はしません。")
        print("  GitHubのSecretsに X_API_KEY / X_API_SECRET /")
        print("  X_ACCESS_TOKEN / X_ACCESS_SECRET の4つを登録してください。")
        return 0

    items = read_social_items()
    if not items:
        print("\n! social.xml が見つからないか、中身が空です。")
        return 0

    # すでに投稿したものの記録を読む
    posted = []
    if os.path.exists(POSTED_FILE):
        try:
            posted = json.load(open(POSTED_FILE, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            posted = []
    done = set(posted)

    todo = [i for i in items if i["guid"] and i["guid"] not in done]
    if not todo:
        print("\n・新しく投稿するものはありません。")
        return 0

    print(f"\n未投稿 {len(todo)}件 / 今回は最大 {SNS_POSTS_PER_RUN}件 投稿します")
    sent = 0
    for item in todo[:SNS_POSTS_PER_RUN]:
        text = f'{item["text"]}\n{item["url"]}'
        print(f"\n▼ 投稿します:\n{text}\n")
        if post_to_x(text, keys):
            print("  ✓ 投稿しました")
            posted.append(item["guid"])
            sent += 1
            time.sleep(2)
        else:
            break

    # 記録が増えすぎないよう、新しい500件だけ残す
    posted = posted[-500:]
    os.makedirs(os.path.dirname(POSTED_FILE), exist_ok=True)
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(posted, f, ensure_ascii=False, indent=1)

    print(f"\n完了: {sent}件 投稿しました")
    return 0


# ---------------------------------------------------------------------
#  4. 接続テスト（--check）
# ---------------------------------------------------------------------

def mask(value):
    if not value:
        return "(未設定)"
    if len(value) <= 8:
        return value[0] + "*" * (len(value) - 1)
    return value[:4] + "*" * 8 + value[-4:]


def run_check():
    print("=" * 56)
    print(" 楽天API 接続テスト")
    print("=" * 56)

    print("\n[1] 設定の確認")
    ok = True
    for key, required in [("RAKUTEN_APP_ID", True), ("RAKUTEN_ACCESS_KEY", True),
                          ("RAKUTEN_AFFILIATE_ID", True), ("RAKUTEN_REFERER", False)]:
        value = os.environ.get(key, "").strip()
        mark = "OK " if value else ("NG " if required else "-- ")
        if required and not value:
            ok = False
        print(f"  {mark} {key} = {mask(value)}")

    if not ok:
        print("\n✗ 必須の設定が足りません。上の NG の項目を登録してください。")
        return 1

    print("\n[2] 総合ランキングAPIのテスト")
    try:
        items = fetch_ranking(genre_id=0, hits=3)
        print(f"  OK  {len(items)}件 取得できました")
        for it in items:
            print(f"      {it['rank']}位: {it['name'][:36]}… / {it['price']:,}円")
            if "hb.afl.rakuten.co.jp" in it["url"] or "a.r10.to" in it["url"]:
                print("            → アフィリエイトリンク OK")
            else:
                print("            → ⚠ アフィリエイトリンクになっていません。"
                      "RAKUTEN_AFFILIATE_ID を確認してください。")
    except Exception as e:
        print(f"  NG  {e}")
        return 1

    print("\n[3] 商品検索API（ハーレー用品）のテスト")
    try:
        items = fetch_search("ハーレー マフラー", genre_id=200305, hits=3)
        print(f"  OK  {len(items)}件 取得できました")
        for it in items:
            print(f"      {it['name'][:36]}… / {it['price']:,}円 / ★{it['review_average']}")
    except Exception as e:
        print(f"  NG  {e}")
        return 1

    print("\n" + "=" * 56)
    print(" すべてOKです。本番を実行できます。")
    print("=" * 56)
    return 0


def xesc(text):
    """RSS（XML）に入れても壊れない文字に変換する"""
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def rfc822(dt):
    """RSSが求める日付の書き方に直す"""
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return (f"{days[dt.weekday()]}, {dt.day:02d} {months[dt.month-1]} {dt.year} "
            f"{dt:%H:%M:%S} +0900")


def _rss(title, desc, link, items, now):
    """RSSの外枠を作る共通部分"""
    body = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>{xesc(title)}</title>
<link>{xesc(link)}</link>
<description>{xesc(desc)}</description>
<language>ja</language>
<lastBuildDate>{rfc822(now)}</lastBuildDate>
{body}
</channel></rss>
"""


def write_feeds(posts, built, now):
    """
    RSSを2種類つくる。

    ① feed.xml   … ふつうのブログ用RSS。記事だけが並びます。
    ② social.xml … SNSに自動投稿するための専用RSS。
                   IFTTTなどの無料ツールにこのURLを登録すると、
                   新しい項目が出るたびに自動でSNSに投稿できます。

    ★ タイトルの先頭に必ず「【PR】」を付けています。
      楽天アフィリエイトのステマ規制対応ページで
      「Xでは上部に、視認しやすく表記すること」と定められているためです。
      ここは絶対に外さないでください。
    """
    base = SITE_URL.rstrip("/") + "/"
    stamp = rfc822(now)

    # --- ① ふつうのブログRSS ---
    items = []
    for p in posts[:20]:
        url = f"{base}posts/{p['filename']}"
        items.append(f"""<item>
<title>{xesc(p['title'])}</title>
<link>{xesc(url)}</link>
<guid isPermaLink="true">{xesc(url)}</guid>
<pubDate>{stamp}</pubDate>
<description>{xesc(p.get('lead', ''))}</description>
</item>""")
    with open(os.path.join(DOCS_DIR, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(_rss(SITE_TITLE, SITE_DESCRIPTION, base, items, now))

    # --- ② SNS投稿用RSS（記事と商品を交互に並べる）---
    article_items, product_items = [], []
    date_tag = now.strftime("%Y%m%d")

    for post, prods in built:
        if not prods:
            continue
        st = analyze(prods)
        url = f"{base}posts/{post['filename']}"

        # 記事の紹介文（数字を入れて「読む理由」を作る）
        text = (f"【PR】{post['title']}\n"
                f"最安 {yen(st['min_price'])}／中央値 {yen(st['median_price'])}"
                + (f"／平均評価 {st['avg_rating']}" if st['avg_rating'] else "")
                + f"　#{post['category']} #楽天")
        article_items.append(f"""<item>
<title>{xesc(text)}</title>
<link>{xesc(url)}</link>
<guid isPermaLink="false">article-{xesc(post['filename'])}-{date_tag}</guid>
<pubDate>{stamp}</pubDate>
<description>{xesc(post.get('lead', ''))}</description>
</item>""")

        # 注目商品（評価がいちばん高いもの。無ければ最安）を1件
        pick = st["best_rated"] or st["cheapest"]
        if pick:
            ptext = (f"【PR】{shorten(pick['name'], 70)}\n"
                     f"{yen(pick['price'])}"
                     + (f"　★{pick['review_average']}（{int(pick['review_count']):,}件）"
                        if pick.get("review_count") else "")
                     + f"　#{post['category']} #楽天市場")
            key = re.sub(r"[^0-9a-zA-Z]", "", pick["url"])[-24:]
            product_items.append(f"""<item>
<title>{xesc(ptext)}</title>
<link>{xesc(pick['url'])}</link>
<guid isPermaLink="false">item-{xesc(key)}-{date_tag}</guid>
<pubDate>{stamp}</pubDate>
<description>{xesc(shorten(pick.get('caption', ''), 140))}</description>
</item>""")

    # 記事→商品→記事→商品… の順に交互に差し込む
    mixed = []
    for a, b in zip(article_items, product_items):
        mixed.append(a)
        mixed.append(b)
    mixed += article_items[len(product_items):]
    mixed += product_items[len(article_items):]

    # 同じ商品が複数の記事で1位になることがあります。
    # そのまま並べると同じ内容を2回つぶやいてしまうので、重複を取り除きます。
    seen, unique = set(), []
    for it in mixed:
        m = re.search(r"<guid[^>]*>(.*?)</guid>", it, re.S)
        key = m.group(1) if m else it
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    mixed = unique

    with open(os.path.join(DOCS_DIR, "social.xml"), "w", encoding="utf-8") as f:
        f.write(_rss(f"{SITE_TITLE}（SNS投稿用）",
                     "SNSへの自動投稿に使うフィードです。", base, mixed, now))
    print(f"  ✓ RSSを作りました（記事{len(items)}件 / SNS用{len(mixed)}件）")


def write_sitemap(posts, now):
    """
    sitemap.xml を作る。

    Googleに「このサイトにはこういうページがありますよ」と伝える地図です。
    新しい記事を早く見つけてもらうために出しておきます。
    """
    base = SITE_URL.rstrip("/") + "/"
    stamp = now.strftime("%Y-%m-%d")
    urls = [f"  <url><loc>{base}</loc><lastmod>{stamp}</lastmod>"
            f"<changefreq>daily</changefreq><priority>1.0</priority></url>",
            f"  <url><loc>{base}about.html</loc>"
            f"<changefreq>monthly</changefreq><priority>0.3</priority></url>"]
    for p in posts[:200]:
        urls.append(f"  <url><loc>{base}posts/{p['filename']}</loc>"
                    f"<lastmod>{p.get('created_at','')[:10]}</lastmod>"
                    f"<priority>0.8</priority></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>\n")
    with open(os.path.join(DOCS_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(xml)
    with open(os.path.join(DOCS_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n")


# ---------------------------------------------------------------------
#  5. ここから実行が始まります
# ---------------------------------------------------------------------

def main():
    if "--check" in sys.argv:
        sys.exit(run_check())

    if "--post" in sys.argv:
        sys.exit(run_post())

    demo = "--demo" in sys.argv
    now = datetime.datetime.now(JST)

    print("=" * 56)
    print(" 楽天アフィリエイト記事 自動生成")
    print(f" 実行日時: {now.strftime('%Y-%m-%d %H:%M')} (日本時間)")
    if demo:
        print(" モード: デモ（ダミーデータ・楽天APIは呼びません）")
    print("=" * 56)

    posts = load_posts()

    # ★リンク切れ防止★
    # 記事のHTMLファイルを手で削除した場合、一覧だけが残ると
    # クリックしてもエラー（404）になってしまいます。
    # 毎回「ファイルが実在するか」を確認し、無いものは一覧から自動で外します。
    before = len(posts)
    def alive(p):
        """記事ファイルが実在し、かつ中身が空でないか"""
        f = os.path.join(POSTS_DIR, p.get("filename", ""))
        return os.path.exists(f) and os.path.getsize(f) > 500

    posts = [p for p in posts if alive(p)]
    removed = before - len(posts)
    if removed:
        print(f"  ※ ファイルが無くなっていた記事 {removed}件 を一覧から外しました。")

    known = {p["filename"] for p in posts}
    built = []          # 今回作った (記事, 商品リスト) の組
    created = 0
    failed = 0

    for theme in THEMES:
        try:
            post, items = build_one(theme, now, demo=demo)
        except Exception as e:
            failed += 1
            print(f"  ✗ エラーが起きました: {e}")
            continue

        if not post:
            continue
        built.append((post, items))

        if post["filename"] in known:
            posts = [p for p in posts if p["filename"] != post["filename"]]
        posts.insert(0, post)
        known.add(post["filename"])
        created += 1

    # トップページとCSSを作り直す
    os.makedirs(POSTS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(posts))
    with open(os.path.join(DOCS_DIR, "about.html"), "w", encoding="utf-8") as f:
        f.write(render_about())
    write_sitemap(posts, now)
    write_feeds(posts, built, now)
    open(os.path.join(DOCS_DIR, ".nojekyll"), "w").close()

    save_posts(posts)

    print("\n" + "=" * 56)
    print(f" 完了: 新しい記事 {created}本 / 失敗 {failed}件 / 記事総数 {len(posts)}本")
    print("=" * 56)

    if created == 0:
        print("\n! 記事が1本も作れませんでした。上のエラー内容を確認してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
