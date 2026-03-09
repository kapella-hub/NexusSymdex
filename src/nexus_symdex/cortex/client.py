"""Async HTTP client wrapper for NexusCortex Memory-as-a-Service."""

import atexit
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


_DISABLED_RESPONSE = {
    "status": "disabled",
    "message": "NexusCortex not configured",
}


class CortexClient:
    """Thin async client for the NexusCortex REST API.

    Reads ``NEXUS_CORTEX_URL`` from the environment.  When the variable is
    empty or unset every method returns a *disabled* status dict instead of
    raising — callers never need to guard against import or connection errors.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url = (base_url or os.environ.get("NEXUS_CORTEX_URL", "")).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_available(self) -> bool:
        """Return True when a NexusCortex URL is configured."""
        return bool(self._base_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create the httpx async client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
        return self._client

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a POST request and return the JSON response or an error dict."""
        if not self.is_available:
            return dict(_DISABLED_RESPONSE)
        try:
            client = self._get_client()
            resp = await client.post(path, json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"error": f"NexusCortex request failed: {exc}"}

    async def _get(self, path: str) -> dict[str, Any]:
        """Send a GET request and return the JSON response or an error dict."""
        if not self.is_available:
            return dict(_DISABLED_RESPONSE)
        try:
            client = self._get_client()
            resp = await client.get(path)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"error": f"NexusCortex request failed: {exc}"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def learn(
        self,
        action: str,
        outcome: str,
        resolution: Optional[str] = None,
        tags: Optional[list[str]] = None,
        domain: str = "",
    ) -> dict[str, Any]:
        """Store a learning in NexusCortex.

        Args:
            action: Description of what happened.
            outcome: Result or summary of the action.
            resolution: Optional resolution or fix applied.
            tags: Categorisation tags.
            domain: Domain identifier (typically the repo name).
        """
        return await self._post("/memory/learn", {
            "action": action,
            "outcome": outcome,
            "resolution": resolution,
            "tags": tags or [],
            "domain": domain,
        })

    async def recall(
        self,
        task: str,
        tags: Optional[list[str]] = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Recall relevant memories for a given task.

        Args:
            task: Description of the current task or query.
            tags: Optional tags to filter results.
            top_k: Maximum number of memories to return.
        """
        return await self._post("/memory/recall", {
            "task": task,
            "tags": tags or [],
            "top_k": top_k,
        })

    async def stream(
        self,
        source: str,
        payload: dict[str, Any],
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Stream an event payload into NexusCortex for background processing.

        Args:
            source: Event source identifier.
            payload: Arbitrary data payload.
            tags: Optional categorisation tags.
        """
        return await self._post("/memory/stream", {
            "source": source,
            "payload": payload,
            "tags": tags or [],
        })

    async def health(self) -> dict[str, Any]:
        """Check NexusCortex service health."""
        return await self._get("/health")

    async def close(self) -> None:
        """Close the underlying HTTP client if open."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# Shared singleton with lazy initialization
# ---------------------------------------------------------------------------
_shared_client: Optional["CortexClient"] = None


def get_cortex_client() -> "CortexClient":
    """Return a shared CortexClient, creating it on first call.

    Reads ``NEXUS_CORTEX_URL`` at call time (not import time), so env
    changes between import and first use are picked up.
    """
    global _shared_client
    if _shared_client is None:
        _shared_client = CortexClient()

        # Best-effort cleanup on interpreter shutdown
        def _cleanup():
            if _shared_client and _shared_client._client is not None:
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(_shared_client.close())
                    else:
                        loop.run_until_complete(_shared_client.close())
                except Exception:
                    pass

        atexit.register(_cleanup)
    return _shared_client
