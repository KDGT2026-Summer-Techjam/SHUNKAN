# SHUNKAN Docs

SHUNKAN（瞬間）は、「この季節をどれだけ楽しめたか」を、やりたいこと・達成したこと・残り時間から振り返れる Web アプリです。

このフォルダは、TechJam の6人チームが同じ前提で開発を進めるための共通資料です。特に初めてチーム開発をするメンバーでも、作業の始め方と提出方法が分かる内容にしています。

## 資料一覧

### [01-product-vision.md](01-product-vision.md)

プロダクトの目的、利用体験、最初に作る機能を確認する資料です。

### [02-development-guide.md](02-development-guide.md)

Django / HTML・CSS を前提にした開発の進め方を確認する資料です。

### [03-git-workflow.md](03-git-workflow.md)

`dev` 起点のブランチ・PR・レビュー手順を確認する資料です。

### [04-roadmap-and-tasks.md](04-roadmap-and-tasks.md)

8月18日〜28日の全体スケジュールと初回担当タスクを確認する資料です。

### [05-techjam-tokyo2026-requirements.md](05-techjam-tokyo2026-requirements.md)

TechJam TOKYO 2026 の配布資料から確認した要件と運営ルールをまとめた資料です。

### [06-team-availability.md](06-team-availability.md)

チームの稼働時間をGoogleスプレッドシートで更新・確認する手順です。

### [reference/TECHJAM-TOKYO2026.pdf](reference/TECHJAM-TOKYO2026.pdf)

TechJam TOKYO 2026 配布資料の原本です。


## まず読む順番

初めて参加するメンバーは、次の順番で読むと作業に入りやすいです。

1. [01-product-vision.md](01-product-vision.md) で、何を作るかを確認する。
2. [04-roadmap-and-tasks.md](04-roadmap-and-tasks.md) で、自分の担当と期限を確認する。
3. [03-git-workflow.md](03-git-workflow.md) で、ブランチ作成・PR の出し方を確認する。
4. [02-development-guide.md](02-development-guide.md) で、実装前・PR前の確認事項を見る。

## 作業の基本ルール

1. 作業前に `dev` を最新にします。
2. `dev` から自分の作業ブランチを作ります。
3. 作業が終わったら `dev` 宛てに Pull Request を出します。
4. `main` へのマージはリポジトリ管理者だけが行います。

> **中間チェック版（8月21日）** では、カウントダウン・タスク登録・完了切替・進捗変化を一連で見せられる状態を目標にします。**審査発表版（8月28日）** では、Must機能の最終確認、達成一覧、スマホ表示・入力エラーなどの品質確認まで完了させます。
