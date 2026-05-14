import os
import time
import tweepy
from pathlib import Path
from datetime import datetime
from core.logger import setup_logger
from dotenv import load_dotenv

def get_tweet_length(text):
    """Twitterのカウント方法（半角1, 全角2）で文字数を計算"""
    length = 0
    for char in text:
        if ord(char) <= 127:
            length += 1
        else:
            length += 2
    return length

rate_limit_remaining = None
rate_limit_reset = None

def update_rate_limit_from_response(response, logger):
    """レスポンスからレート制限情報を取得・更新する"""
    global rate_limit_remaining, rate_limit_reset
    try:
        # v1.1 互換ヘッダーを試す
        if hasattr(response, 'resp') and hasattr(response.resp, 'headers'):
            headers = response.resp.headers
            remaining = headers.get('x-rate-limit-remaining')
            reset = headers.get('x-rate-limit-reset')
            limit = headers.get('x-rate-limit-limit')

            if remaining is not None and reset is not None:
                rate_limit_remaining = int(remaining)
                rate_limit_reset = int(reset)
                limit_val = int(limit) if limit is not None else 'N/A'
                logger.debug(f"レート制限情報更新 (Header): 残り={rate_limit_remaining}, 上限={limit_val}, リセット={datetime.fromtimestamp(rate_limit_reset)}")
                return True
        
        # v2 レスポンスの rate_limit 属性
        elif hasattr(response, 'rate_limit') and response.rate_limit is not None:
            rate_limit_remaining = response.rate_limit.remaining
            rate_limit_reset = response.rate_limit.reset
            limit = response.rate_limit.limit
            logger.debug(f"レート制限情報更新 (v2 response): 残り={rate_limit_remaining}, 上限={limit}, リセット={datetime.fromtimestamp(rate_limit_reset)}")
            return True
            
    except Exception as e:
        logger.warning(f"レート制限情報解析中にエラー: {e}")
    return False

def post_tweet_with_retry(client, text, in_reply_to_tweet_id, logger, max_retries=3, base_delay=10):
    """ツイート投稿関数 (リトライ、レート制限考慮)"""
    global rate_limit_remaining, rate_limit_reset

    for attempt in range(max_retries):
        try:
            # 事前待機チェック
            if rate_limit_remaining is not None and rate_limit_remaining <= 1:
                if rate_limit_reset is not None and rate_limit_reset > 0:
                    wait_time = datetime.utcfromtimestamp(rate_limit_reset) - datetime.utcnow()
                    wait_seconds = max(0, wait_time.total_seconds()) + 5
                    if wait_seconds > 0:
                        logger.info(f"リセットまで {wait_seconds:.1f} 秒待機します...")
                        time.sleep(wait_seconds)
                rate_limit_remaining = None
                rate_limit_reset = None

            # 投稿実行
            response = client.create_tweet(
                text=text,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
                user_auth=True
            )
            tweet_id = response.data["id"]
            update_rate_limit_from_response(response, logger)
            return tweet_id

        except tweepy.errors.TooManyRequests as e:
            logger.warning(f"レートリミット超過 (429エラー): {e}")
            reset_time = None
            if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'headers'):
                reset_header = e.response.headers.get('x-rate-limit-reset')
                if reset_header:
                    try:
                        reset_time = int(reset_header)
                        rate_limit_reset = reset_time
                        logger.info(f"レートリミットリセット時刻 (ヘッダーより): {datetime.fromtimestamp(reset_time)}")
                    except ValueError:
                        pass

            if reset_time:
                wait_time = datetime.utcfromtimestamp(reset_time) - datetime.utcnow()
                delay = max(1, wait_time.total_seconds()) + 5
                logger.warning(f"リセット時刻に基づき、{delay:.1f} 秒待機します...")
            else:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"リセット時刻不明。{delay}秒待機します...")

            time.sleep(delay)
            rate_limit_remaining = None
            rate_limit_reset = None

        except tweepy.errors.Forbidden as e:
            logger.error(f"Twitter APIエラー (Forbidden - 403): {e}")
            is_duplicate = False
            if hasattr(e, 'api_codes') and 187 in getattr(e, 'api_codes', []):
                is_duplicate = True
            elif "duplicate content" in str(e).lower():
                is_duplicate = True

            if is_duplicate:
                logger.error("重複ツイートのため、リトライせずに終了します。")
            else:
                logger.error("重複以外のForbiddenエラーのため、リトライせずに終了します。")
            return None

        except tweepy.errors.HTTPException as e:
            if e.response is not None and e.response.status_code == 402:
                logger.error(f"Twitter投稿エラー: 402 Payment Required - {e}")
                logger.error("【注意】Twitter API (Freeプラン) の月間ツイート数上限(1500件) または24時間上限(50件) に達した可能性があります。")
                return None
            logger.error(f"Twitter API HTTPエラー: {e}")
            return None

        except tweepy.TweepyException as e:
            logger.error(f"Tweepyエラー: {e}")
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)

        except Exception as e:
            logger.error(f"予期せぬエラー: {e}", exc_info=True)
            return None

    logger.error("ツイート投稿のリトライ上限回数に達しました。")
    return None


