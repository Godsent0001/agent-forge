"""Domain-neutral capability registry for tool-backed agent work.

Concrete image/video/security/code/document adapters plug into this registry. The core
only executes registered capabilities, checks declared permissions and prerequisites,
and returns structured outcomes suitable for verification and artifact persistence.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    domain: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    permissions: frozenset[str] = frozenset()
    required_binaries: tuple[str, ...] = ()
    required_environment: tuple[str, ...] = ()
    idempotent: bool = False
    timeout_seconds: float = 120.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityResult:
    capability: str
    ok: bool
    content: str
    artifacts: tuple[Mapping[str, Any], ...] = ()
    retryable: bool = False
    duration_ms: int = 0
    error_code: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class CapabilityAdapter(Protocol):
    async def execute(self, arguments: Mapping[str, Any], context: Any) -> CapabilityResult: ...


class CapabilityError(RuntimeError):
    pass


class CapabilityDenied(CapabilityError):
    pass


class CapabilityUnavailable(CapabilityError):
    pass


PermissionPolicy = Callable[[CapabilitySpec, Mapping[str, Any], Any], bool | Awaitable[bool]]


class CapabilityRegistry:
    """Explicit registration, deterministic discovery, preflight, permission checks and timeout."""

    def __init__(self, permission_policy: PermissionPolicy | None = None):
        self._items: dict[str, tuple[CapabilitySpec, CapabilityAdapter]] = {}
        self._policy = permission_policy

    def register(self, spec: CapabilitySpec, adapter: CapabilityAdapter) -> None:
        key = spec.name.strip().casefold()
        if not key or not spec.domain.strip() or not spec.description.strip():
            raise ValueError("Capability name, domain, and description must be non-empty")
        if key in self._items:
            raise ValueError(f"Capability {spec.name!r} is already registered")
        if spec.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not callable(getattr(adapter, "execute", None)):
            raise TypeError("Capability adapter must provide execute(arguments, context)")
        self._items[key] = (spec, adapter)

    def list(self, *, domain: str | None = None, available_only: bool = False) -> list[CapabilitySpec]:
        result = []
        for spec, _ in self._items.values():
            if domain and spec.domain.casefold() != domain.casefold():
                continue
            if available_only and self.preflight(spec.name):
                continue
            result.append(spec)
        return sorted(result, key=lambda item: (item.domain.casefold(), item.name.casefold()))

    def get(self, name: str) -> CapabilitySpec | None:
        entry = self._items.get(name.strip().casefold())
        return entry[0] if entry else None

    def preflight(self, name: str) -> list[str]:
        spec = self.get(name)
        if spec is None:
            return [f"Unknown capability: {name}"]
        issues = []
        for binary in spec.required_binaries:
            if shutil.which(binary) is None:
                issues.append(f"Required executable is not available: {binary}")
        for variable in spec.required_environment:
            if not os.environ.get(variable):
                issues.append(f"Required environment variable is not configured: {variable}")
        return issues

    async def execute(
        self, name: str, arguments: Mapping[str, Any], context: Any = None, *,
        timeout_seconds: float | None = None,
    ) -> CapabilityResult:
        entry = self._items.get(name.strip().casefold())
        if entry is None:
            raise CapabilityUnavailable(f"Capability {name!r} is not registered")
        spec, adapter = entry
        missing = self.preflight(name)
        if missing:
            raise CapabilityUnavailable("; ".join(missing))
        if self._policy:
            allowed = self._policy(spec, arguments, context)
            if inspect.isawaitable(allowed):
                allowed = await allowed
            if not allowed:
                raise CapabilityDenied(f"Permission policy denied capability {spec.name!r}")
        timeout = min(spec.timeout_seconds, timeout_seconds) if timeout_seconds is not None else spec.timeout_seconds
        if timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout):
                result = await adapter.execute(arguments, context)
        except TimeoutError as exc:
            raise CapabilityUnavailable(f"Capability {spec.name!r} timed out after {timeout:g}s") from exc
        if not isinstance(result, CapabilityResult):
            raise TypeError("Capability adapter must return CapabilityResult")
        # Normalize the externally visible name and runtime duration; do not infer success.
        return CapabilityResult(
            capability=spec.name, ok=result.ok, content=result.content,
            artifacts=tuple(result.artifacts), retryable=bool(result.retryable and spec.idempotent),
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            error_code=result.error_code, metadata=dict(result.metadata),
        )
