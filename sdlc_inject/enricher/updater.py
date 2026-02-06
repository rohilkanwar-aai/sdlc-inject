"""Update pattern YAML files with enriched incident data."""

import os
from pathlib import Path
from typing import Any

import yaml

from ..models import Pattern, RelatedIncident
from .searcher import IncidentSearcher, SearchResult
from .summarizer import IncidentSummarizer, IncidentSummary


class PatternUpdater:
    """Updates pattern YAML files with enriched incident references."""

    def __init__(
        self,
        patterns_dir: Path | str,
        searcher: IncidentSearcher | None = None,
        summarizer: IncidentSummarizer | None = None,
    ):
        """
        Initialize the pattern updater.

        Args:
            patterns_dir: Directory containing pattern YAML files
            searcher: Optional IncidentSearcher instance
            summarizer: Optional IncidentSummarizer instance
        """
        self.patterns_dir = Path(patterns_dir)
        self.searcher = searcher or IncidentSearcher()
        self.summarizer = summarizer or IncidentSummarizer()

    def enrich_pattern(
        self,
        pattern_id: str,
        dry_run: bool = False,
        max_incidents: int = 3,
    ) -> dict[str, Any]:
        """
        Enrich a single pattern with incident references.

        Args:
            pattern_id: Pattern ID (e.g., "RACE-001")
            dry_run: If True, don't write changes to file
            max_incidents: Maximum number of incidents to add

        Returns:
            Dict with enrichment results
        """
        # Find the pattern file
        pattern_file = self._find_pattern_file(pattern_id)
        if not pattern_file:
            return {"error": f"Pattern {pattern_id} not found"}

        # Load the pattern
        with open(pattern_file) as f:
            pattern_data = yaml.safe_load(f)

        # Parse with model for validation
        pattern = Pattern(**pattern_data)

        # Search for related incidents
        search_results = self.searcher.search_for_pattern(
            pattern_id=pattern.id,
            name=pattern.name,
            category=pattern.category,
            subcategory=pattern.subcategory,
            description=pattern.description,
            max_results=max_incidents,
        )

        # Summarize each incident
        enriched_incidents: list[dict[str, Any]] = []
        pattern_type = self._get_pattern_type(pattern_id)

        for result in search_results:
            summary = self.summarizer.summarize_incident(
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                pattern_type=pattern_type,
            )

            if summary:
                incident_data = self._build_incident_data(result, summary)
                enriched_incidents.append(incident_data)

        # Merge with existing incidents (avoid duplicates)
        existing_urls = {
            inc.get("url") for inc in pattern_data.get("related_incidents", [])
        }
        new_incidents = [
            inc for inc in enriched_incidents if inc["url"] not in existing_urls
        ]

        # Update the pattern data
        if "related_incidents" not in pattern_data:
            pattern_data["related_incidents"] = []

        pattern_data["related_incidents"].extend(new_incidents)

        result = {
            "pattern_id": pattern_id,
            "pattern_file": str(pattern_file),
            "existing_incidents": len(existing_urls),
            "new_incidents": len(new_incidents),
            "total_incidents": len(pattern_data["related_incidents"]),
            "incidents_added": new_incidents,
        }

        if not dry_run and new_incidents:
            self._write_pattern(pattern_file, pattern_data)
            result["written"] = True
        else:
            result["written"] = False

        return result

    def enrich_all(
        self,
        category: str | None = None,
        dry_run: bool = False,
        max_incidents_per_pattern: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Enrich all patterns or patterns in a specific category.

        Args:
            category: Optional category filter (e.g., "race", "split-brain")
            dry_run: If True, don't write changes
            max_incidents_per_pattern: Max incidents per pattern

        Returns:
            List of enrichment results for each pattern
        """
        results = []

        # Find all pattern files
        pattern_files = self._find_all_pattern_files(category)

        for pattern_file in pattern_files:
            pattern_id = self._extract_pattern_id(pattern_file)
            if pattern_id:
                result = self.enrich_pattern(
                    pattern_id=pattern_id,
                    dry_run=dry_run,
                    max_incidents=max_incidents_per_pattern,
                )
                results.append(result)

        return results

    def add_incident(
        self,
        pattern_id: str,
        url: str,
        title: str | None = None,
        relevance: str | None = None,
        summarize: bool = True,
    ) -> dict[str, Any]:
        """
        Add a specific incident URL to a pattern.

        Args:
            pattern_id: Pattern ID
            url: Incident URL to add
            title: Optional title
            relevance: Optional relevance description
            summarize: Whether to generate an LLM summary

        Returns:
            Result dict
        """
        pattern_file = self._find_pattern_file(pattern_id)
        if not pattern_file:
            return {"error": f"Pattern {pattern_id} not found"}

        with open(pattern_file) as f:
            pattern_data = yaml.safe_load(f)

        # Check if URL already exists
        existing_urls = {
            inc.get("url") for inc in pattern_data.get("related_incidents", [])
        }
        if url in existing_urls:
            return {"error": f"URL already exists in pattern {pattern_id}"}

        # Build incident data
        incident_data: dict[str, Any] = {"url": url}

        if title:
            incident_data["title"] = title

        if relevance:
            incident_data["relevance"] = relevance

        # Classify source
        company, source_type = self.searcher.classify_source(url)
        if company:
            incident_data["company"] = company
        if source_type:
            incident_data["source_type"] = source_type

        # Extract year
        year = self.searcher.extract_year(url, title or "")
        if year:
            incident_data["year"] = year

        # Generate summary if requested
        if summarize:
            pattern_type = self._get_pattern_type(pattern_id)
            summary = self.summarizer.summarize_incident(
                url=url,
                title=title or "",
                snippet=relevance or "",
                pattern_type=pattern_type,
            )
            if summary:
                incident_data["engineer_solution_summary"] = summary.solution_summary
                incident_data["tags"] = summary.tags

        # Add to pattern
        if "related_incidents" not in pattern_data:
            pattern_data["related_incidents"] = []

        pattern_data["related_incidents"].append(incident_data)

        # Write back
        self._write_pattern(pattern_file, pattern_data)

        return {
            "pattern_id": pattern_id,
            "incident_added": incident_data,
            "total_incidents": len(pattern_data["related_incidents"]),
        }

    def _find_pattern_file(self, pattern_id: str) -> Path | None:
        """Find the YAML file for a pattern ID."""
        # Pattern ID format: CATEGORY-NNN (e.g., RACE-001, SPLIT-002)
        category_map = {
            "RACE": "race",
            "SPLIT": "split-brain",
            "CLOCK": "clock-skew",
            "COORD": "coordination",
        }

        prefix = pattern_id.split("-")[0]
        category_dir = category_map.get(prefix)

        if category_dir:
            pattern_file = self.patterns_dir / category_dir / f"{pattern_id}.yaml"
            if pattern_file.exists():
                return pattern_file

        # Fallback: search all subdirectories
        for yaml_file in self.patterns_dir.rglob("*.yaml"):
            if yaml_file.stem == pattern_id:
                return yaml_file

        return None

    def _find_all_pattern_files(self, category: str | None = None) -> list[Path]:
        """Find all pattern files, optionally filtered by category."""
        pattern_files = []

        if category:
            category_dir = self.patterns_dir / category
            if category_dir.exists():
                pattern_files = list(category_dir.glob("*.yaml"))
        else:
            pattern_files = list(self.patterns_dir.rglob("*.yaml"))

        return sorted(pattern_files)

    def _extract_pattern_id(self, pattern_file: Path) -> str | None:
        """Extract pattern ID from filename."""
        # Assumes filename is PATTERN-ID.yaml
        stem = pattern_file.stem
        if "-" in stem and stem.split("-")[0].isupper():
            return stem
        return None

    def _get_pattern_type(self, pattern_id: str) -> str:
        """Get pattern type from ID."""
        prefix = pattern_id.split("-")[0].lower()
        type_map = {
            "race": "race",
            "split": "split-brain",
            "clock": "clock-skew",
            "coord": "coordination",
        }
        return type_map.get(prefix, "race")

    def _build_incident_data(
        self, result: SearchResult, summary: IncidentSummary
    ) -> dict[str, Any]:
        """Build incident dict from search result and summary."""
        data: dict[str, Any] = {
            "url": result.url,
            "title": result.title,
            "relevance": result.snippet,
        }

        if result.source_type:
            data["source_type"] = result.source_type
        if result.company:
            data["company"] = result.company
        if result.year:
            data["year"] = result.year

        if summary.solution_summary:
            data["engineer_solution_summary"] = summary.solution_summary
        if summary.tags:
            data["tags"] = summary.tags

        return data

    def _write_pattern(self, pattern_file: Path, pattern_data: dict[str, Any]) -> None:
        """Write pattern data back to YAML file."""

        class FlowStyleDumper(yaml.SafeDumper):
            """Custom dumper to preserve formatting."""

            pass

        def str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        FlowStyleDumper.add_representer(str, str_representer)

        with open(pattern_file, "w") as f:
            yaml.dump(
                pattern_data,
                f,
                Dumper=FlowStyleDumper,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=100,
            )

    def close(self) -> None:
        """Clean up resources."""
        self.searcher.close()
        self.summarizer.close()
