# -*- coding: utf-8 -*-
"""
=========================================================
 楽天ウェブサービス API 呼び出し担当
=========================================================
このファイルは「楽天のサーバーに商品情報をもらいに行く」係です。

2026年5月の新仕様に対応しています。
  ・エンドポイント（住所）が openapi.rakuten.co.jp に変わった
  ・applicationId に加えて accessKey が必須になった
  ・アプリ登録時に「許可ウェブサイト」を登録しておく必要がある
"""

import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

import config

# --- 楽天APIの住所（2026年新仕様） ---------------------------------
RANKING_URL = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"


class RakutenApiError(Exception):
    """楽天APIでエラーが起きたときに使う、専用のエラーの型"""
    pass


def _get_credentials():
    """
    GitHub の Secrets（環境変数）から、秘密の3つの値を取り出す。

      RAKUTEN_APP_ID      … アプリID
      RAKUTEN_ACCESS_KEY  … アクセスキー
      RAKUTEN_AFFILIATE_ID… アフィリエイトID
    """
    app_id = os.environ.get("RAKUTEN_APP_ID", "").strip()
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY", "").strip()
    affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID", "").strip()

    if not app_id:
        raise RakutenApiError(
            "RAKUTEN_APP_ID が設定されていません。\n"
            "GitHub の Settings > Secrets and variables > Actions に登録してください。"
        )
    if not access_key:
        raise RakutenApiError(
            "RAKUTEN_ACCESS_KEY が設定されていません。\n"
            "2026年5月の新仕様から必須になりました。楽天ウェブサービスの管理画面で確認できます。"
        )
    if not affiliate_id:
        raise RakutenApiError(
            "RAKUTEN_AFFILIATE_ID が設定されていません。\n"
            "これが無いと報酬が発生しないので、必ず設定してください。"
        )
    return app_id, access_key, affiliate_id


def _build_headers(access_key):
    """
    楽天に送るリクエストの「ヘッダー（送り状）」を作る。

    Referer / Origin は、アプリ登録時の「許可ウェブサイト」と
    一致させる必要があります（IPアドレスが毎回変わる
    GitHub Actions から呼ぶ場合の必須テクニックです）。
    """
    referer = os.environ.get("RAKUTEN_REFERER", "").strip()

    headers = {
        "User-Agent": "rakuten-auto-blog/1.0",
        "Accept": "application/json",
        "accessKey": access_key,
    }
    if referer:
        headers["Referer"] = referer
        # Origin は「https://ドメイン名」までの形にする
        parsed = urllib.parse.urlparse(referer)
        if parsed.scheme and parsed.netloc:
            headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    return headers


