# ポケモン選出補助ツール（stlite / iPad対応版）

ブラウザだけで動く版です（Mac不要・サーバー不要）。
[stlite](https://github.com/whitphx/stlite) を使い、Streamlit アプリを
ブラウザ内（WebAssembly / Pyodide）で実行します。

## 構成ファイル

| ファイル | 役割 |
|----------|------|
| `index.html` | stlite を読み込んでアプリを起動。PWA設定もここ |
| `app.py` | アプリ本体（元の `pokemon_selector.py` のブラウザ版）|
| `manifest.json` | ホーム画面アプリ化の設定 |
| `icon-192.png` / `icon-512.png` | アプリアイコン |
| `serve_preview.py` / `preview.sh` | ローカル確認用サーバー（本番では不要）|

## データの保存場所と使い方

- 初回はデータが空です。サイドバーの「JSONファイルを選択」から
  手持ちの **`team_data.json`** を読み込んでください（アップロード運用）。
- 一度読み込めば、以降は **その端末のブラウザ内（IndexedDB）** に自動保存され、
  ページを閉じても残ります（`index.html` の `idbfsMountpoints: ["/mnt"]` で永続化）。
- 別端末へ移すときは「💾 現在のデータをJSONで保存」でバックアップし、
  移行先で読み込んでください。

> ⚠️ `team_data.json` は個人の構築・戦績データです。**公開リポジトリには含めないでください**
> （`.gitignore` で除外済み）。アプリには同梱せず、使うときにアップロードする運用です。

## ローカルで確認する

```bash
cd web
./preview.sh
# → ブラウザで http://localhost:8600/index.html を開く
```

※ `file://` で直接開くと動きません（CDNからのwheel取得がブロックされるため）。
必ずサーバー経由（上記 or GitHub Pages）で開いてください。

## iPad で使えるようにする（GitHub Pages 無料デプロイ）

1. GitHub で新しいリポジトリを作成（例: `pokemon-selector`）
2. この `web/` フォルダの中身（`index.html` 等）をリポジトリ直下にアップロード
3. リポジトリの **Settings → Pages** で
   - Source: `Deploy from a branch`
   - Branch: `main` / `(root)` を選択して保存
4. 数分後に `https://<ユーザー名>.github.io/pokemon-selector/` で公開される
5. iPad の Safari でそのURLを開く
6. 「共有」→「ホーム画面に追加」でアプリ化

これで **Mac不要・ネットさえあればどこでも** 使えます。
一度開けばオフラインでも起動します（ブラウザがキャッシュするため）。
