# -*- coding: utf-8 -*-
"""
=========================================================
 メインプログラム（これを実行すると記事ができます）
=========================================================
使い方:

  python scripts/generate.py           … 本番（楽天APIから取得）
  python scripts/generate.py --demo    … お試し（ダミー商品で見た目だけ確認）

やっていること:
  1. 楽天APIから商品を取ってくる
  2. HTMLの記事ページを docs/posts/ に書き出す
  3. 記事の一覧を data/posts.json に記録する
  4. トップページ docs/index.html を作り直す
"""

import datetime
import json
import os
import sys

import config
import templates
import rakuten_api

# --- フォルダの場所を決める -----------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(ROOT, "docs")
POSTS_DIR = os.path.join(DOCS_DIR, "posts")
DATA_FILE = os.path.join(ROOT, "data", "posts.json")

# 日本時間（GitHub Actionsのサーバーは世界標準時なのでズレを直す）
JST = datetime.timezone(datetime.timedelta(hours=9))


def today_jst():
    return datetime.datetime.now(JST)


def load_posts():
    """これまでに作った記事の一覧を読み込む"""
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
    # 1月1日からの通算日数で割った余りを使う → 毎日ちがうキーワードになる
    index = now.timetuple().tm_yday % len(rotation)
    return rotation[index]


def make_demo_items(n, label):
    """--demo のときに使う、にせものの商品データ"""
    items = []
    for i in range(1, n + 1):
        items.append({
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
            "postage_flag": 0,
        })
    return items


def build_one(theme, now, demo=False):
    """テーマ1つ分の記事を作る。成功したら記事情報を返す"""
    date_str = now.strftime("%Y年%m月%d日")
    date_slug = now.strftime("%Y%m%d")
    hits = int(theme.get("hits", 10))
    keyword = pick_keyword(theme, now)

    print(f"\n▼ 記事を作ります: {theme['category']}"
          + (f"（キーワード: {keyword}）" if keyword else ""))

    # --- 商品を取ってくる ---
    if demo:
        items = make_demo_items(hits, theme["category"])
    elif theme["kind"] == "ranking":
        items = rakuten_api.fetch_ranking(genre_id=theme.get("genre_id", 0), hits=hits)
    else:
        items = rakuten_api.fetch_search(
            keyword=keyword,
            genre_id=theme.get("genre_id", 0),
            hits=hits,
            sort=theme.get("sort", "-reviewCount"),
        )

    if not items:
        print("  ! 商品が1件も取れなかったので、この記事はスキップします。")
        return None

    n = len(items)
    title = theme["title"].format(date=date_str, n=n, kw=keyword)
    lead = theme["lead"].format(date=date_str, n=n, kw=keyword)
    filename = f"{date_slug}-{theme['slug']}.html"

    post = {
        "filename": filename,
        "slug": theme["slug"],
        "title": title,
        "lead": lead,
        "category": theme["category"],
        "keyword": keyword,
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "item_count": n,
    }

    os.makedirs(POSTS_DIR, exist_ok=True)
    with open(os.path.join(POSTS_DIR, filename), "w", encoding="utf-8") as f:
        f.write(templates.render_article(post, items))

    print(f"  ✓ {n}件の商品で記事を作りました → docs/posts/{filename}")
    return post


def main():
    demo = "--demo" in sys.argv
    now = today_jst()

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

    for theme in config.THEMES:
        try:
            post = build_one(theme, now, demo=demo)
        except Exception as e:
            failed += 1
            print(f"  ✗ エラーが起きました: {e}")
            continue

        if not post:
            continue

        # 同じファイル名の記事があれば、新しいもので置き換える
        if post["filename"] in known:
            posts = [p for p in posts if p["filename"] != post["filename"]]
        posts.insert(0, post)
        known.add(post["filename"])
        created += 1

    # --- トップページとCSSを作り直す ---
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(templates.CSS)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(templates.render_index(posts))
    # GitHub Pages が余計な変換をしないようにするおまじない
    open(os.path.join(DOCS_DIR, ".nojekyll"), "w").close()

    save_posts(posts)

    print("\n" + "=" * 56)
    print(f" 完了: 新しい記事 {created}本 / 失敗 {failed}件 / 記事総数 {len(posts)}本")
    print("=" * 56)

    # 1本も作れなかったら、GitHub Actions を「失敗」にして気づけるようにする
    if created == 0:
        print("\n! 記事が1本も作れませんでした。上のエラー内容を確認してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
