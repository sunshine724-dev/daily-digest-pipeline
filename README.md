# Daily Digest Pipeline

毎日の作業ログを自動収集し、Notionデータベースに日別ページとして記録するパイプラインです。

## 概要

- **22:55** に自動実行し、その日の作業データを収集
- 固定フォーマットのMarkdownを生成
- Notion APIで**データベースに新規ページを作成**（日別に1ページ）
- **未実行日の自動補完**: PCが起動していなかった等の理由でパイプラインが実行されなかった日がある場合、次回実行時にNotionデータベースの最新記録日を参照し、不足分を自動で遡って補完します
- **23:00** の夜用Notionエージェントが日記ページへ反映

## 収集対象

| データソース      | 収集内容                            |
| :---------------- | :---------------------------------- |
| **Notion**        | 指定日に編集されたページのタイトル・URL |
| **GitHub**        | 指定日のコミット（リポジトリ別）      |
| **Chrome**        | 指定日の閲覧履歴（訪問回数順）        |
| **ActivityWatch** | アプリ別の使用時間                  |
| **Google Calendar** | 指定日の予定一覧                  |
| **WhatPulse**     | キー入力数・クリック数・スクロール数・ネットワーク使用量・稼働時間 |

## Notionデータベース構成

パイプラインはNotionの**データベース**にページを追加する方式です。  
データベースには以下のプロパティが必要です：

| プロパティ名           | 型         | 説明                                      |
| :--------------------- | :--------- | :---------------------------------------- |
| `Title`                | タイトル   | 「Daily Digest YYYY-MM-DD」が自動設定される |
| `Date`                 | 日付       | 対象日。未実行日の検出に使用               |
| `AI Summary Generated` | チェックボックス | Notion AIが要約を書いたかどうかの判定用 |

## セットアップ

### 1. 仮想環境とパッケージ

```powershell
cd c:\Users\sunshine724\Desktop\development-root\development-win\daily-digest-pipeline
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 環境変数

`.env.example` をコピーして `.env` を作成し、各値を設定：

```powershell
Copy-Item .env.example .env
# .env を編集して以下を設定：
# - NOTION_API_TOKEN
# - MCP_LOG_DB_ID      ← NotionデータベースのID（URLから取得）
# - GITHUB_TOKEN
# - GITHUB_USERNAME
# - WHATPULSE_API_BASE  ← デフォルト: http://localhost:3490（通常は変更不要）
```

### 3. Notionデータベースの準備

1. Notionで新規データベース（フルページ）を作成
2. 上記のプロパティ（`Title`, `Date`, `AI Summary Generated`）を追加
3. データベースページの **「…」→「コネクトの追加」** から `daily-digest-pipeline` を接続
4. URLからDatabase IDを取得し、`.env` の `MCP_LOG_DB_ID` に設定
   - URL例: `https://notion.so/ワークスペース/{Database ID}?v={View ID}`

### 4. 動作確認

```powershell
# Notion更新なしでテスト（ターミナル出力のみ）
python main.py --dry-run

# 実際にNotionを更新
python main.py
```

### 5. スケジューラ登録（毎日22:55自動実行）

```powershell
# 管理者権限で実行
.\setup_scheduler.ps1

# 削除する場合
.\setup_scheduler.ps1 -Remove
```

## テスト

```powershell
python -m pytest tests/ -v
```

## プロジェクト構成

```
daily-digest-pipeline/
├── config.py              # 設定管理（.env読み込み）
├── main.py                # メインオーケストレータ（未実行日の自動補完ロジック含む）
├── formatter.py           # Markdown生成
├── uploader.py            # Notion DBへのページ作成・最新日付取得
├── collectors/
│   ├── notion_collector.py
│   ├── github_collector.py
│   ├── chrome_collector.py
│   ├── activitywatch_collector.py
│   ├── gcal_collector.py
│   └── whatpulse_collector.py
├── tests/
│   ├── test_collectors.py
│   └── test_formatter.py
├── .env.example
├── requirements.txt
├── setup_scheduler.ps1
└── README.md
```

## 注意事項

- 各収集モジュールは **独立して動作** します。特定のサービスが利用できなくても、他のデータは正常に収集されます（graceful degradation）
- Chrome履歴はブラウザが使用中でも読み取り可能（一時コピーを使用）
- ActivityWatchが起動していない場合は自動的にスキップされます
- **WhatPulse** はClient APIを有効にする必要があります（クライアント設定 → Client API → 有効化、デフォルトポート `3490`）。起動していない場合は自動的にスキップされます
- WhatPulseは `/v1/unpulsed`（最後のパルス以降の統計）を取得します。正確な日次データを得るには、パイプライン実行後にパルスすることを推奨します
- **未実行日の補完**は、Notionデータベース上の最新の `Date` から今日までの差分を自動計算して行われます。ローカルにSQLite等の状態管理ファイルは不要です
