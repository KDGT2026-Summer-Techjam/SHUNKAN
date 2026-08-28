# 単体HTMLからDjango接続への実装手順

## この資料の目的

画面案は `core/templates/core/` に置き、Django Templatesとして表示する。画面構造、文言、フォーム項目、画面間の導線を確認したうえで、対応するIssueの範囲でデータ表示、保存処理、認証、CSS、JavaScriptを段階的に接続する。

現在は `{% load static %}`、`{% static %}`、`{% url %}`、POSTフォームの `{% csrf_token %}` を接続済みである。Django標準Authによる新規登録・ログイン・ログアウトと、未ログイン利用者をRoom関連画面からログイン画面へ戻す制御も実装済みである。開発用の `DEBUG=True` 環境では `seed_demo` が公開デモアカウント `demo / demo` を作成する。Room一覧・作成・詳細、Task作成・編集・削除・完了切替、SHUNKAN-logと写真の保存、Room別Album表示はログイン中の利用者のRoomへ接続済みである。Room状態による操作制御、写真の形式・容量検証、PostgreSQLの期間・Room境界・完了状態・写真枚数制約も実装済みである。画面が表示できることだけでなく、PostgreSQLの回帰テストと主要導線の確認を完了条件とする。

## 現在の単体HTML

| ファイル | 画面の目的 | Django化後の候補URL |
| --- | --- | --- |
| `core/templates/core/signup.html` | 新規登録画面 | `/accounts/signup/` |
| `core/templates/core/login.html` | ログイン画面 | `/accounts/login/` |
| `core/templates/core/home.html` | ログイン画面へのリダイレクト | `/` |
| `core/templates/core/rooms.html` | 自分のRoom一覧とRoom作成 | `/rooms/` |
| `core/templates/core/room_detail.html` | Room状態に応じたホーム | `/rooms/<room_id>/` |
| `core/templates/core/room_active.html` | 旧URLからRoom一覧へ案内する互換テンプレート | `/rooms/active/` |
| `core/templates/core/room_ended.html` | 旧URLからRoom一覧へ案内する互換テンプレート | `/rooms/ended/` |
| `core/templates/core/tasks.html` | Task一覧、追加、完了操作 | `/rooms/<room_id>/tasks/` |
| `core/templates/core/moments_new.html` | SHUNKAN-logと写真の入力 | `/rooms/<room_id>/moments/new/` |
| `core/templates/core/album.html` | Room別アルバム | `/rooms/<room_id>/album/` |

画像を使う画面は、既存の `static/core/images/` を相対参照している。単体HTMLの段階では見た目を完成させず、画像・文言・フォームの意味を確認する。

## 現在のテンプレート接続状態

- 実機能は `/rooms/<room_id>/`、`/rooms/<room_id>/tasks/`、`/rooms/<room_id>/moments/new/`、`/rooms/<room_id>/album/` のRoom別URLで扱う。旧プレビューURLはRoom一覧へリダイレクトする互換経路である。
- `core/views.py` は、ログイン中の利用者が所有するRoom、Task、SHUNKAN-log、Photoだけを扱う。Roomホームには実データの進捗、次のTask、最新SHUNKAN-logを表示する。
- 撮影UI以外は `core/templates/core/base.html` を継承し、本番用CSS `static/core/css/app.css` を使う。撮影UIだけは固有体験を維持するため `shunkan-preview.css` を使う。
- 秒単位カウントダウンは `static/core/js/countdown.js` で表示する。保存可否などのサーバー制約はJavaScriptへ委ねない。

## テンプレートを更新する手順

1. 対応するIssue、[07-要件定義.md](07-要件定義.md)、[08-ルーム中心設計.md](08-ルーム中心設計.md)を読み、変更対象と完了条件を確認する。
2. `core/templates/core/` の対象HTMLだけを更新する。画面遷移はファイル名ではなく `{% url %}`、静的ファイルは `{% static %}`、POSTフォームは `{% csrf_token %}` を使う。
3. `label` と入力要素を `for` と `id` で対応させ、ボタン・リンクには操作対象が分かる文言を付ける。状態は色だけで表さない。
4. URL逆引き、見出し、必須・任意、空状態、終了後の操作不可メッセージを確認する。
5. プロダクト判断が変わる場合は、同じ変更で要件・設計資料も更新する。データモデル、保存処理、CSS、JavaScriptは対応Issueの範囲で追加する。

## データ、CSS、JavaScriptを追加する手順

1つのPRで全画面を接続しない。Issueの対象画面と必要なデータだけを、次の順序で置き換える。

### 1. Djangoテンプレートの共通部分を切り出す

対象画面が2つ以上で共通のヘッダーやナビゲーションを持つ場合だけ、`core/templates/core/base.html` を新設する。

