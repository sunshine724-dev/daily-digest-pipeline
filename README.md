# Daily Digest Pipeline

毎日の作業ログを自動収集し、Notion「MCPログ」ページを更新するパイプラインです。

## 概要

- **22:55** に自動実行し、その日の作業データを収集
- 固定フォーマットのMarkdownを生成
- Notion APIで「MCPログ」ページを **全文置換** で更新
- **23:00** の夜用Notionエージェントが日記ページへ反映

## 収集対象

| データソース      | 収集内容                            |
| :---------------- | :---------------------------------- |
| **Notion**        | 今日編集されたページのタイトル・URL |
| **GitHub**        | 今日のコミット（リポジトリ別）      |
| **Chrome**        | 今日の閲覧履歴（訪問回数順）        |
| **ActivityWatch** | アプリ別の使用時間                  |

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
# - GITHUB_TOKEN
# - GITHUB_USERNAME
```

### 3. 動作確認

```powershell
# Notion更新なしでテスト（ターミナル出力のみ）
python main.py --dry-run

# 実際にNotionを更新
python main.py
```

### 4. スケジューラ登録（毎日22:55自動実行）

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
├── main.py                # メインオーケストレータ
├── formatter.py           # Markdown生成
├── uploader.py            # Notion APIアップロード
├── collectors/
│   ├── notion_collector.py
│   ├── github_collector.py
│   ├── chrome_collector.py
│   └── activitywatch_collector.py
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
