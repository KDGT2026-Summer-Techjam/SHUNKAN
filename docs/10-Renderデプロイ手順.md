# Renderデプロイ手順

このリポジトリは、ルートの`render.yaml`を使って、旬間 (SHUNKAN) のWebサービスとPostgreSQLをまとめて作成できる。

## 作成されるもの

- Django Web Service（Python、Gunicorn、シンガポールリージョン）
- Render PostgreSQL
- 静的ファイルを収集して配信する設定
- Render内のPostgreSQL接続文字列を`DATABASE_URL`としてWeb Serviceへ渡す設定
- 本番用のランダムな`DJANGO_SECRET_KEY`
- Gitの接続先ブランチへpushしたときの自動デプロイ

`render.yaml`の初期設定は無料プランである。無料Web Serviceは一定時間アクセスがないと休止し、無料PostgreSQLには有効期限がある。継続公開や発表当日の利用では、Renderのダッシュボードで各プランを確認して切り替える。

## デプロイ手順

1. この変更をGitHubのデプロイ対象ブランチへpushする。
2. RenderでGitHubを接続し、**New +** → **Blueprint** を選ぶ。
3. `SHUNKAN`リポジトリとデプロイ対象ブランチを選び、`render.yaml`を読み込む。
4. 内容を確認してApplyする。初回ビルドでは依存関係のインストール、静的ファイル収集、migrationを行う。
5. デプロイ完了後に表示される`https://<service-name>.onrender.com/accounts/login/`を開き、ログイン画面が表示されることを確認する。

## 環境変数

`render.yaml`が次の値を設定するため、初回デプロイで秘密情報をリポジトリへ追加する必要はない。

| 変数 | 設定元 | 用途 |
| --- | --- | --- |
| `DATABASE_URL` | Render PostgreSQL | 本番DB接続 |
| `DJANGO_SECRET_KEY` | Renderが生成 | セッション・CSRF署名 |
| `DJANGO_DEBUG` | `false` | 本番モード |
| `RENDER_EXTERNAL_HOSTNAME` | Renderが提供 | Renderの公開URLを許可（Django設定で自動利用） |

カスタムドメインを追加した場合は、RenderのWeb Serviceに次を追加して再デプロイする。

```env
DJANGO_ALLOWED_HOSTS=.onrender.com,app.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
```

実際のURL・パスワード・接続文字列は、Git、Issue、チャットに記録しない。

## 公開後の確認

1. `/accounts/login/`が表示される。
2. 新規登録、ログイン、ログアウトができる。
3. Roomの作成・一覧・詳細表示ができる。
4. ブラウザの開発者ツールでCSS・画像の`/static/`リクエストが404になっていない。
5. Renderのログに`DisallowedHost`、migration失敗、DB接続失敗がない。

## 写真を有効化する前の注意

Render Web Serviceのローカルファイル領域は永続ストレージではない。写真アップロードの実処理を公開するIssueでは、Render Persistent Diskまたは外部画像ストレージを選び、アップロード先を設定してから有効化する。静的ファイルはビルド時に収集するため、この制約の対象ではない。
