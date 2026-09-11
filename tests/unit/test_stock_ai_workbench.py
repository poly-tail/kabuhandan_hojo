"""Structural guards for the scoped dashboard workbench (browser QA is separate)."""

from collections import Counter
from html.parser import HTMLParser
import re

from app.api.routes.analysis_ui import _analysis_shell_html
from app.api.routes.ui import _ui_shell_html


class WorkbenchParser(HTMLParser):
    """Keep element ancestry without adding a production or test dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[dict] = []
        self.stack: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = {"tag": tag, "attrs": dict(attrs), "ancestors": self.stack.copy()}
        self.nodes.append(node)
        void_tags = {
            "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr",
        }
        if tag not in void_tags:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def by_id(self, identifier: str) -> dict:
        matches = [node for node in self.nodes if node["attrs"].get("id") == identifier]
        assert len(matches) == 1, identifier
        return matches[0]


def has_class(node: dict, class_name: str) -> bool:
    return class_name in (node["attrs"].get("class") or "").split()


def test_workbench_has_unique_panes_and_controls_inside_main() -> None:
    parser = WorkbenchParser()
    parser.feed(_ui_shell_html(page_mode="top", initial_ticker=None))
    ids = [node["attrs"]["id"] for node in parser.nodes if "id" in node["attrs"]]
    assert all(count == 1 for count in Counter(ids).values())
    for class_name, tag in (
        ("stock-ai-workbench", "div"),
        ("stock-ai-control-pane", "section"),
        ("stock-ai-result-pane", "section"),
    ):
        matches = [node for node in parser.nodes if has_class(node, class_name)]
        assert len(matches) == 1
        assert matches[0]["tag"] == tag
        assert any(parent["tag"] == "main" for parent in matches[0]["ancestors"])

    primary = (
        "stock-ai-mode", "stock-ai-target", "stock-ai-tickers",
        "stock-ai-position-intent", "stock-ai-user-hypothesis", "portfolio-ai-web-search",
    )
    advanced = (
        "stock-ai-max-web-search", "portfolio-ai-mock-response", "stock-ai-save-result",
        "stock-ai-use-cache", "stock-ai-usage", "stock-ai-copy-prompt", "stock-ai-prompt-output",
    )
    for identifier in primary + advanced:
        node = parser.by_id(identifier)
        assert any(has_class(parent, "stock-ai-control-pane") for parent in node["ancestors"])
        in_details = any(
            parent["attrs"].get("id") == "stock-ai-details" for parent in node["ancestors"]
        )
        assert in_details == (identifier in advanced)
    for identifier in (
        "portfolio-ai-review-feedback", "portfolio-ai-review-reader-link", "portfolio-ai-review-results",
    ):
        assert any(
            has_class(parent, "stock-ai-result-pane") for parent in parser.by_id(identifier)["ancestors"]
        )
    assert "hidden" in parser.by_id("stock-ai-prompt-output")["attrs"]
    assert "open" not in parser.by_id("stock-ai-details")["attrs"]


def test_four_mode_buttons_remain_visible_and_prompt_operations_are_in_details() -> None:
    parser = WorkbenchParser()
    parser.feed(_ui_shell_html(page_mode="top", initial_ticker=None))
    buttons = [node for node in parser.nodes if "data-stock-ai-run" in node["attrs"]]
    assert Counter(node["attrs"]["data-stock-ai-run"] for node in buttons) == {
        "scanner": 1, "analyst": 1, "judge": 1, "critical": 1, "prompt_only": 1,
    }
    for button in buttons:
        inside_details = any(parent["tag"] == "details" for parent in button["ancestors"])
        assert inside_details == (button["attrs"]["data-stock-ai-run"] == "prompt_only")
    assert parser.by_id("stock-ai-mode")["tag"] == "select"
    reader = parser.by_id("portfolio-ai-review-reader-link")["attrs"]
    assert reader["target"] == "_blank"
    assert reader["rel"] == "noopener noreferrer"


def test_new_css_is_dashboard_scoped_with_mobile_and_keyboard_guards() -> None:
    html = _ui_shell_html(page_mode="top", initial_ticker=None)
    block = html.split("/* Dashboard theme and AI workbench;", 1)[1].split(
        "/* End dashboard AI workbench. */", 1
    )[0]
    block = block.split("*/", 1)[1]
    for selector in re.findall(r"([^{}]+)\{", block):
        selector = selector.strip()
        if selector.startswith("@media"):
            continue
        assert selector.startswith(".page-top"), selector
    assert "grid-template-columns: 400px minmax(0, 1fr)" in block
    assert "@media (max-width: 960px)" in block
    assert "grid-template-columns: minmax(0, 1fr)" in block
    assert ":focus-visible" in block
    assert "min-width: 0" in block
    assert "overflow-wrap: anywhere" in block
    assert ".prompt-output[hidden] { display: none; }" in block
    assert "stock-ai-workbench" not in _analysis_shell_html()
