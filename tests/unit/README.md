# Unit tests

API、service、prompt、UI shellを検査する。外部APIはstub、DB・history・cache・usageは一時保存先を使い、利用者のdataを変更しない。

`test_review_target_provenance.py`はlive/mock対象の分離、`test_review_search_evidence.py`は実検索の0回／実行／不明、`test_review_cache_identity.py`はidentity・metadata・TTLとreview経路の再利用を検査する。Node・実ブラウザを含む実行手順は[../README.md](../README.md)を参照する。
