# Figma・UI参考資料

## 優先するFigma

- TKMonkeyPy案（今回の画面構造・余白・情報設計の基準）
  - https://www.figma.com/design/B8iTl6uDDNZnOHphBjbpEP/%E7%84%A1%E9%A1%8C?node-id=0-1

## 参考案

- cani案
  - https://www.figma.com/design/FVQiaFMDeWSLVMvV117Nxe/SHUNKAN-%E6%97%AC%E9%96%93?node-id=31-153
- sisicity4案
  - https://www.figma.com/design/mOZnuaXwT3uw3ZBcXYzIr3/SHUNKAN-demo?node-id=9-85

## 実装へ採用する方針

Figmaの体験構造を優先しつつ、`pictures/figma-design-comparison-line.png` の結論「体験は踏襲、ビジュアルは再解釈」に従う。

- スマートフォン幅を基準にする。
- 残り時間をRoomホームの主役にし、「今を残す」を最優先操作にする。
- 温かいオフホワイト、深いネイビー、夕暮れを想起するコーラルを共通色とする。
- Room、Task、アルバム、プロフィール、認証画面は共通シェル・共通ナビ・共通フォームで統一する。
- 状態は色だけでなく「開催前」「開催中」「終了済み」「完了」などの文言を併記する。
- 撮影UIは固有の体験を維持し、今回の視覚統一対象から除外する。ただしHTML妥当性と共通ナビの整合性は保つ。
