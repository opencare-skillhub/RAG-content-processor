# FastGPT Content Processor

FastGPTナレッジベースコンテンツの管理・処理を行うコマンドラインツール。ナレッジベースのクエリ、コンテンツ検索、ファイルアップロード、およびWeChat記事のダウンロード・クリーニング・アップロードをサポートします。

## 機能

- **list-datasets**: すべてのFastGPTデータセットを一覧表示
- **list-collections**: データセット内の記事/コレクションを一覧表示
- **search**: ナレッジベース内のセマンティック検索
- **upload-file**: 単一のMarkdownファイルをアップロード
- **upload-folder**: フォルダ内のMarkdownファイルを一括アップロード
- **download-wechat**: MCP経由でWeChat記事を一括ダウンロード
- **clean-wechat**: 2段階のWeChat Markdownクリーニング
- **download-and-clean**: ワークフロー統合：ダウンロード → クリーニング → アップロード

## インストールと実行

### 推奨方式：uv

```bash
cd fastgpt-content-processor
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

### 標準方式：venv

```bash
cd fastgpt-content-processor
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

### コマンド実行

```bash
python3 main.py --help
python3 main.py list-datasets
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS 変異"
```

## 使用例

### すべてのデータセットを一覧表示

```bash
python3 main.py list-datasets
```

### データセット内の記事を一覧表示

```bash
python3 main.py list-collections --dataset-id 697b19a113081cf58b45cac3
```

### ナレッジベースで検索

```bash
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS 変異"
```

### 単一ファイルをアップロード

```bash
python3 main.py upload-file --file article.md --dataset-id 697b19a113081cf58b45cac3
```

### フォルダを一括アップロード

```bash
python3 main.py upload-folder --folder ./articles --dataset-id 697b19a113081cf58b45cac3
```

### WeChat記事をダウンロード

`urls.txt`にWeChat記事URLを1行に1つずつ記述：

```bash
python3 main.py download-wechat --urls urls.txt --output ./wechat-downloads
```

### WeChat記事をクリーニング

```bash
python3 main.py clean-wechat --input ./wechat-downloads --output ./cleaned-articles
```

### 統合ワークフロー（ダウンロード → クリーニング → アップロード）

```bash
python3 main.py download-and-clean \
  --urls urls.txt \
  --output ./wechat-downloads \
  --cleaned-output ./cleaned-articles \
  --dataset-id 697b19a113081cf58b45cac3
```

## プロジェクト構造

```
fastgpt-content-processor/
├── main.py                      # CLIエントリーポイント
├── fastgpt_sync.py              # FastGPT APIラッパー
├── fetchers/                    # コンテンツフェッチャー
├── cleaners/                    # コンテンツクリーナー
├── utils/                       # ユーティリティ
├── tests/                       # テストディレクトリ
├── .env.example                 # 環境変数テンプレート
├── requirements.txt             # Python依存関係
└── README.md                    # ドキュメント
```

## テスト

[`tests/README.md`](tests/README.md)を参照してください。

```bash
python3 -m pytest
```

## ロードマップ

### 短期：再現性と検証
- `python3`の統一と仮想環境のドキュメント整備
- コアロジックテストの追加
- FastGPT、MCP、サンプルスクリプトの境界明確化

### 中期：保守性とコラボレーション
- クリーニングパイプラインの統一
- CLIパラメータとインタラクティブ体験の最適化
- dry-run / プレビューモードの追加
- 詳細なロギングと統計の追加

### 長期：拡張性とプラットフォーム化
- プラグインベースのフェッチャー / クリーナー / アップロードアダプタ
- より多くのコンテンツソースのサポート
- ワークフローベースの処理パイプライン
- 設定可能なルールとバッチジョブオーケストレーション

## コントリビューション

コード、ドキュメント、テスト、使用経験のコントリビューションを歓迎します。

### 推奨プラクティス
- 要件や問題を記述するissueを先に作成
- ロジック変更前にテストを追加
- ドキュメントをコードと同期
- 新しいクリーニングルール追加時にサンプル入力/出力を提供

## 謝辞

以下のプロジェクトとリソースに感謝します：

- [wechat-article-downloader](https://github.com/qiye45/wechatDownload)
- [baoyu-format-markdown](https://github.com/baoyu-tech/markdown-formatter)
- [markdown-frontmatter-doctor](https://github.com/example/frontmatter-doctor)
- [FastGPT APIドキュメント](https://doc.fastgpt.in/docs/development/api/)

## ライセンス

MIT License

---

**他の言語**: [中文](README.md) | [English](README.en.md) | [Русский](README.ru.md) | [한국어](README.ko.md)