def run_post(target_date_str: str):
    logger = setup_logger("post")
    load_dotenv()
    
    # 認証情報の取得
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    access_token = os.getenv("ACCESS_TOKEN")
    access_secret = os.getenv("ACCESS_SECRET")
    
    if not all([api_key, api_secret, access_token, access_secret]):
        logger.error("Twitter投稿用の認証情報(API_KEY, etc.)が.envに設定されていません。")
        return

    # ファイルの読み込み
    out_dir = Path(__file__).parent.parent / "output"
    main_file = out_dir / f"{target_date_str}.txt"
    
    if not main_file.exists():
        logger.error(f"投稿対象のファイルが見つかりません: {main_file}")
        return
        
    with open(main_file, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        logger.warning("ファイルが空のため、投稿をスキップします。")
        return

    # 番組ブロックごとに分割してツイートを組み立て
    blocks = content.split("\n\n")
    target_dt = datetime.strptime(target_date_str, "%Y%m%d")
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"][target_dt.weekday()]
    header = f"{target_dt.strftime('%y/%m/%d')}({weekday_ja})のニュース・ドキュメンタリー番組など\n\n"
    
    tweets = []
    for i, block in enumerate(blocks):
        if not block.strip():
            continue
            
        # 最初の番組にのみヘッダーを付与
        if i == 0:
            tweet_text = header + block
        else:
            tweet_text = block
            
        tweets.append(tweet_text.strip())

    # プレビュー表示
    logger.info(f"=== 投稿プレビュー (全 {len(tweets)} 件) ===")
    for i, t in enumerate(tweets, 1):
        print(f"\n--- ツイート {i} ---\n{t}\n" + "-"*20)
    
    # 投稿実行
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
        
        logger.info(f"=== {target_date_str} の情報(全 {len(tweets)} 件)を投稿します ===")
        
        last_tweet_id = None
        for idx, tweet_text in enumerate(tweets, 1):
            logger.info(f"📝 {idx}/{len(tweets)} 件目を投稿中...")
            logger.debug(f"\n{tweet_text}")
            
            new_tweet_id = post_tweet_with_retry(
                client=client,
                text=tweet_text,
                in_reply_to_tweet_id=last_tweet_id,
                logger=logger
            )
            
            if not new_tweet_id:
                logger.error(f"❌ {idx} 件目のツイート投稿に失敗したため、以降の投稿を中止します。")
                break
                
            last_tweet_id = new_tweet_id
            
            if idx < len(tweets):
                logger.info("⏳ 5秒待機...")
                time.sleep(5)
                
        else:
            # ループがbreakされずに完了した場合
            logger.info(f"✅ すべての投稿が完了しました。")
        
    except Exception as e:
        logger.error(f"Twitter投稿予期せぬエラー: {e}")

