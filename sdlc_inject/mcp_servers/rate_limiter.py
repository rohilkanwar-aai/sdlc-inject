"""Rate limiting for MCP servers.

Implements token bucket with burst protection and exponential backoff
for rate limit violations.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting behavior."""

    requests_per_minute: int = 30
    burst_limit: int = 5  # Max requests in 5 second window
    penalty_multiplier: float = 2.0  # Exponential backoff multiplier
    initial_retry_after: int = 2  # Base retry-after seconds


@dataclass
class RateLimitStats:
    """Statistics about rate limiting."""

    total_requests: int = 0
    limited_requests: int = 0
    violations: int = 0
    peak_requests_per_minute: int = 0

    @property
    def limit_rate(self) -> float:
        """Percentage of requests that were rate limited."""
        if self.total_requests == 0:
            return 0.0
        return self.limited_requests / self.total_requests * 100

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "total_requests": self.total_requests,
            "limited_requests": self.limited_requests,
            "violations": self.violations,
            "peak_requests_per_minute": self.peak_requests_per_minute,
            "limit_rate_percent": round(self.limit_rate, 2),
        }


class RateLimiter:
    """Token bucket rate limiter with burst protection.

    Tracks requests over a sliding window and enforces:
    1. Per-minute rate limit
    2. Burst limit (requests in short window)
    3. Exponential backoff on violations

    Example:
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=30))

        if limiter.is_limited():
            return Response(429, headers={"Retry-After": str(limiter.retry_after)})

        # Process request...
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self.request_times: deque[datetime] = deque()
        self.violations: int = 0
        self.stats = RateLimitStats()

    def _cleanup_old_requests(self, now: datetime) -> None:
        """Remove requests older than 1 minute from tracking."""
        cutoff = now - timedelta(minutes=1)
        while self.request_times and self.request_times[0] < cutoff:
            self.request_times.popleft()

    def _count_burst(self, now: datetime) -> int:
        """Count requests in the last 5 seconds."""
        cutoff = now - timedelta(seconds=5)
        return sum(1 for t in self.request_times if t >= cutoff)

    def is_limited(self) -> bool:
        """Check if the current request should be rate limited.

        Returns:
            True if request should be blocked, False if allowed.
        """
        now = datetime.now()
        self._cleanup_old_requests(now)

        self.stats.total_requests += 1

        # Update peak tracking
        current_rpm = len(self.request_times)
        if current_rpm > self.stats.peak_requests_per_minute:
            self.stats.peak_requests_per_minute = current_rpm

        # Check per-minute limit
        if len(self.request_times) >= self.config.requests_per_minute:
            self.violations += 1
            self.stats.violations += 1
            self.stats.limited_requests += 1
            return True

        # Check burst limit
        burst_count = self._count_burst(now)
        if burst_count >= self.config.burst_limit:
            self.violations += 1
            self.stats.violations += 1
            self.stats.limited_requests += 1
            return True

        # Request allowed, track it
        self.request_times.append(now)
        return False

    @property
    def retry_after(self) -> int:
        """Calculate retry-after seconds with exponential backoff.

        Each violation doubles the wait time from the base.
        """
        base = self.config.initial_retry_after
        multiplier = self.config.penalty_multiplier ** min(self.violations, 10)
        return int(base * multiplier)

    @property
    def requests_remaining(self) -> int:
        """Number of requests remaining in the current minute."""
        self._cleanup_old_requests(datetime.now())
        return max(0, self.config.requests_per_minute - len(self.request_times))

    def reset(self) -> None:
        """Reset the rate limiter state."""
        self.request_times.clear()
        self.violations = 0

    def get_stats(self) -> RateLimitStats:
        """Get current rate limiting statistics."""
        return self.stats
