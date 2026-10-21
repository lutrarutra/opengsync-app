"""Unit tests for the chat assistant: code tools, rendering, history compaction, SSE heartbeat."""
import asyncio
from pathlib import Path

import pytest
from pydantic_ai import ModelRequest, ModelResponse, ModelRetry, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart

from server.chat import render_markdown
from server.chat.store import compact_history
from server.chat.tools import code
from server.routes.htmx.chat import _with_heartbeat


# ── code tools ─────────────────────────────────────────────────────


@pytest.fixture
def roots(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    """Fake allowlisted roots, including files that must never be exposed."""
    server = tmp_path / "server"
    (server / "routes").mkdir(parents=True)
    (server / "routes" / "requests.py").write_text("def submit_request():\n    return 'submitted'\n")
    (server / "big.py").write_text("\n".join(f"line_{i}" for i in range(1, 1001)))
    (server / ".env").write_text("SECRET_KEY=hidden\n")
    (server / "settings.yaml").write_text("password: hidden\n")
    (server / "__pycache__").mkdir()
    (server / "__pycache__" / "requests.py").write_text("cached = True\n")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("PASSWORD = 'hunter2'\n")
    (server / "link.py").symlink_to(outside / "secret.py")
    (server / "linkdir").symlink_to(outside)
    (server / "alias.py").symlink_to(server / ".env")  # innocent name, hidden target inside the root

    docs = tmp_path / "docs"
    (docs / "plans").mkdir(parents=True)
    (docs / "feature.md").write_text("# Feature\nShare links expire after two weeks.\n")
    (docs / "plans" / "idea.md").write_text("# Plan\nShare links will get passwords.\n")

    # a data folder (e.g. uploads) misconfigured to live inside a root
    (server / "uploads").mkdir()
    (server / "uploads" / "upload.txt").write_text("PATIENT_ID = 1234\n")

    fake = {"server": server.resolve(), "docs": docs.resolve()}
    monkeypatch.setattr(code, "_roots", lambda: fake)
    monkeypatch.setattr(code, "_data_dirs", lambda: ((server / "uploads").resolve(),))
    return fake


def test_list_roots(roots):
    listing = code.list_dir()
    assert "server/" in listing and "docs/" in listing


def test_list_dir_hides_sensitive_entries(roots):
    listing = code.list_dir("server").splitlines()
    assert "routes/" in listing
    assert "big.py" in listing
    for hidden in (".env", "settings.yaml", "__pycache__/", "link.py", "linkdir/", "uploads/"):
        assert hidden not in listing


@pytest.mark.parametrize("path", [
    "server/../outside/secret.py",
    "/etc/passwd",
    "etc/passwd",
    "outside/secret.py",
    "server/link.py",
    "server/.env",
    "server/settings.yaml",
    "server/__pycache__/requests.py",
    "docs/plans/idea.md",
    "server/uploads/upload.txt",
    "media/file.txt",
    "uploads/upload.txt",
    "/app_data/fs_index/fs_index.sqlite3",
])
def test_read_file_refuses(roots, path):
    with pytest.raises(ModelRetry):
        code.read_file(path)


@pytest.mark.parametrize("path", ["server/linkdir", "docs/plans", "server/..", "server/uploads", "/media"])
def test_list_dir_refuses(roots, path):
    with pytest.raises(ModelRetry):
        code.list_dir(path)


def test_read_file_with_line_numbers(roots):
    out = code.read_file("server/routes/requests.py")
    assert out.startswith("server/routes/requests.py (lines 1-2 of 2)")
    assert "    1  def submit_request():" in out


def test_read_file_is_capped(roots):
    out = code.read_file("server/big.py", start_line=10, end_line=5000)
    assert f"(lines 10-{10 + code.MAX_READ_LINES - 1} of 1000)" in out
    assert "file continues" in out


def test_grep_finds_code(roots):
    assert code.grep_code("def submit_") == "server/routes/requests.py:1: def submit_request():"


def test_grep_skips_symlinks_and_hidden_files(roots):
    assert code.grep_code("PASSWORD|SECRET_KEY|cached|PATIENT_ID") == "No matches."


def test_grep_docs_is_flat(roots):
    out = code.grep_code("share links")
    assert "docs/feature.md" in out
    assert "plans" not in out


def test_grep_invalid_pattern(roots):
    with pytest.raises(ModelRetry, match="Invalid regular expression"):
        code.grep_code("(unclosed")


def test_grep_time_budget(roots, monkeypatch):
    monkeypatch.setattr(code, "GREP_TIMEOUT_SECONDS", 0.0)
    with pytest.raises(ModelRetry, match="took too long"):
        code.grep_code("line_")


# ── rendering ──────────────────────────────────────────────────────


def test_render_escapes_raw_html():
    html = str(render_markdown("Hi <script>alert(1)</script> **bold**"))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<strong>bold</strong>" in html


def test_render_drops_unsafe_urls():
    html = str(render_markdown("[a](javascript:alert(1)) [b](data:text/html,x) [c](/projects/1) [d](https://x.org)"))
    assert "javascript:" not in html and "data:" not in html
    assert 'href="/projects/1"' in html
    assert 'href="https://x.org"' in html and 'target="_blank"' in html


# ── history compaction ─────────────────────────────────────────────


def _turn(question: str, answer: str, tool_calls: int = 0) -> list:
    messages: list = [ModelRequest(parts=[UserPromptPart(content=question)])]
    for i in range(tool_calls):
        messages.append(ModelResponse(parts=[ToolCallPart(tool_name="read_file", args={"path": "x"}, tool_call_id=f"c{i}")]))
        messages.append(ModelRequest(parts=[ToolReturnPart(tool_name="read_file", content="x" * 1000, tool_call_id=f"c{i}")]))
    messages.append(ModelResponse(parts=[TextPart(content=answer)]))
    return messages


def _kinds(messages: list) -> list[str]:
    return [type(p).__name__ for m in messages for p in m.parts]


def test_compaction_keeps_latest_turn_complete():
    history = _turn("q1", "a1", tool_calls=2) + _turn("q2", "a2", tool_calls=2)
    compacted = compact_history(history, max_turns=5)
    assert _kinds(compacted) == [
        "UserPromptPart", "TextPart",  # q1, compacted
        "UserPromptPart", "ToolCallPart", "ToolReturnPart", "ToolCallPart", "ToolReturnPart", "TextPart",  # q2
    ]


def test_compaction_limits_turns():
    history = [m for i in range(6) for m in _turn(f"q{i}", f"a{i}")]
    compacted = compact_history(history, max_turns=3)
    prompts = [p.content for m in compacted for p in m.parts if isinstance(p, UserPromptPart)]
    assert prompts == ["q3", "q4", "q5"]


def test_compaction_keeps_a_long_latest_turn():
    history = _turn("q1", "a1") + _turn("q2", "a2", tool_calls=40)
    compacted = compact_history(history, max_turns=1)
    assert len(compacted) == 82  # the whole latest turn, nothing dropped


# ── SSE heartbeat ──────────────────────────────────────────────────


def test_heartbeat_does_not_lose_items():
    async def slow():
        for delay in (0.05, 0.35, 0.05):
            await asyncio.sleep(delay)
            yield delay

    async def collect():
        return [item async for item in _with_heartbeat(slow(), interval=0.1)]

    items = asyncio.run(collect())
    assert [i for i in items if i is not None] == [0.05, 0.35, 0.05]
    assert items.count(None) >= 2  # heartbeats while waiting for the slow item
