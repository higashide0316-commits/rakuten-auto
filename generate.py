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

 ★ 設定を変えたいときは、下の「設定エリア」だけ書き換えてください。
   それより下は、意味が分からなければ触らなくて大丈夫です。
"""

import datetime
import html
import json
import os
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
SITE_TITLE = "楽天うれすじ速報"
SITE_DESCRIPTION = "楽天市場の売れ筋ランキングと、ゴルフ用品・ハーレー用品のおすすめを毎日自動でお届けします。"

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

        result.append({
            "rank": item.get("rank"),
            "name": (item.get("itemName") or "").strip(),
            "price": item.get("itemPrice") or 0,
            "url": link,
            "image": image_url,
            "shop": (item.get("shopName") or "").strip(),
            "review_count": item.get("reviewCount") or 0,
            "review_average": item.get("reviewAverage") or 0,
            "caption": (item.get("itemCaption") or "").strip(),
            "point_rate": item.get("pointRate") or 1,
        })
    return result


def fetch_ranking(genre_id=0, hits=10):
    """売れ筋ランキングを取ってくる"""
    params = {"period": "realtime"}
    if genre_id:
        params["genreId"] = genre_id
    data = call_api(RANKING_URL, params)
    time.sleep(REQUEST_INTERVAL_SEC)
    return normalize(data.get("Items", []))[:hits]


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
  --bg:#0f1115; --card:#171a21; --line:#252a34;
  --text:#e8eaed; --muted:#9aa3af; --accent:#e8384f; --accent2:#ffb020;
}
@media (prefers-color-scheme: light){
  :root{ --bg:#f7f8fa; --card:#ffffff; --line:#e4e7ec;
         --text:#1a1d23; --muted:#61697a; }
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",
              "Yu Gothic UI",Meiryo,sans-serif;
  line-height:1.75; -webkit-text-size-adjust:100%;
}
.wrap{max-width:760px; margin:0 auto; padding:0 16px 64px;}
header.site{
  border-bottom:1px solid var(--line); background:var(--card);
  padding:20px 16px; margin-bottom:24px;
}
header.site .inner{max-width:760px; margin:0 auto;}
header.site h1{margin:0; font-size:20px; letter-spacing:.02em;}
header.site h1 a{color:var(--text); text-decoration:none;}
header.site p{margin:6px 0 0; color:var(--muted); font-size:13px;}
.pr{
  display:inline-block; margin:12px 0 0; padding:4px 10px; border-radius:999px;
  background:rgba(232,56,79,.12); color:var(--accent);
  font-size:11px; font-weight:700; letter-spacing:.04em;
}
h2.article-title{font-size:22px; line-height:1.5; margin:8px 0 4px;}
.meta{color:var(--muted); font-size:12px; margin-bottom:20px;}
.badge{
  display:inline-block; padding:2px 8px; border-radius:4px;
  background:var(--line); color:var(--muted); font-size:11px; margin-right:8px;
}
.lead{
  background:var(--card); border:1px solid var(--line); border-left:3px solid var(--accent);
  border-radius:8px; padding:14px 16px; font-size:14px; margin-bottom:28px;
}
.item{
  background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:16px; margin-bottom:18px; display:flex; gap:14px;
}
@media (max-width:520px){ .item{flex-direction:column;} }
.item .thumb{
  flex:0 0 132px; width:132px; height:132px; border-radius:8px; overflow:hidden;
  background:var(--line); display:flex; align-items:center; justify-content:center;
}
@media (max-width:520px){ .item .thumb{width:100%; height:200px; flex:none;} }
.item .thumb img{width:100%; height:100%; object-fit:contain;}
.item .body{flex:1 1 auto; min-width:0;}
.rank{
  display:inline-flex; align-items:center; justify-content:center;
  min-width:26px; height:26px; padding:0 7px; border-radius:6px;
  background:var(--accent); color:#fff; font-weight:800; font-size:13px;
  margin-right:8px;
}
.rank.gold{background:linear-gradient(135deg,#f6c94a,#d99a12); color:#3a2b00;}
.rank.silver{background:linear-gradient(135deg,#d7dbe2,#a6adb8); color:#2a2f38;}
.rank.bronze{background:linear-gradient(135deg,#d9a273,#a8703c); color:#2f1c08;}
.item h3{font-size:15px; margin:0 0 8px; line-height:1.5; font-weight:600;}
.item h3 a{color:var(--text); text-decoration:none;}
.item h3 a:hover{color:var(--accent);}
.price{font-size:19px; font-weight:800; color:var(--accent); margin:0 0 6px;}
.price small{font-size:12px; font-weight:600; color:var(--muted); margin-left:4px;}
.sub{font-size:12px; color:var(--muted); margin:0 0 4px;}
.stars{color:var(--accent2); letter-spacing:1px;}
.desc{font-size:13px; color:var(--muted); margin:8px 0 12px;}
.btn{
  display:inline-block; padding:10px 18px; border-radius:8px;
  background:var(--accent); color:#fff !important; text-decoration:none;
  font-weight:700; font-size:14px;
}
.btn:hover{opacity:.88;}
ul.posts{list-style:none; padding:0; margin:0;}
ul.posts li{
  background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:14px 16px; margin-bottom:12px;
}
ul.posts a{color:var(--text); text-decoration:none; font-weight:600; font-size:15px;}
ul.posts a:hover{color:var(--accent);}
footer.site{
  margin-top:48px; padding-top:20px; border-top:1px solid var(--line);
  color:var(--muted); font-size:12px;
}
.back{display:inline-block; margin-bottom:16px; color:var(--muted);
      font-size:13px; text-decoration:none;}
.back:hover{color:var(--accent);}
"""


