# Renderデプロイ手順

このリポジトリは、ルートの`render.yaml`を使って、旬間 (SHUNKAN) のWebサービスとPostgreSQLをまとめて作成できる。

## 作成されるもの

- Django Web Service（Python、Gunicorn、シンガポールリージョン）
- Render PostgreSQL
- 静的ファイルを収集して配信する設定
- Render内のPostgreSQL接続文字列を`DATABASE_URL`としてWeb Serviceへ渡す設定
- 本番用のランダムな`DJANGO_SECRET_KEY`
- DB接続を確認する`/healthz/`
- Gitの接続先ブランチへpushしたときの自動デプロイ

`render.yaml`の初期設定は無料プランである。無料Web Serviceは一定時間アクセスがないと休止し、無料PostgreSQLには有効期限がある。継続公開や発表当日の利用では、Renderのダッシュボードで各プランを確認して切り替える。

## デプロイ手順

1. この変更をGitHubのデプロイ対象ブランチへpushする。
2. RenderでGitHubを接続し、**New +** → **Blueprint** を選ぶ。
3. `SHUNKAN`リポジトリとデプロイ対象ブランチを選び、`render.yaml`を読み込む。
4. 内容を確認してApplyする。無料Web Serviceでは`preDeployCommand`を利用できないため、ビルドでは依存関係のインストールと静的ファイル収集だけを行い、`startCommand`のGunicorn起動前に`python manage.py migrate --noinput`を1回実行する。migrationが失敗した場合はWeb Serviceを起動しない。
5. デプロイ完了後、`https://<service-name>.onrender.com/healthz/`が`{"status": "ok"}`を返すことと、`https://<service-name>.onrender.com/accounts/login/`にログイン画面が表示されることを確認する。

## 環境変数

`render.yaml`が次の値を設定するため、初回デプロイで秘密情報をリポジトリへ追加する必要はない。

| 変数 | 設定元 | 用途 |
| --- | --- | --- |
| `DATABASE_URL` | Render PostgreSQL | 本番DB接続 |
| `DJANGO_SECRET_KEY` | Renderが生成 | セッション・CSRF署名 |
| `DJANGO_DEBUG` | `false` | 本番モード |
| `ALLOW_PHOTO_UPLOADS` | `false` | 外部ストレージ導入まで写真保存を停止 |
| `RENDER_EXTERNAL_HOSTNAME` | Renderが提供 | Renderの公開URLを許可（Django設定で自動利用） |

カスタムドメインを追加した場合は、RenderのWeb Serviceに次を追加して再デプロイする。

```env
DJANGO_ALLOWED_HOSTS=.onrender.com,app.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
```

実際のURL・パスワード・接続文字列は、Git、Issue、チャットに記録しない。

## Render上でデモデータを投入する

デプロイ後にRoomやTaskの確認用データを作る場合は、`seed_demo`を本番サービスの実行環境で1回だけ実行する。`seed_demo`は本番PostgreSQLへデモユーザー、Room、Task、SHUNKAN-logを書き込むため、発表・画面確認など、投入先を明確にした場合だけ使う。

### 事前設定

Render Dashboardで対象Web Serviceの **Environment** を開き、次の環境変数を追加する。

| 変数 | 値 | 用途 |
| --- | --- | --- |
| `DEMO_USER_PASSWORD` | Render上だけで管理するデモ用パスワード | `demo`ユーザーのログイン用 |

`DJANGO_DEBUG`や`DEBUG`を`true`に変更してはいけない。本番の`DEBUG=False`でも`DEMO_USER_PASSWORD`があれば実行できる。パスワードはGit、Issue、チャット、スクリーンショットに記録しない。

### 有料Web Serviceの場合

1. 環境変数を保存して、デプロイが成功するまで待つ。
2. Web Serviceの **Shell** を開く。
3. 次を実行する。

```bash
python manage.py seed_demo
```

4. `デモデータを投入しました。`と表示されたら、`/accounts/login/`へアクセスする。
5. ユーザー名`demo`と、`DEMO_USER_PASSWORD`に設定した値でログインする。

### 無料Web Serviceの場合

無料Web ServiceではDashboardのShellを利用できないため、Render CLIのOne-Off Jobを使う。Render CLIへのログインと、対象サービスのIDが必要である。

```bash
render jobs create <service-id> --start-command "python manage.py seed_demo"
```

One-Off Jobは対象サービスの最新ビルドと設定済み環境変数を使う。実行ログで`デモデータを投入しました。`を確認してから、`/accounts/login/`で`demo`ユーザーを使う。One-Off Jobには実行時間に応じた料金が発生する場合がある。

### 実行後の注意

- `seed_demo`を`render.yaml`の`startCommand`や`preDeployCommand`へ追加しない。デプロイのたびにデモデータが更新されるためである。
- 再実行すると`demo`ユーザーのパスワードや、名前が一致するデモデータが更新される。
- `seed_demo`は写真ファイルを作成しない。本番では`ALLOW_PHOTO_UPLOADS=false`のため、写真の確認はローカル環境で行う。
- 確認が終わったら、Render上の`DEMO_USER_PASSWORD`を削除またはローテーションする。ただし、環境変数を削除しても既に作成された`demo`ユーザーは削除されない。

## PostgreSQL認証情報が流出した場合のローテーション

接続文字列をチャット、Issue、ログ等へ貼った場合は、削除だけではなく直ちに失効させる。

1. Render Dashboardで対象DB `shunkan-db` を開く。
2. **Info** の認証情報から **Reset Database Password**（表示名は変更される場合がある）を実行する。
3. Connected Serviceの `shunkan` にある `DATABASE_URL` が `shunkan-db` の `connectionString` 参照であることを確認する。手入力値なら、新しいInternal Database URLへ置き換える。
4. Web Serviceを再デプロイし、migrationと起動が成功することを確認する。
5. 旧URLを保存していたローカル `.env`、CI、共有メモ、シェル履歴等を新しい値へ更新または削除する。新しいURLはGit・Issue・チャットへ貼らない。
6. `python manage.py showmigrations` 相当の確認と、ログイン・Room一覧表示を行う。

パスワードのリセットからWeb Service再起動までは、一時的にDB接続エラーが発生し得るため連続して実施する。漏えい範囲が不明な場合は、DB内ユーザー情報や不審な変更も確認する。

## 公開後の確認

1. `/healthz/`がHTTP 200で`{"status": "ok"}`だけを返す。
2. `/accounts/login/`が表示され、新規登録、ログイン、ログアウトができる。
3. Roomの作成・一覧・詳細表示ができる。
4. ブラウザの開発者ツールでCSS・画像の`/static/`リクエストが404になっていない。
5. Renderのログに`DisallowedHost`、migration失敗、DB接続失敗がない。

## 写真を有効化する前の注意

Render Web Serviceのローカルファイル領域は永続ストレージではない。現在は `ALLOW_PHOTO_UPLOADS=false` により本番の写真アップロードを停止する。Render Persistent Diskまたは外部画像ストレージを設定し、再デプロイ後も画像が残ることを確認してから `true` へ変更する。静的ファイルはビルド時に収集するため、この制約の対象ではない。