- `{% load static %}` を追加する。
- HTMLの共通部分を `base.html` に切り出し、各画面で `{% extends "core/base.html" %}` と `{% block content %}` を使う。
- CSSは `static/core/css/`、JavaScriptは `static/core/js/` に置き、`{% static %}` で参照する。
- 画像も `static/core/images/` を `{% static %}` で参照する。

共通化しない画面は、単体HTMLをそのままDjangoテンプレートとして使ってよい。共通化のためだけに表示仕様を変えない。

### 2. URLとビューを接続する

`core/urls.py` に要件定義のURLを追加し、`core/views.py` から対象テンプレートを返す。リンクはファイル名ではなく、名前付きURLを使う。

```django
<a href="{% url 'room_detail' room.pk %}">Roomへ戻る</a>
```

Roomを扱うビューは、URLのIDだけで取得しない。必ずログイン中の利用者が所有するRoomへ絞る。

```python
room = get_object_or_404(Room, pk=room_id, owner=request.user)
```

### 3. 表示データを固定値から置き換える

単体HTMLにあるサンプル文言・件数・日時・一覧を、ビューから渡すデータへ置き換える。

- Roomホーム: Room名、開始・終了日時、秒単位カウントダウン、進捗、次のTask、最新のSHUNKAN-log
- Room一覧: ログイン中の利用者が所有するRoomだけ
- Task: 選択中RoomのTaskと進捗
- SHUNKAN-log: 選択中Roomのカテゴリ、関連Task、入力値
- アルバム: 選択中Roomの完了Task、SHUNKAN-log（この瞬間へのひとこと）、写真

データが0件のときは、サンプルのTaskや写真を表示せず、空状態を表示する。

### 4. フォームと保存処理を接続する

フォームは対応するDjango Formへ置き換える。Room、所有者、完了日時などの信頼してはいけない値をブラウザから受け取らない。

| 画面 | 単体HTMLの主な入力 | Django接続時の確認 |
| --- | --- | --- |
| Task | `title`、`due_date`、`category` | `room` はURLから決定する。カテゴリは同じRoomだけ、期限はRoom期間内だけ許可する。 |
| 今を残す | `body`、`occurred_at`、`category`、`task` | カテゴリとTaskは同じRoomだけ許可し、通常ログの発生日時はRoom期間内にする。 |
| 写真 | `images`、`captions` | `request.FILES` を使い、JPEG / PNG / WebP、1枚5MB以下、SHUNKAN-log 1件あたり最大3枚を検証する。 |

ファイルを含むフォームには `enctype="multipart/form-data"` を付ける。Task完了時は `completed_at` をサーバー側で記録し、必要なら関連するSHUNKAN-logと写真を同じRoom内へ保存する。

### 5. Room状態をサーバー側で制御する

開催中以外のRoomでは、Task、通常SHUNKAN-log、写真、Room設定を更新できない。ボタンを無効表示にするだけでなく、直接URLやPOSTでも共通の状態判定により拒否する。

終了後の振り返り投稿はAdditional機能である。実装するまでは終了済みRoomを閲覧専用とし、単体HTMLの説明文を保存可能な仕様として扱わない。

### 6. CSSとJavaScriptを追加する

HTMLとデータ接続が確認できてから、必要な範囲だけを追加する。

- CSSはスマートフォン幅を基準に、`static/core/css/` に置く。主要操作は片手で押しやすいサイズにする。
- JavaScriptは秒単位カウントダウンなど、ブラウザ側で必要な機能だけに使う。保存可否、所有者、Room状態の判定はJavaScriptだけに任せない。
- 色だけで状態を表さず、終了済み、完了、未完了などのラベル・文言・アイコンも併用する。

### 7. テストと確認を行う

最低限、次を実行する。

```bash
python manage.py check
python manage.py test
```

PostgreSQLに接続できる環境で確認する。画面ごとに、少なくとも通常、空状態、完了、終了後、他人のRoomへ直接アクセスした場合をテストする。スマートフォン幅でも主要操作と画面遷移を確認する。

## レビュー時の確認項目

- 単体HTMLの変更は、対応Issueの範囲に収まっているか。
- Django化した画面で、仮リンクを `{% url %}`、画像参照を `{% static %}` に置き換えたか。
- Roomの取得、関連データの表示、フォームの選択肢をログイン中の利用者と選択中Roomへ絞ったか。
- Room終了後の更新を、UIとサーバー側の両方で拒否しているか。
- CSSやJavaScriptが、単体HTMLの構造・アクセシビリティ・サーバー側の制約を壊していないか。
- `python manage.py check` と `python manage.py test` の結果、未実行理由をPRへ記載したか。
