# src/app

application service と use-case orchestration を置く層です。  
CLI や UI から呼ばれる処理を集約し、入出力の整形と依存境界の橋渡しを担当します。

## Responsibilities
- input の normalize
- use-case 単位の orchestration
- domain / infrastructure / ui 向け payload shaping
- thin CLI / UI から呼ばれる共有処理の集約

## Best Practices
- CLI / UI はここへ処理を寄せ、分岐や validation の重複を避ける
- parse / lookup / render/export が混ざるなら use-case 単位で段階を分ける
- 中間データは dataclass や typed dict で束ねる
- domain 固有の preview / export tool は、template 本体ではなく利用側プロジェクトの `src/app/` に実装する
