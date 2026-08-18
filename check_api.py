# -*- coding: utf-8 -*-
"""
=========================================================
 楽天APIの接続テスト（困ったときはこれを実行）
=========================================================
使い方（自分のパソコンで試す場合）:

  Windowsのコマンドプロンプトで
    set RAKUTEN_APP_ID=あなたのアプリID
    set RAKUTEN_ACCESS_KEY=あなたのアクセスキー
    set RAKUTEN_AFFILIATE_ID=あなたのアフィリエイトID
    set RAKUTEN_REFERER=https://あなたのユーザー名.github.io/
    python scripts/check_api.py

「OK」がぜんぶ出れば、本番も動きます。
"""

import os
import sys

import rakuten_api


def mask(value):
    """秘密の値を、画面に出しても大丈夫な形に隠す"""
    if not value:
        return "(未設定)"
    if len(value) <= 8:
        return value[0] + "*" * (len(value) - 1)
    return value[:4] + "*" * 8 + value[-4:]


def main():
    print("=" * 56)
    print(" 楽天API 接続テスト")
    print("=" * 56)

    # --- 1. 設定が入っているか確認 ---
    print("\n[1] 設定の確認")
    ok = True
    for key, required in [
        ("RAKUTEN_APP_ID", True),
        ("RAKUTEN_ACCESS_KEY", True),
        ("RAKUTEN_AFFILIATE_ID", True),
        ("RAKUTEN_REFERER", False),
    ]:
        value = os.environ.get(key, "").strip()
        mark = "OK " if value else ("NG " if required else "-- ")
        if required and not value:
            ok = False
        print(f"  {mark} {key} = {mask(value)}")

    if not ok:
        print("\n✗ 必須の設定が足りません。上の NG の項目を設定してください。")
        sys.exit(1)

    # --- 2. 総合ランキングを取ってみる ---
    print("\n[2] 総合ランキングAPIのテスト")
    try:
        items = rakuten_api.fetch_ranking(genre_id=0, hits=3)
        print(f"  OK  {len(items)}件 取得できました")
        for it in items:
            print(f"      {it['rank']}位: {it['name'][:40]}… / {it['price']:,}円")
            # アフィリエイトリンクになっているかチェック
            if "hb.afl.rakuten.co.jp" in it["url"] or "a.r10.to" in it["url"]:
                print("            → アフィリエイトリンク OK")
            else:
                print("            → ⚠ アフィリエイトリンクになっていません。"
                      "RAKUTEN_AFFILIATE_ID を確認してください。")
    except Exception as e:
        print(f"  NG  {e}")
        sys.exit(1)

    # --- 3. 商品検索APIを取ってみる ---
    print("\n[3] 商品検索API（ハーレー用品）のテスト")
    try:
        items = rakuten_api.fetch_search("ハーレー マフラー", genre_id=200305, hits=3)
        print(f"  OK  {len(items)}件 取得できました")
        for it in items:
            print(f"      {it['name'][:40]}… / {it['price']:,}円 / ★{it['review_average']}")
    except Exception as e:
        print(f"  NG  {e}")
        sys.exit(1)

    print("\n" + "=" * 56)
    print(" すべてOKです。本番を実行できます。")
    print("=" * 56)


if __name__ == "__main__":
    main()
