import sys
from datetime import datetime
from actions.gather import run_gather
from actions.post import run_post
from actions.open import run_open

def print_help():
    print("""
使用方法: python main.py [コマンド] [日付:YYYYMMDD]
コマンド一覧:
  gather   - WebスクレイピングとTwitter情報収集を行い、結果をファイルに保存します。
  open     - 取得した情報に含まれるURLをブラウザで一括で開きます。
  post     - 取得した情報を整理してTwitterに投稿します（プレビュー付き）。
""")

def main():
    if len(sys.argv) < 3:
        print_help()
        sys.exit(1)
        
    command = sys.argv[1]
    target_date = sys.argv[2]
    
    try:
        datetime.strptime(target_date, "%Y%m%d")
    except ValueError:
        print(f"エラー: 日付の形式が正しくありません: {target_date} (例: 20260501)")
        sys.exit(1)
        
    if command == "gather":
        run_gather(target_date)
    elif command == "open":
        run_open(target_date)
    elif command == "post":
        run_post(target_date)
    else:
        print(f"エラー: 不明なコマンドです: {command}")
        print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
