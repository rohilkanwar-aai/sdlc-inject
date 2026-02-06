"""Web search for finding related real-world incidents."""

import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SearchResult:
    """A single search result for an incident."""

    url: str
    title: str
    snippet: str
    source_type: str | None = None
    company: str | None = None
    year: int | None = None


class IncidentSearcher:
    """Searches for real-world incidents related to failure patterns."""

    # Known engineering blog domains and their companies
    KNOWN_DOMAINS = {
        "aws.amazon.com": ("AWS", "postmortem"),
        "engineering.fb.com": ("Meta", "blog"),
        "netflixtechblog.com": ("Netflix", "blog"),
        "eng.uber.com": ("Uber", "blog"),
        "engineering.linkedin.com": ("LinkedIn", "blog"),
        "blog.cloudflare.com": ("Cloudflare", "blog"),
        "github.blog": ("GitHub", "blog"),
        "stripe.com/blog": ("Stripe", "blog"),
        "dropbox.tech": ("Dropbox", "blog"),
        "slack.engineering": ("Slack", "blog"),
        "medium.com/airbnb-engineering": ("Airbnb", "blog"),
        "discord.com/blog": ("Discord", "blog"),
        "blog.twitter.com/engineering": ("Twitter", "blog"),
        "engineering.atspotify.com": ("Spotify", "blog"),
        "about.gitlab.com/blog": ("GitLab", "blog"),
        "status.": ("", "postmortem"),  # Generic status pages
        "postmortem": ("", "postmortem"),
        "incident-report": ("", "postmortem"),
    }

    # Search query templates for different pattern types
    QUERY_TEMPLATES = {
        "race": [
            '"{name}" race condition postmortem',
            '"{category}" distributed race condition incident',
            "concurrent {subcategory} bug production outage",
        ],
        "split-brain": [
            "split brain {name} postmortem",
            "network partition {category} incident",
            "distributed system partition failure case study",
        ],
        "clock-skew": [
            "clock skew {name} incident",
            "time synchronization bug production",
            "NTP drift outage {category}",
        ],
        "coordination": [
            "distributed lock {name} failure",
            "{category} consensus failure postmortem",
            "coordination bug {subcategory} incident",
        ],
    }

    def __init__(self, api_key: str | None = None):
        """Initialize the searcher with optional API key for search services."""
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)

    def search_for_pattern(
        self,
        pattern_id: str,
        name: str,
        category: str,
        subcategory: str,
        description: str,
        max_results: int = 5,
    ) -> list[SearchResult]:
        """
        Search for incidents related to a specific pattern.

        Args:
            pattern_id: Pattern identifier (e.g., "RACE-001")
            name: Pattern name
            category: Pattern category
            subcategory: Pattern subcategory
            description: Pattern description
            max_results: Maximum number of results to return

        Returns:
            List of SearchResult objects
        """
        results: list[SearchResult] = []

        # Determine pattern type from ID
        pattern_type = self._get_pattern_type(pattern_id)

        # Generate search queries
        queries = self._generate_queries(pattern_type, name, category, subcategory)

        # Search using available methods
        for query in queries[:3]:  # Limit to 3 queries
            try:
                batch_results = self._search_web(query, max_results=max_results)
                results.extend(batch_results)
            except Exception:
                continue

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_results: list[SearchResult] = []
        for result in results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)

        return unique_results[:max_results]

    def _get_pattern_type(self, pattern_id: str) -> str:
        """Extract pattern type from ID (e.g., 'RACE-001' -> 'race')."""
        prefix = pattern_id.split("-")[0].lower()
        type_mapping = {
            "race": "race",
            "split": "split-brain",
            "clock": "clock-skew",
            "coord": "coordination",
        }
        return type_mapping.get(prefix, "race")

    def _generate_queries(
        self, pattern_type: str, name: str, category: str, subcategory: str
    ) -> list[str]:
        """Generate search queries for the pattern."""
        templates = self.QUERY_TEMPLATES.get(pattern_type, self.QUERY_TEMPLATES["race"])
        queries = []
        for template in templates:
            query = template.format(
                name=name, category=category, subcategory=subcategory
            )
            queries.append(query)
        return queries

    def _search_web(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """
        Perform web search using available search APIs.

        This is a placeholder that should be extended to use actual search APIs
        like Exa, Google Custom Search, or Bing Search.
        """
        # For now, return curated results from known incident databases
        return self._search_curated_sources(query, max_results)

    def _search_curated_sources(
        self, query: str, max_results: int
    ) -> list[SearchResult]:
        """Search through curated incident sources."""
        # Known incident URLs categorized by pattern type
        curated_incidents: dict[str, list[dict[str, Any]]] = {
            "race": [
                {
                    "url": "https://aws.amazon.com/message/11201/",
                    "title": "Summary of the Amazon S3 Service Disruption",
                    "snippet": "Race condition in index subsystem caused cascading failures",
                    "company": "AWS",
                    "year": 2017,
                    "source_type": "postmortem",
                },
                {
                    "url": "https://github.blog/2021-03-12-how-we-found-and-fixed-a-race-condition-in-git/",
                    "title": "How we found and fixed a race condition in Git",
                    "snippet": "Race condition in Git's object store during concurrent operations",
                    "company": "GitHub",
                    "year": 2021,
                    "source_type": "blog",
                },
                {
                    "url": "https://blog.cloudflare.com/cloudflare-outage-on-july-17-2020/",
                    "title": "Cloudflare outage on July 17, 2020",
                    "snippet": "Configuration deployment race caused global outage",
                    "company": "Cloudflare",
                    "year": 2020,
                    "source_type": "postmortem",
                },
            ],
            "split-brain": [
                {
                    "url": "https://about.gitlab.com/blog/2017/02/01/gitlab-dot-com-database-incident/",
                    "title": "GitLab.com Database Incident",
                    "snippet": "Database replication issues led to data loss",
                    "company": "GitLab",
                    "year": 2017,
                    "source_type": "postmortem",
                },
                {
                    "url": "https://engineering.fb.com/2021/10/05/networking-traffic/outage-details/",
                    "title": "More details about the October 4 outage",
                    "snippet": "BGP configuration caused network partition",
                    "company": "Meta",
                    "year": 2021,
                    "source_type": "postmortem",
                },
            ],
            "clock-skew": [
                {
                    "url": "https://blog.cloudflare.com/how-and-why-the-leap-second-affected-cloudflare-dns/",
                    "title": "How and why the leap second affected Cloudflare DNS",
                    "snippet": "Leap second caused clock drift and service degradation",
                    "company": "Cloudflare",
                    "year": 2017,
                    "source_type": "blog",
                },
            ],
            "coordination": [
                {
                    "url": "https://engineering.linkedin.com/blog/2016/02/eliminating-large-jvm-gc-pauses-caused-by-background-io-traffic",
                    "title": "Eliminating Large JVM GC Pauses",
                    "snippet": "Coordination issues between GC and background I/O",
                    "company": "LinkedIn",
                    "year": 2016,
                    "source_type": "blog",
                },
            ],
        }

        # Determine which category to search
        query_lower = query.lower()
        results: list[SearchResult] = []

        for category, incidents in curated_incidents.items():
            if category in query_lower or any(
                keyword in query_lower
                for keyword in [
                    "race",
                    "split",
                    "partition",
                    "clock",
                    "time",
                    "lock",
                    "coordination",
                ]
            ):
                for incident in incidents[:max_results]:
                    results.append(
                        SearchResult(
                            url=incident["url"],
                            title=incident["title"],
                            snippet=incident["snippet"],
                            source_type=incident.get("source_type"),
                            company=incident.get("company"),
                            year=incident.get("year"),
                        )
                    )

        return results[:max_results]

    def classify_source(self, url: str) -> tuple[str | None, str | None]:
        """
        Classify the source type and company from a URL.

        Returns:
            Tuple of (company, source_type)
        """
        url_lower = url.lower()

        for domain, (company, source_type) in self.KNOWN_DOMAINS.items():
            if domain in url_lower:
                return company if company else None, source_type

        # Try to extract year from URL
        return None, "blog"

    def extract_year(self, url: str, title: str = "", snippet: str = "") -> int | None:
        """Extract year from URL or content."""
        # Try URL first
        year_match = re.search(r"/20(\d{2})/", url)
        if year_match:
            year = 2000 + int(year_match.group(1))
            if 2010 <= year <= 2026:
                return year

        # Try title and snippet
        for text in [title, snippet]:
            year_match = re.search(r"20(\d{2})", text)
            if year_match:
                year = 2000 + int(year_match.group(1))
                if 2010 <= year <= 2026:
                    return year

        return None

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