def esc(text):
    return html.escape(str(text if text is not None else ""))


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
    return "★" * full + ("☆" if half else "") + "・" * (5 - full - half)


def rank_class(i):
    return {1: "rank gold", 2: "rank silver", 3: "rank bronze"}.get(i, "rank")


def page_shell(title, body_html, is_top=False):
    """全ページ共通の外枠"""
    prefix = "" if is_top else "../"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(SITE_DESCRIPTION)}">
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="site">
  <div class="inner">
    <h1><a href="{prefix}index.html">{esc(SITE_TITLE)}</a></h1>
    <p>{esc(SITE_DESCRIPTION)}</p>
    <span class="pr">PR</span>
  </div>
</header>
<div class="wrap">
{body_html}
<footer class="site">
  <p>{esc(PR_NOTICE)}</p>
  <p>掲載している価格・ポイント・在庫状況は記事の作成時点のものです。
     最新の情報は必ず楽天市場の商品ページでご確認ください。</p>
  <p>&copy; {esc(SITE_TITLE)}</p>
</footer>
</div>
</body>
</html>
"""


def render_article(post, items):
    """記事1本分のHTMLを作る"""
    parts = ['<a class="back" href="../index.html">&larr; 記事一覧にもどる</a>',
             f'<h2 class="article-title">{esc(post["title"])}</h2>',
             f'<p class="meta"><span class="badge">{esc(post["category"])}</span>'
             f'{esc(post["created_at"])} 更新</p>',
             f'<div class="lead">{esc(post["lead"])}</div>']

    for i, it in enumerate(items, start=1):
        rank_no = it.get("rank") or i
        img = (f'<div class="thumb"><img src="{esc(it["image"])}" '
               f'alt="{esc(it["name"])[:60]}" loading="lazy"></div>'
               if it.get("image") else '<div class="thumb"></div>')

        price = f'{int(it["price"]):,}円' if it.get("price") else "価格は商品ページで確認"
        point = ""
        try:
            if int(it.get("point_rate") or 1) > 1:
                point = f'<small>ポイント{int(it["point_rate"])}倍</small>'
        except (TypeError, ValueError):
            pass

        review = ""
        if it.get("review_count"):
            review = (f'<p class="sub"><span class="stars">{stars(it["review_average"])}</span> '
                      f'{esc(it["review_average"])}（{int(it["review_count"]):,}件のレビュー）</p>')

        desc = it.get("caption", "")
        if len(desc) > 110:
            desc = desc[:110] + "…"

        parts.append(f"""<div class="item">
  {img}
  <div class="body">
    <h3><span class="{rank_class(i)}">{esc(rank_no)}</span>
        <a href="{esc(it["url"])}" target="_blank" rel="nofollow sponsored noopener">{esc(it["name"])}</a></h3>
    <p class="price">{esc(price)}{point}</p>
    <p class="sub">ショップ: {esc(it["shop"])}</p>
    {review}
    <p class="desc">{esc(desc)}</p>
    <a class="btn" href="{esc(it["url"])}" target="_blank" rel="nofollow sponsored noopener">楽天市場で見る</a>
  </div>
</div>""")

    return page_shell(post["title"], "\n".join(parts))


def render_index(posts):
    """トップページ（記事一覧）のHTMLを作る"""
    if not posts:
        return page_shell(SITE_TITLE, "<p>まだ記事がありません。</p>", is_top=True)

    lis = []
    for p in posts[:TOP_PAGE_ARTICLE_COUNT]:
        lis.append(
            f'<li><a href="posts/{esc(p["filename"])}">{esc(p["title"])}</a>'
            f'<div class="meta" style="margin:6px 0 0">'
            f'<span class="badge">{esc(p["category"])}</span>{esc(p["created_at"])}</div></li>'
        )
    body = ('<h2 class="article-title">最新の記事</h2>\n<ul class="posts">\n'
            + "\n".join(lis) + "\n</ul>")
    return page_shell(SITE_TITLE, body, is_top=True)


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
        "url": "https://example.com/",
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
        return None

    n = len(items)
    post = {
        "filename": f"{date_slug}-{theme['slug']}.html",
        "slug": theme["slug"],
        "title": theme["title"].format(date=date_str, n=n, kw=keyword),
        "lead": theme["lead"].format(date=date_str, n=n, kw=keyword),
        "category": theme["category"],
        "keyword": keyword,
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "item_count": n,
    }

    os.makedirs(POSTS_DIR, exist_ok=True)
    with open(os.path.join(POSTS_DIR, post["filename"]), "w", encoding="utf-8") as f:
        f.write(render_article(post, items))

    print(f"  ✓ {n}件の商品で記事を作りました → docs/posts/{post['filename']}")
    return post


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


# ---------------------------------------------------------------------
#  5. ここから実行が始まります
# ---------------------------------------------------------------------

def main():
    if "--check" in sys.argv:
        sys.exit(run_check())

    demo = "--demo" in sys.argv
    now = datetime.datetime.now(JST)

    print("=" * 56)
    print(" 楽天アフィリエイト記事 自動生成")
    print(f" 実行日時: {now.strftime('%Y-%m-%d %H:%M')} (日本時間)")
    if demo:
        print(" モード: デモ（ダミーデータ・楽天APIは呼びません）")
    print("=" * 56)

    posts = load_posts()
    known = {p["filename"] for p in posts}
    created = 0
    failed = 0

    for theme in THEMES:
        try:
            post = build_one(theme, now, demo=demo)
        except Exception as e:
            failed += 1
            print(f"  ✗ エラーが起きました: {e}")
            continue

        if not post:
            continue

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
