from scripts.sync_current_files import parse_version, sync_content


def test_parse_version_handles_multi_digit_segments() -> None:
    assert parse_version("requirements_v10.2.md") == (10, 2)


def test_sync_content_updates_pointer_and_current_version_line() -> None:
    original = (
        "# 要件定義書 Current\n\n"
        "> 現在版は `requirements_v1.0.md`\n\n"
        "## 概要\n"
        "- 要件定義書: v1.0\n"
    )
    updated = sync_content(
        original,
        latest_filename="requirements_v1.2.md",
        version_label="要件定義書",
    )
    assert "> 現在版は `requirements_v1.2.md`" in updated
    assert "- 要件定義書: v1.2" in updated

