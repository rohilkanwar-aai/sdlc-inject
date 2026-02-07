"""Base classes for mock MCP servers.

Provides the abstract base class and data structures for building
mock API servers that simulate Sentry, Slack, GitHub, etc.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..models import Pattern
from .rate_limiter import RateLimiter, RateLimitConfig


@dataclass
class Response:
    """HTTP-like response from a mock server."""

    status: int
    body: Any
    headers: dict[str, str] = field(default_factory=dict)

    def is_success(self) -> bool:
        """Check if response indicates success (2xx)."""
        return 200 <= self.status < 300

    def is_error(self) -> bool:
        """Check if response indicates error (4xx or 5xx)."""
        return self.status >= 400

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status,
            "body": self.body,
            "headers": self.headers,
        }


@dataclass
class RequestLog:
    """Log entry for a request to a mock server."""

    timestamp: datetime
    service: str
    endpoint: str
    method: str
    params: dict[str, Any]
    response_status: int
    duration_ms: float
    rate_limited: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "service": self.service,
            "endpoint": self.endpoint,
            "method": self.method,
            "params": self.params,
            "response_status": self.response_status,
            "duration_ms": round(self.duration_ms, 2),
            "rate_limited": self.rate_limited,
        }


class BaseMCPServer(ABC):
    """Abstract base class for mock MCP servers.

    Provides:
    - Deterministic random number generation (seeded)
    - Rate limiting with configurable thresholds
    - Request logging for analytics
    - Mutable state for multi-turn interactions

    Subclasses must implement:
    - get_endpoints(): Return list of supported endpoints
    - handle_request(): Process a request and return response
    - _initialize_data(): Set up initial server state from pattern

    Example:
        class SentryMCPServer(BaseMCPServer):
            def get_endpoints(self) -> list[str]:
                return ["GET /issues", "GET /issues/{id}"]

            def handle_request(self, method: str, endpoint: str, params: dict) -> Response:
                if endpoint == "/issues":
                    return Response(200, self.issues)
                return Response(404, {"error": "Not found"})
    """

    # Service name for logging
    service_name: str = "base"

    def __init__(
        self,
        pattern: Pattern,
        seed: int | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        """Initialize the mock server.

        Args:
            pattern: The failure pattern being simulated
            seed: Random seed for deterministic data generation
            rate_limit_config: Configuration for rate limiting
        """
        self.pattern = pattern
        self.seed = seed
        self.rng = random.Random(seed)
        self.state: dict[str, Any] = {}
        self.request_log: list[RequestLog] = []
        self.rate_limiter = RateLimiter(rate_limit_config or RateLimitConfig())

        # Initialize server data from pattern
        self._initialize_data()

    @abstractmethod
    def get_endpoints(self) -> list[str]:
        """Return list of supported API endpoints.

        Format: "METHOD /path" or "METHOD /path/{param}"

        Example:
            return [
                "GET /issues",
                "GET /issues/{id}",
                "POST /issues/{id}/resolve",
            ]
        """
        pass

    @abstractmethod
    def handle_request(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> Response:
        """Process a request and return a response.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Request parameters (query params, path params, body)

        Returns:
            Response object with status, body, and headers
        """
        pass

    @abstractmethod
    def _initialize_data(self) -> None:
        """Initialize server data from the pattern.

        Called during __init__ to set up initial state based on
        the pattern's observable symptoms, trigger conditions, etc.
        """
        pass

    def make_request(
        self, method: str, endpoint: str, params: dict[str, Any] | None = None
    ) -> Response:
        """Unified entry point for making requests.

        Handles:
        1. Rate limit checking
        2. Request logging
        3. Delegation to handle_request()

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Request parameters

        Returns:
            Response object
        """
        params = params or {}
        start_time = time.time()

        # Check rate limit
        if self.rate_limiter.is_limited():
            duration_ms = (time.time() - start_time) * 1000
            response = Response(
                status=429,
                body={"error": "Rate limit exceeded", "message": "Too many requests"},
                headers={"Retry-After": str(self.rate_limiter.retry_after)},
            )
            self._log_request(
                method, endpoint, params, response, duration_ms, rate_limited=True
            )
            return response

        # Handle the request
        response = self.handle_request(method, endpoint, params)
        duration_ms = (time.time() - start_time) * 1000

        # Log the request
        self._log_request(method, endpoint, params, response, duration_ms)

        return response

    def _log_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any],
        response: Response,
        duration_ms: float,
        rate_limited: bool = False,
    ) -> None:
        """Log a request for analytics."""
        self.request_log.append(
            RequestLog(
                timestamp=datetime.now(),
                service=self.service_name,
                endpoint=endpoint,
                method=method,
                params=params,
                response_status=response.status,
                duration_ms=duration_ms,
                rate_limited=rate_limited,
            )
        )

    def get_logs(self) -> list[RequestLog]:
        """Get all request logs."""
        return self.request_log

    def get_stats(self) -> dict[str, Any]:
        """Get server statistics."""
        return {
            "service": self.service_name,
            "total_requests": len(self.request_log),
            "successful_requests": sum(
                1 for log in self.request_log if 200 <= log.response_status < 300
            ),
            "error_requests": sum(
                1 for log in self.request_log if log.response_status >= 400
            ),
            "rate_limited_requests": sum(
                1 for log in self.request_log if log.rate_limited
            ),
            "rate_limit_stats": self.rate_limiter.get_stats().to_dict(),
        }

    def reset(self) -> None:
        """Reset server state and logs."""
        self.request_log.clear()
        self.rate_limiter.reset()
        self.state.clear()
        self._initialize_data()

    # Helper methods for generating deterministic data

    def _random_id(self, prefix: str = "", length: int = 8) -> str:
        """Generate a deterministic random ID."""
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        id_part = "".join(self.rng.choice(chars) for _ in range(length))
        return f"{prefix}{id_part}" if prefix else id_part

    def _random_timestamp(
        self, start_hours_ago: int = 24, end_hours_ago: int = 0
    ) -> datetime:
        """Generate a random timestamp within a range."""
        now = datetime.now()
        start_seconds = start_hours_ago * 3600
        end_seconds = end_hours_ago * 3600
        offset_seconds = self.rng.randint(end_seconds, start_seconds)
        return datetime.fromtimestamp(now.timestamp() - offset_seconds)

    def _random_choice(self, items: list[Any]) -> Any:
        """Make a deterministic random choice."""
        return self.rng.choice(items)

    def _random_sample(self, items: list[Any], k: int) -> list[Any]:
        """Make a deterministic random sample."""
        k = min(k, len(items))
        return self.rng.sample(items, k)

    def _random_int(self, a: int, b: int) -> int:
        """Generate a deterministic random integer."""
        return self.rng.randint(a, b)

    def _random_float(self, a: float = 0.0, b: float = 1.0) -> float:
        """Generate a deterministic random float."""
        return self.rng.uniform(a, b)
