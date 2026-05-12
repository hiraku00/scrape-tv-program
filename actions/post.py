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
            
            response = client.create_tweet(
                text=tweet_text,
                in_reply_to_tweet_id=last_tweet_id
            )
            last_tweet_id = response.data["id"]
            
            if idx < len(tweets):
                logger.info("⏳ 5秒待機...")
                time.sleep(5)
                
        logger.info(f"✅ すべての投稿が完了しました。")
        
    except Exception as e:
        logger.error(f"Twitter投稿エラー: {e}")

