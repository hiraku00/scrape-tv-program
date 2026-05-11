# ニュース番組情報収集・投稿システム (News Scraper)

## セットアップ

1. **環境変数の準備**
   `.env.example` をコピーして `.env` ファイルを作成し、必要なAPIキーを設定してください。
   ```bash
   cp .env.example .env
   ```

## 使い方

すべての操作は `main.py` を通じて行います。

### 1. 番組情報の収集
指定した日付（YYYYMMDD）の情報を収集し、整理・ソート済みのテキストファイルを生成します。
**日付を省略した場合は、自動的に前日の情報が取得されます。**
生成されたファイルを編集して、投稿内容を最終調整します。

```bash
python main.py gather [20260507]
```
生成ファイル: `output/YYYYMMDD.txt`

### 2. URLの確認
取得したURLに間違いがないか、ブラウザで一括確認できます。
（日付省略時は前日）
```bash
python main.py open [20260507]
```

### 3. Twitterへの投稿
`YYYYMMDD.txt` の内容を読み込み、自動で分割して投稿します。
（日付省略時は前日）
実行時にコンソール上で**投稿内容のプレビュー**が表示されます。
```bash
python main.py post [20260507]
```

## ディレクトリ構造
- `core/`: ログ、モデル、ユーティリティ
- `scrapers/`: 各媒体のスクレイピングロジック
- `actions/`: コマンドの実体 (gather, post, open)
- `config/`: 番組設定 (`programs.json`)
- `output/`: 生成ファイル
