# -*- coding: utf-8 -*-
"""
=========================================================
 HTMLの見た目を作る担当
=========================================================
記事ページとトップページのHTMLを組み立てます。
デザインを変えたいときは、このファイルの CSS を触ってください。
"""

import html

import config


# ★ 景品表示法（ステマ規制）対応
#   アフィリエイトリンクを貼るサイトは「広告であること」の明示が必須です。
#   この表記は絶対に消さないでください。
PR_NOTICE = "本ページはプロモーションを含みます（楽天アフィリエイト）"


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
h2.article-title{
  font-size:22px; line-height:1.5; margin:8px 0 4px;
}
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
.back{display:inline-block; margin-bottom:16px; color:var(--muted); font-size:13px; text-decoration:none;}
.back:hover{color:var(--accent);}
"""


def _esc(text):
    """HTMLに埋め込んでも安全な文字に変換する"""
    return html.escape(str(text if text is not None else ""))


def _stars(average):
    """4.3 → ★★★★☆ のような文字列にする"""
    try:
        a = float(average)
    except (TypeError, ValueError):
        return ""
    if a <= 0:
        return ""
    full = int(a)
    half = 1 if a - full >= 0.5 else 0
    return "★" * full + ("☆" if half else "") + "・" * (5 - full - half)


def _rank_class(i):
    return {1: "rank gold", 2: "rank silver", 3: "rank bronze"}.get(i, "rank")


def _page_shell(title, body_html, is_top=False):
    """全ページ共通の外枠（<html>〜</html>）"""
    home = "index.html" if not is_top else "#"
    prefix = "" if is_top else "../"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(config.SITE_DESCRIPTION)}">
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="site">
  <div class="inner">
    <h1><a href="{prefix}index.html">{_esc(config.SITE_TITLE)}</a></h1>
    <p>{_esc(config.SITE_DESCRIPTION)}</p>
    <span class="pr">PR</span>
  </div>
</header>
<div class="wrap">
{body_html}
<footer class="site">
  <p>{_esc(PR_NOTICE)}</p>
  <p>掲載している価格・ポイント・在庫状況は記事の作成時点のものです。
     最新の情報は必ず楽天市場の商品ページでご確認ください。</p>
  <p>&copy; {_esc(config.SITE_TITLE)}</p>
</footer>
</div>
</body>
</html>
"""


def render_article(post, items):
    """記事1本分のHTMLを作る"""
    parts = []
    parts.append('<a class="back" href="../index.html">&larr; 記事一覧にもどる</a>')
    parts.append(f'<h2 class="article-title">{_esc(post["title"])}</h2>')
    parts.append(
        f'<p class="meta"><span class="badge">{_esc(post["category"])}</span>'
        f'{_esc(post["created_at"])} 更新</p>'
    )
    parts.append(f'<div class="lead">{_esc(post["lead"])}</div>')

    for i, it in enumerate(items, start=1):
        rank_no = it.get("rank") or i
        img = (
            f'<div class="thumb"><img src="{_esc(it["image"])}" alt="{_esc(it["name"])[:60]}" loading="lazy"></div>'
            if it.get("image") else '<div class="thumb"></div>'
        )

        price = f'{int(it["price"]):,}円' if it.get("price") else "価格は商品ページで確認"
        point = ""
        try:
            if int(it.get("point_rate") or 1) > 1:
                point = f'<small>ポイント{int(it["point_rate"])}倍</small>'
        except (TypeError, ValueError):
            pass

        review = ""
        if it.get("review_count"):
            review = (
                f'<p class="sub"><span class="stars">{_stars(it["review_average"])}</span> '
                f'{_esc(it["review_average"])}（{int(it["review_count"]):,}件のレビュー）</p>'
            )

        desc = it.get("caption", "")
        if len(desc) > 110:
            desc = desc[:110] + "…"

        parts.append(f"""<div class="item">
  {img}
  <div class="body">
    <h3><span class="{_rank_class(i)}">{_esc(rank_no)}</span>
        <a href="{_esc(it["url"])}" target="_blank" rel="nofollow sponsored noopener">{_esc(it["name"])}</a></h3>
    <p class="price">{_esc(price)}{point}</p>
    <p class="sub">ショップ: {_esc(it["shop"])}</p>
    {review}
    <p class="desc">{_esc(desc)}</p>
    <a class="btn" href="{_esc(it["url"])}" target="_blank" rel="nofollow sponsored noopener">楽天市場で見る</a>
  </div>
</div>""")

    return _page_shell(post["title"], "\n".join(parts))


def render_index(posts):
    """トップページ（記事一覧）のHTMLを作る"""
    if not posts:
        body = "<p>まだ記事がありません。</p>"
        return _page_shell(config.SITE_TITLE, body, is_top=True)

    lis = []
    for p in posts[: config.TOP_PAGE_ARTICLE_COUNT]:
        lis.append(
            f'<li><a href="posts/{_esc(p["filename"])}">{_esc(p["title"])}</a>'
            f'<div class="meta" style="margin:6px 0 0">'
            f'<span class="badge">{_esc(p["category"])}</span>{_esc(p["created_at"])}</div></li>'
        )
    body = f'<h2 class="article-title">最新の記事</h2>\n<ul class="posts">\n' + "\n".join(lis) + "\n</ul>"
    return _page_shell(config.SITE_TITLE, body, is_top=True)
