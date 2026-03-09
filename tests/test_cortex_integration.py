"""Tests for NexusCortex integration tools."""
import pytest
from unittest.mock import patch


class TestCortexClient:
    """Test CortexClient behavior."""

    def test_disabled_when_no_url(self):
        """Client is disabled when NEXUS_CORTEX_URL is not set."""
        with patch.dict("os.environ", {"NEXUS_CORTEX_URL": ""}):
            from nexus_symdex.cortex.client import CortexClient
            client = CortexClient()
            assert not client.is_available

    def test_enabled_when_url_set(self):
        """Client is enabled when NEXUS_CORTEX_URL is set."""
        with patch.dict("os.environ", {"NEXUS_CORTEX_URL": "http://localhost:8000"}):
            from nexus_symdex.cortex.client import CortexClient
            client = CortexClient()
            assert client.is_available

    async def test_learn_returns_disabled_when_no_url(self):
        """learn() returns disabled status when cortex not configured."""
        with patch.dict("os.environ", {"NEXUS_CORTEX_URL": ""}):
            from nexus_symdex.cortex.client import CortexClient
            client = CortexClient()
            result = await client.learn("test action", "test outcome")
            assert result.get("status") == "disabled"

    async def test_recall_returns_disabled_when_no_url(self):
        """recall() returns disabled status when cortex not configured."""
        with patch.dict("os.environ", {"NEXUS_CORTEX_URL": ""}):
            from nexus_symdex.cortex.client import CortexClient
            client = CortexClient()
            result = await client.recall("test task")
            assert result.get("status") == "disabled"

    async def test_stream_returns_disabled_when_no_url(self):
        """stream() returns disabled status when cortex not configured."""
        with patch.dict("os.environ", {"NEXUS_CORTEX_URL": ""}):
            from nexus_symdex.cortex.client import CortexClient
            client = CortexClient()
            result = await client.stream("test-source", {"key": "value"})
            assert result.get("status") == "disabled"


class TestGetCortexClient:
    """Test the shared singleton factory."""

    def test_returns_same_instance(self):
        """get_cortex_client returns the same instance on repeated calls."""
        import nexus_symdex.cortex.client as mod
        # Reset singleton for test isolation
        mod._shared_client = None
        try:
            a = mod.get_cortex_client()
            b = mod.get_cortex_client()
            assert a is b
        finally:
            mod._shared_client = None

    def test_reads_env_at_call_time(self):
        """Client picks up NEXUS_CORTEX_URL set after import."""
        import nexus_symdex.cortex.client as mod
        mod._shared_client = None
        try:
            with patch.dict("os.environ", {"NEXUS_CORTEX_URL": "http://localhost:9999"}):
                client = mod.get_cortex_client()
                assert client.is_available
                assert "9999" in client._base_url
        finally:
            mod._shared_client = None


class TestLearnFromChanges:
    """Test learn_from_changes tool."""

    async def test_no_changes_returns_early(self, tmp_path):
        """When repo not indexed, returns an error."""
        from nexus_symdex.tools.learn_from_changes import learn_from_changes
        result = await learn_from_changes("nonexistent/repo", storage_path=str(tmp_path))
        assert "error" in result or "no_changes" in result.get("status", "")


class TestRecallWithCode:
    """Test recall_with_code tool."""

    async def test_works_without_cortex(self, tmp_path):
        """Falls back to code-only context when cortex unavailable."""
        from nexus_symdex.parser import parse_file
        from nexus_symdex.storage import IndexStore

        content = 'def authenticate(user, password):\n    return True\n'
        symbols = parse_file(content, "auth.py", "python")
        store = IndexStore(base_path=str(tmp_path))
        store.save_index(
            owner="test", name="test-repo",
            source_files=["auth.py"],
            symbols=symbols,
            raw_files={"auth.py": content},
            languages={"python": 1},
            references=[],
        )

        from nexus_symdex.tools.recall_with_code import recall_with_code
        import nexus_symdex.cortex.client as cortex_mod
        original = cortex_mod._shared_client
        cortex_mod._shared_client = None
        try:
            with patch.dict("os.environ", {"NEXUS_CORTEX_URL": ""}):
                cortex_mod._shared_client = None
                result = await recall_with_code(
                    task="fix authentication",
                    repo="test/test-repo",
                    storage_path=str(tmp_path),
                )
        finally:
            cortex_mod._shared_client = original

        assert "error" not in result
        assert "code_context" in result
        assert result["_meta"]["cortex_available"] is False


class TestReviewWithHistory:
    """Test review_with_history tool."""

    async def test_works_without_cortex(self, tmp_path):
        """Review works even when cortex unavailable (just no history)."""
        from nexus_symdex.parser import parse_file
        from nexus_symdex.storage import IndexStore

        content = 'def handler(req):\n    return "ok"\n'
        symbols = parse_file(content, "app.py", "python")
        store = IndexStore(base_path=str(tmp_path))
        store.save_index(
            owner="test", name="test-repo",
            source_files=["app.py"],
            symbols=symbols,
            raw_files={"app.py": content},
            languages={"python": 1},
            references=[],
        )

        from nexus_symdex.tools.review_with_history import review_with_history
        import nexus_symdex.cortex.client as cortex_mod
        original = cortex_mod._shared_client
        cortex_mod._shared_client = None
        try:
            with patch.dict("os.environ", {"NEXUS_CORTEX_URL": ""}):
                cortex_mod._shared_client = None
                result = await review_with_history(
                    repo="test/test-repo",
                    changed_files=["app.py"],
                    storage_path=str(tmp_path),
                )
        finally:
            cortex_mod._shared_client = original

        assert "error" not in result
        assert "review" in result
        assert result["_meta"]["cortex_available"] is False
