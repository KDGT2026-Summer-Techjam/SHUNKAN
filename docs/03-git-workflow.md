# Git・GitHub 運用手引書

## 大事なルール

- `main` は公開・提出に使う安定ブランチです。 **`main` へのマージはリポジトリ管理者だけ** が行います。
- 普段の統合場所は `dev` です。全メンバーは `dev` から自分の作業ブランチを作ります。
- 作業ブランチから `main` へ直接 PR を出さず、必ず `dev` 宛てに PR を出します。
- 作業は必ず GitHub Issue と結び付けます。`dev` 宛てのPRには `Refs #番号` を書いて関連Issueを示します。`main` 宛てのリリースPRで `Closes #番号` を書くと、`main` への取り込み時にIssueを自動で閉じられます。
- 1つの PR には1つの目的だけを入れます。デザイン調整と機能追加を無関係に混ぜません。
- 誰かの変更を勝手に消したり、履歴を強制的に書き換えたりしません。

```text
main  ← リポジトリ管理者だけが dev から取り込む
  ↑
dev   ← チームの統合場所
  ↑
feature/〇〇  ← 各メンバーが dev から作成して PR を出す
```

## ブランチ名

次の形式を使います。短く、何をするか分かる英小文字・ハイフンで書きます。

```text
feature/task-form
feature/countdown-ui
fix/task-complete-state
docs/team-guide
```

## 初回：リポジトリを準備する人

このリポジトリは、まず土台を `dev` に作ります。リポジトリ管理者または任命された担当者が、Django の初期構成、`.gitignore`、README、初回の `dev` コミットを用意します。

初期化が終わるまで、他のメンバーは勝手に別の初回コミットを作らず、土台担当の連絡を待ってください。土台が `dev` に入った後は、以下の通常手順で作業します。

## 通常の作業手順

### 0. 今の状態を確認する

作業前に、いま自分がどのブランチにいて、未コミットの変更があるか確認します。

```bash
git status
git branch -vv
git remote -v
```

見るポイントは次の3つです。

- `On branch ...` または `## ...` が、現在のブランチです。
- `behind` と出ている場合は、リモート側にまだ取り込んでいない変更があります。
- `??` と出ているファイルは、まだ Git 管理に入っていない新規ファイルです。

未コミットの変更がある場合は、現在の作業をコミットするか、安全に退避してから次へ進みます。内容が分からない変更は削除せず、リーダーへ相談してください。変更を残したまま `git switch dev` や `git pull` を実行すると、切り替えや更新に失敗することがあります。

### 1. `dev` を最新にする

```bash
git switch dev
git pull origin dev
```

`dev` が `origin/dev: behind ...` になっている場合は、作業ブランチを作る前に必ず上の `git pull origin dev` を実行します。

### 2. 自分の作業ブランチを作る

```bash
git switch -c feature/task-form
```

例：

```bash
git switch -c docs/readability-cleanup
```

ブランチ作成前に、対応するIssueの「完了条件」を確認します。完了条件が曖昧なら、作業を始める前にリーダーへ相談します。

### 3. 作業内容を確認して記録する

```bash
git status
git add 変更したファイル
git commit -m "feat: タスク追加フォームを作成"
git push -u origin feature/task-form
```

`git add .` は、意図しないファイルまで入る可能性があります。最初はファイル名を指定して追加してください。

### 4. GitHubで PR を作る

- **base（取り込み先）:** `dev`
- **compare（自分のブランチ）:** `feature/task-form`
- タイトル例: `feat: タスク追加フォームを作成`
- 担当者またはレビュー担当を指定する

PR の説明には、次のテンプレートを使います。

```md
## 変更内容
- Refs #番号

## 確認方法
-

## まだ残ること・相談したいこと
- なし
```

### 5. 取り込み後

`dev` に PR が取り込まれたら、自分のローカルも最新にします。

```bash
git switch dev
git pull origin dev
```

## よくあるエラー

### `error: remote origin already exists.`

`origin` はすでに登録されています。追加し直さず、URLを確認します。

```bash
git remote -v
```

URLが違う場合だけ、次のように変更します。

```bash
git remote set-url origin git@github.com:sisicity4/SHUNKAN.git
```

### `fatal: couldn't find remote ref main`

リモート側に `main` ブランチがない、または普段使う統合ブランチが `dev` の可能性があります。まず一覧を確認します。

```bash
git branch -r
git ls-remote --heads origin
```

このプロジェクトでは、通常作業は `dev` を最新にしてから進めます。

```bash
git switch dev
git pull origin dev
```

### `git remote pull` と打ってしまった

`git remote` はリモート設定を管理するコマンドです。取り込みには `git pull` を使います。

```bash
git pull origin dev
```

## コンフリクトが出たら

コンフリクトは、同じ場所を複数人が変更した印です。焦って「全部受け入れる」を選ばず、次を行います。

1. PR 画面またはチャットで、同じファイルを触った人に連絡する。
2. どちらの変更を残すか相談する。
3. 解決後は対象画面をもう一度確認する。

自信がないときは、解決せずにリーダーへ相談して大丈夫です。

## `main` へ出す前の確認（管理者用）

- `dev` 上で Must 機能が一連で動く。
- 未解決の重大な不具合がない。
- 発表で使う画面と文言を確認した。
- `dev` から `main` への PR を作り、変更内容を確認した。

`main` に取り込んだ後、管理者はリリース・提出に使う版としてタグやデプロイを管理します。