def _request(url, params, headers):
    """実際に1回だけ通信する、いちばん内側の処理"""
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    req = urllib.request.Request(full_url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as res:
        body = res.read().decode("utf-8")
    return json.loads(body)


def _call_api(url, params):
    """
    楽天APIを呼ぶ（失敗したらリトライする）。

    accessKey はヘッダーでもクエリでも渡せる仕様ですが、
    環境によってどちらかしか通らないことがあるため、
    ヘッダーで失敗したらクエリでもう一度試します。
    """
    app_id, access_key, affiliate_id = _get_credentials()

    base_params = dict(params)
    base_params["applicationId"] = app_id
    base_params["affiliateId"] = affiliate_id
    base_params["format"] = "json"
    base_params["formatVersion"] = 2

    headers = _build_headers(access_key)

    last_error = None
    for attempt in range(1, config.MAX_RETRY + 1):
        # 1回目はヘッダー方式、2回目以降はクエリ方式も試す
        use_query_key = attempt > 1
        p = dict(base_params)
        if use_query_key:
            p["accessKey"] = access_key

        try:
            return _request(url, p, headers)

        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            last_error = f"HTTP {e.code}: {detail}"

            # よくあるエラーは、原因が分かるようにヒントを足す
            if e.code == 403 and "CLIENT_IP_NOT_ALLOWED" in detail:
                last_error += (
                    "\n\n【原因のヒント】アプリを「API/バックエンドサービス」型で登録すると、"
                    "登録したIPアドレスからしかアクセスできません。"
                    "GitHub ActionsはIPが毎回変わるため弾かれます。"
                    "楽天ウェブサービスの管理画面でアプリのタイプを"
                    "「ウェブフロントエンド」系に変更し、"
                    "「許可ウェブサイト」にGitHub Pagesのドメインを登録したうえで、"
                    "GitHubのSecretsに RAKUTEN_REFERER を設定してください。"
                )
            elif e.code in (400, 401):
                last_error += (
                    "\n\n【原因のヒント】アプリIDかアクセスキーが違う可能性があります。"
                    "2026年5月以降、両方が必須になりUUID形式に変わっています。"
                    "古いアプリIDは使えないので、再発行してください。"
                )
            elif e.code == 429:
                last_error += "\n\n【原因のヒント】アクセスしすぎです。config.py の REQUEST_INTERVAL_SEC を増やしてください。"

        except Exception as e:  # 通信エラーなど
            last_error = f"{type(e).__name__}: {e}"

        if attempt < config.MAX_RETRY:
            wait = config.REQUEST_INTERVAL_SEC * attempt
            print(f"  ! 失敗しました（{attempt}回目）。{wait:.1f}秒待って再試行します。")
            time.sleep(wait)

    raise RakutenApiError(f"楽天APIの呼び出しに{config.MAX_RETRY}回失敗しました。\n{last_error}")


# =========================================================
#  外から使う関数は、この2つだけ
# =========================================================

def fetch_ranking(genre_id=0, hits=10):
    """
    ランキングAPIで「売れ筋ランキング」を取得する。

    genre_id=0 なら総合ランキング。
    """
    params = {"period": "realtime"}
    if genre_id:
        params["genreId"] = genre_id

    data = _call_api(RANKING_URL, params)
    items = data.get("Items", [])
    time.sleep(config.REQUEST_INTERVAL_SEC)
    return _normalize(items)[:hits]


def fetch_search(keyword, genre_id=0, hits=10, sort="-reviewCount"):
    """
    商品検索APIでキーワード検索する。

    ランキングAPIでは細かい絞り込みができないので、
    「ハーレー用品」のような特定テーマはこちらを使います。
    """
    params = {
        "keyword": keyword,
        "hits": min(int(hits), 30),
        "sort": sort,
        "imageFlag": config.IMAGE_FLAG,
        "availability": config.AVAILABILITY,
    }
    if genre_id:
        params["genreId"] = genre_id

    data = _call_api(SEARCH_URL, params)
    items = data.get("Items", [])
    time.sleep(config.REQUEST_INTERVAL_SEC)
    return _normalize(items)[:hits]


def _normalize(raw_items):
    """
    楽天から返ってきたデータを、記事作成で使いやすい形に整える。

    formatVersion=2 だと商品が素直な辞書で返ってくるので、
    必要な項目だけ取り出して名前をそろえます。
    """
    result = []
    for raw in raw_items:
        # formatVersion=1 の場合の入れ子にも一応対応しておく
        item = raw.get("Item", raw) if isinstance(raw, dict) else {}

        image_urls = item.get("mediumImageUrls") or item.get("smallImageUrls") or []
        image_url = ""
        if image_urls:
            first = image_urls[0]
            image_url = first.get("imageUrl", "") if isinstance(first, dict) else str(first)
            # 末尾の ?_ex=128x128 を大きめのサイズに差し替える
            image_url = image_url.split("?")[0] + "?_ex=400x400"

        link = item.get("affiliateUrl") or item.get("itemUrl") or ""
        if not link:
            continue  # リンクが無い商品は載せない

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
            "postage_flag": item.get("postageFlag"),
        })
    return result
