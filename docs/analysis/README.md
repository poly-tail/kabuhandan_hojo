# Analysis Docs

実装の補助メモ、設計メモ、直近 backlog を置くディレクトリです。正式仕様は `docs/requirements/`、`docs/specs/`、`docs/screen_specs/` を参照してください。

## 収録ファイル

- `technical_flow_design_v0.1.md`
  - テクニカル特徴量、需給 snapshot、score breakdown の設計メモ
- `implementation_backlog_v0.1.md`
  - UI 3 画面を入れた直後の初期 backlog
- `implementation_backlog_v0.2.md`
  - no-mock live UI、chart detail 強化、TDnet / EDINET 整理後の backlog
- `tdnet_edinet_roles_v0.1.md`
  - EDINET を canonical source とし、TDnet を参照導線として扱うための設計メモ

## 使い分け

- 仕様を決める: `requirements` / `specs` / `screen_specs`
- 今後の作業順を見る: `implementation_backlog_*`
- source 方針を確認する: `tdnet_edinet_roles_v0.1.md`
- 技術的な設計意図を確認する: `technical_flow_design_v0.1.md`
