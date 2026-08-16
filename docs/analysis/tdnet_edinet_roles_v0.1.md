# TDnet / EDINET 役割分担メモ v0.1

## 結論

- **EDINET API を canonical source とする**
- **TDnet は速報確認と UI 参照導線として扱う**

## 理由

### EDINET

- 構造化された正式 API がある
- 提出書類やメタデータを安定して同期できる
- connector と sync route を持たせる対象として適している

### TDnet

- 適時開示の速報確認先として有用
- 実務では見る価値が高い
- ただし現時点の repo では connector を持たず、手動参照に留める方が安全

## repo での扱い

| source | 役割 | 実装方針 |
|---|---|---|
| EDINET API | 一次情報の canonical source | connector / sync route を持つ |
| TDnet | 速報確認とリンク導線 | 手動参照のみ |
| allowlist IR | 会社公式 IR の確認 | 許可済みドメインのみ参照 |

## 将来 TDnet を正式導入するなら

必要になる整理は次の通りです。

1. canonical fact は EDINET 優先のまま維持する
2. TDnet は `reference pointer` として保存する
3. dedupe key を定義する
- ticker
- 開示日
- 文書タイトル
- source priority
4. UI では EDINET と TDnet の役割差を見せる

## 非対応事項

- TDnet の規約無視スクレイピング
- TDnet と EDINET の内容を無条件で同格保存すること
- broker 連携と同列の自動取得 source にすること
