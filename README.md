Aチームのアプリ、旬間のレポジトリ。

# 旬間 (SHUNKAN)

TechJam 用の Django 製、個人利用の夏タスク・SHUNKAN-logアプリです。SHUNKAN-log は、旬の出来事や気持ちを残す短い記録の名称です。

夏の終わりまでを秒単位で数えながら、やりたいことと「今しかない」出来事を残します。短い時間でも次にやることが分かり、夏を楽しめた実感につながることを目指します。

## MVPでできること

- 2026年8月31日23:59:59までの残り日・時・分・秒を確認する
- タイトル・カテゴリ・期限を付けて夏タスクを登録する
- タスクを完了にし、未完了・完了と進捗率を確認する
- 旬の出来事や気持ちをSHUNKAN-logに残し、写真を添える
- 夏のアルバムで完了タスクとSHUNKAN-logを振り返る

> MVPは個人利用です。SHUNKAN-logには写真を最大3枚添付できます。共有・公開、SNS連携、通知、動画アップロードはMVPの対象外です。詳細は [要件定義](docs/07-要件定義.md) を確認してください。

## チーム開発

開発方針・GitHub運用・ロードマップは [docs/README.md](docs/README.md) にまとめています。初めて参加するメンバーは、次の順番で確認してください。

1. [プロダクトビジョン](docs/01-プロダクトビジョン.md)
2. [要件定義](docs/07-要件定義.md)
3. [ロードマップとタスク](docs/04-ロードマップとタスク.md)
4. [GitHub運用手順](docs/03-GitHub運用手順.md)
5. [開発ガイド](docs/02-開発ガイド.md)

## 開発環境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

ブラウザで `http://127.0.0.1:8000/` を開き、トップページが表示されることを確認します。

## デザイン資料

画面イメージは [pictures/](pictures/) にあります。これらはチームで共有する参考資料です。

## リポジトリ構成

```text
.
├── core/               # トップページなどのアプリ本体
├── docs/               # 企画、開発、運用に関する共通資料
├── pictures/           # 共有する画面・デザインの参考画像
├── shunkan_project/    # Djangoプロジェクト設定
├── manage.py
└── requirements.txt
```
