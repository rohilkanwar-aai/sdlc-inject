"""Analysis tools for scanning codebases."""

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CodebaseStructure:
    """Structure information about a codebase."""

    root_path: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    architecture_hints: list[str] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0
    has_tests: bool = False
    has_ci: bool = False
    has_docker: bool = False


@dataclass
class ConcurrencyPattern:
    """A detected concurrency pattern in the code."""

    file_path: str
    line_number: int
    pattern_type: str  # "async", "threading", "mutex", "atomic", "channel"
    code_snippet: str
    risk_level: str  # "low", "medium", "high"


@dataclass
class DistributedPattern:
    """A detected distributed system pattern."""

    file_path: str
    line_number: int
    pattern_type: str  # "rpc", "message_queue", "database", "cache", "service_call"
    code_snippet: str
    description: str


@dataclass
class StatePattern:
    """A detected state management pattern."""

    file_path: str
    line_number: int
    pattern_type: str  # "shared_state", "cache", "session", "global_var"
    code_snippet: str
    risk_level: str


@dataclass
class TimeSensitivePattern:
    """A detected time-sensitive pattern."""

    file_path: str
    line_number: int
    pattern_type: str  # "timestamp", "timeout", "ttl", "expiry", "duration"
    code_snippet: str


class AnalysisTools:
    """Tools for analyzing codebases to identify injection targets."""

    # Language detection patterns
    LANGUAGE_FILES = {
        "rust": ["Cargo.toml", "*.rs"],
        "python": ["pyproject.toml", "setup.py", "*.py", "requirements.txt"],
        "javascript": ["package.json", "*.js", "*.jsx"],
        "typescript": ["tsconfig.json", "*.ts", "*.tsx"],
        "go": ["go.mod", "*.go"],
        "java": ["pom.xml", "build.gradle", "*.java"],
        "csharp": ["*.csproj", "*.cs"],
        "ruby": ["Gemfile", "*.rb"],
    }

    # Framework detection patterns
    FRAMEWORK_PATTERNS = {
        "tokio": r"tokio::",
        "actix": r"actix_web|actix::",
        "axum": r"axum::",
        "django": r"from django|import django",
        "flask": r"from flask|import flask",
        "fastapi": r"from fastapi|import fastapi",
        "react": r"from ['\"](react|@react)",
        "nextjs": r"from ['\"](next|@next)",
        "express": r"require\(['\"]express['\"]|from ['\"]express['\"]",
        "spring": r"org\.springframework",
        "rails": r"require ['\"]rails['\"]",
    }

    # Concurrency patterns by language
    CONCURRENCY_PATTERNS = {
        "rust": [
            (r"async fn|\.await", "async"),
            (r"std::thread|thread::spawn", "threading"),
            (r"Mutex|RwLock|Arc<Mutex", "mutex"),
            (r"AtomicU\d+|AtomicBool|AtomicPtr", "atomic"),
            (r"mpsc::|crossbeam::", "channel"),
        ],
        "python": [
            (r"async def|await ", "async"),
            (r"threading\.|Thread\(", "threading"),
            (r"Lock\(\)|RLock\(\)|Semaphore\(", "mutex"),
            (r"multiprocessing\.", "multiprocessing"),
            (r"asyncio\.|aiohttp", "async"),
        ],
        "go": [
            (r"go func|go \w+\(", "goroutine"),
            (r"sync\.Mutex|sync\.RWMutex", "mutex"),
            (r"chan\s+\w+|<-\s*\w+", "channel"),
            (r"sync\.WaitGroup", "sync"),
        ],
        "javascript": [
            (r"async function|await ", "async"),
            (r"new Promise|Promise\.", "promise"),
            (r"Worker\(|SharedArrayBuffer", "threading"),
        ],
        "typescript": [
            (r"async function|await ", "async"),
            (r"new Promise|Promise\.", "promise"),
            (r"Worker\(|SharedArrayBuffer", "threading"),
        ],
    }

    # Distributed system patterns
    DISTRIBUTED_PATTERNS = [
        (r"grpc::|tonic::|protobuf", "rpc", "gRPC calls"),
        (r"reqwest::|hyper::|http::", "http_client", "HTTP client calls"),
        (r"kafka|rdkafka|pulsar", "message_queue", "Message queue"),
        (r"redis::|Redis\(|redis\.", "cache", "Redis cache"),
        (r"sqlx::|diesel::|postgres|mysql|sqlite", "database", "Database operations"),
        (r"etcd|consul|zookeeper", "service_discovery", "Service discovery"),
        (r"rabbitmq|amqp::", "message_queue", "RabbitMQ"),
    ]

    # State management patterns
    STATE_PATTERNS = [
        (r"static mut|lazy_static|once_cell", "global_state", "high"),
        (r"\.cache\(|@cache|@lru_cache", "cache", "medium"),
        (r"session\[|request\.session", "session", "medium"),
        (r"SharedPreferences|localStorage|sessionStorage", "client_storage", "low"),
        (r"\.set\(|\.get\(.*cache", "cache_operation", "medium"),
    ]

    # Time-sensitive patterns
    TIME_PATTERNS = [
        (r"SystemTime|Instant::now|time::now", "timestamp"),
        (r"timeout|Timeout|TIMEOUT", "timeout"),
        (r"ttl|TTL|time_to_live", "ttl"),
        (r"expires?_at|expir(y|ation)", "expiry"),
        (r"Duration::|timedelta|time\.sleep", "duration"),
    ]

    def __init__(self, codebase_path: str | Path):
        """Initialize with path to codebase."""
        self.codebase_path = Path(codebase_path)
        if not self.codebase_path.exists():
            raise ValueError(f"Codebase path does not exist: {codebase_path}")

    def analyze_structure(self) -> CodebaseStructure:
        """Analyze the overall structure of the codebase."""
        structure = CodebaseStructure(root_path=str(self.codebase_path))

        # Detect languages
        structure.languages = self._detect_languages()

        # Detect frameworks
        structure.frameworks = self._detect_frameworks()

        # Count files and lines
        structure.total_files, structure.total_lines = self._count_code()

        # Detect architecture hints
        structure.architecture_hints = self._detect_architecture()

        # Check for common infrastructure
        structure.has_tests = self._has_tests()
        structure.has_ci = self._has_ci()
        structure.has_docker = self._has_docker()

        return structure

    def find_concurrency_patterns(self) -> list[ConcurrencyPattern]:
        """Find concurrency-related patterns in the codebase."""
        patterns: list[ConcurrencyPattern] = []
        structure = self.analyze_structure()

        for language in structure.languages:
            if language in self.CONCURRENCY_PATTERNS:
                for regex, pattern_type in self.CONCURRENCY_PATTERNS[language]:
                    matches = self._search_pattern(regex, self._get_extensions(language))
                    for match in matches:
                        risk = self._assess_concurrency_risk(match["snippet"], pattern_type)
                        patterns.append(
                            ConcurrencyPattern(
                                file_path=match["file"],
                                line_number=match["line"],
                                pattern_type=pattern_type,
                                code_snippet=match["snippet"],
                                risk_level=risk,
                            )
                        )

        return patterns

    def find_distributed_patterns(self) -> list[DistributedPattern]:
        """Find distributed system patterns in the codebase."""
        patterns: list[DistributedPattern] = []

        for regex, pattern_type, description in self.DISTRIBUTED_PATTERNS:
            matches = self._search_pattern(regex)
            for match in matches:
                patterns.append(
                    DistributedPattern(
                        file_path=match["file"],
                        line_number=match["line"],
                        pattern_type=pattern_type,
                        code_snippet=match["snippet"],
                        description=description,
                    )
                )

        return patterns

    def find_state_patterns(self) -> list[StatePattern]:
        """Find state management patterns in the codebase."""
        patterns: list[StatePattern] = []

        for regex, pattern_type, risk in self.STATE_PATTERNS:
            matches = self._search_pattern(regex)
            for match in matches:
                patterns.append(
                    StatePattern(
                        file_path=match["file"],
                        line_number=match["line"],
                        pattern_type=pattern_type,
                        code_snippet=match["snippet"],
                        risk_level=risk,
                    )
                )

        return patterns

    def find_time_sensitive_patterns(self) -> list[TimeSensitivePattern]:
        """Find time-sensitive patterns in the codebase."""
        patterns: list[TimeSensitivePattern] = []

        for regex, pattern_type in self.TIME_PATTERNS:
            matches = self._search_pattern(regex)
            for match in matches:
                patterns.append(
                    TimeSensitivePattern(
                        file_path=match["file"],
                        line_number=match["line"],
                        pattern_type=pattern_type,
                        code_snippet=match["snippet"],
                    )
                )

        return patterns

    def _detect_languages(self) -> list[str]:
        """Detect programming languages used in the codebase."""
        languages = []
        for lang, patterns in self.LANGUAGE_FILES.items():
            for pattern in patterns:
                if pattern.startswith("*."):
                    # Extension pattern
                    ext = pattern[1:]
                    if list(self.codebase_path.rglob(f"*{ext}"))[:1]:
                        languages.append(lang)
                        break
                else:
                    # Specific file
                    if (self.codebase_path / pattern).exists() or list(
                        self.codebase_path.rglob(pattern)
                    )[:1]:
                        languages.append(lang)
                        break
        return languages

    def _detect_frameworks(self) -> list[str]:
        """Detect frameworks used in the codebase."""
        frameworks = []
        # Sample some files to check for framework imports
        for ext in [".rs", ".py", ".js", ".ts", ".go", ".java"]:
            for file_path in list(self.codebase_path.rglob(f"*{ext}"))[:50]:
                try:
                    content = file_path.read_text(errors="ignore")
                    for framework, pattern in self.FRAMEWORK_PATTERNS.items():
                        if re.search(pattern, content) and framework not in frameworks:
                            frameworks.append(framework)
                except Exception:
                    continue
        return frameworks

    def _detect_architecture(self) -> list[str]:
        """Detect architecture hints from directory structure."""
        hints = []
        dirs = [d.name for d in self.codebase_path.iterdir() if d.is_dir()]

        # Microservices hints
        if any(d in dirs for d in ["services", "microservices", "apps"]):
            hints.append("microservices")

        # Monorepo hints
        if any(d in dirs for d in ["packages", "crates", "libs"]):
            hints.append("monorepo")

        # Backend patterns
        if any(d in dirs for d in ["api", "server", "backend"]):
            hints.append("backend")

        # Frontend patterns
        if any(d in dirs for d in ["client", "frontend", "web", "ui"]):
            hints.append("frontend")

        # Database patterns
        if any(d in dirs for d in ["migrations", "db", "database"]):
            hints.append("database")

        return hints

    def _count_code(self) -> tuple[int, int]:
        """Count total files and lines of code."""
        total_files = 0
        total_lines = 0

        extensions = {".rs", ".py", ".js", ".ts", ".go", ".java", ".rb", ".cs"}

        for ext in extensions:
            for file_path in self.codebase_path.rglob(f"*{ext}"):
                if any(p in str(file_path) for p in ["node_modules", "target", ".git", "venv"]):
                    continue
                total_files += 1
                try:
                    total_lines += len(file_path.read_text(errors="ignore").splitlines())
                except Exception:
                    continue

        return total_files, total_lines

    def _has_tests(self) -> bool:
        """Check if the codebase has tests."""
        test_indicators = [
            "tests/",
            "test/",
            "*_test.py",
            "*_test.rs",
            "*_test.go",
            "*.test.js",
            "*.test.ts",
            "*.spec.js",
            "*.spec.ts",
        ]
        for indicator in test_indicators:
            if "/" in indicator:
                if (self.codebase_path / indicator.rstrip("/")).exists():
                    return True
            else:
                if list(self.codebase_path.rglob(indicator))[:1]:
                    return True
        return False

    def _has_ci(self) -> bool:
        """Check if the codebase has CI configuration."""
        ci_files = [
            ".github/workflows",
            ".gitlab-ci.yml",
            "Jenkinsfile",
            ".circleci",
            ".travis.yml",
            "azure-pipelines.yml",
        ]
        for ci_file in ci_files:
            if (self.codebase_path / ci_file).exists():
                return True
        return False

    def _has_docker(self) -> bool:
        """Check if the codebase has Docker configuration."""
        docker_files = ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]
        for docker_file in docker_files:
            if (self.codebase_path / docker_file).exists() or list(
                self.codebase_path.rglob(docker_file)
            )[:1]:
                return True
        return False

    def _get_extensions(self, language: str) -> list[str]:
        """Get file extensions for a language."""
        ext_map = {
            "rust": [".rs"],
            "python": [".py"],
            "javascript": [".js", ".jsx"],
            "typescript": [".ts", ".tsx"],
            "go": [".go"],
            "java": [".java"],
            "csharp": [".cs"],
            "ruby": [".rb"],
        }
        return ext_map.get(language, [])

    def _search_pattern(
        self, pattern: str, extensions: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Search for a regex pattern in the codebase using ripgrep or fallback."""
        matches: list[dict[str, Any]] = []

        # Build the command
        try:
            cmd = ["rg", "--line-number", "--no-heading", "-e", pattern]
            if extensions:
                for ext in extensions:
                    cmd.extend(["-g", f"*{ext}"])
            cmd.append(str(self.codebase_path))

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            for line in result.stdout.splitlines()[:100]:  # Limit results
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append(
                        {
                            "file": parts[0],
                            "line": int(parts[1]),
                            "snippet": parts[2].strip()[:200],
                        }
                    )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback to Python search
            matches = self._python_search(pattern, extensions)

        return matches

    def _python_search(
        self, pattern: str, extensions: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Fallback Python-based search."""
        matches: list[dict[str, Any]] = []
        regex = re.compile(pattern)

        if not extensions:
            extensions = [".rs", ".py", ".js", ".ts", ".go", ".java"]

        for ext in extensions:
            for file_path in list(self.codebase_path.rglob(f"*{ext}"))[:100]:
                if any(p in str(file_path) for p in ["node_modules", "target", ".git"]):
                    continue
                try:
                    lines = file_path.read_text(errors="ignore").splitlines()
                    for i, line in enumerate(lines[:1000], 1):
                        if regex.search(line):
                            matches.append(
                                {
                                    "file": str(file_path),
                                    "line": i,
                                    "snippet": line.strip()[:200],
                                }
                            )
                except Exception:
                    continue

        return matches[:100]

    def _assess_concurrency_risk(self, snippet: str, pattern_type: str) -> str:
        """Assess the risk level of a concurrency pattern."""
        high_risk_indicators = [
            "unsafe",
            "raw pointer",
            "static mut",
            "no lock",
            "without lock",
        ]
        medium_risk_indicators = ["shared", "global", "singleton"]

        snippet_lower = snippet.lower()

        if any(ind in snippet_lower for ind in high_risk_indicators):
            return "high"
        if any(ind in snippet_lower for ind in medium_risk_indicators):
            return "medium"
        if pattern_type in ["mutex", "atomic", "channel"]:
            return "medium"

        return "low"
