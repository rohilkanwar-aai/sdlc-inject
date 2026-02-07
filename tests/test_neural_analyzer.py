"""Tests for the refactored NeuralCodeAnalyzer."""

import pytest
from pathlib import Path

from sdlc_inject.analyzer.neural import (
    NeuralCodeAnalyzer,
    VulnerabilityPoint,
    NeuralAnalysisResult,
)


class TestNeuralCodeAnalyzerInit:
    """Tests for NeuralCodeAnalyzer initialization."""

    def test_default_init(self):
        analyzer = NeuralCodeAnalyzer()
        assert analyzer.model == "claude-opus-4-6"
        assert analyzer.total_tokens == 0

    def test_custom_model(self):
        analyzer = NeuralCodeAnalyzer(model="claude-opus-4-6")
        assert analyzer.model == "claude-opus-4-6"

    def test_exa_client_lazy_init(self):
        analyzer = NeuralCodeAnalyzer()
        assert analyzer._exa_client is None

    def test_backward_compat_api_key_param(self):
        """api_key parameter is accepted but ignored (SDK reads from env)."""
        analyzer = NeuralCodeAnalyzer(api_key="sk-ant-test")
        # Should not raise


class TestFindRelevantFiles:
    """Tests for the heuristic file selector."""

    def test_find_files_empty_dir(self, tmp_path):
        analyzer = NeuralCodeAnalyzer()
        result = analyzer._find_relevant_files(tmp_path, 10)
        assert result == []

    def test_find_files_prioritizes_concurrency(self, tmp_path):
        # Create files with different priority levels
        (tmp_path / "mutex.py").write_text("import threading")
        (tmp_path / "utils.py").write_text("print('hello')")
        (tmp_path / "lock_manager.rs").write_text("fn acquire_lock() {}")

        analyzer = NeuralCodeAnalyzer()
        result = analyzer._find_relevant_files(tmp_path, 10)

        filenames = [f.name for f in result]
        # mutex and lock files should be prioritized
        assert "mutex.py" in filenames
        assert "lock_manager.rs" in filenames

    def test_find_files_respects_max(self, tmp_path):
        for i in range(30):
            (tmp_path / f"file_{i}.py").write_text(f"# file {i}")

        analyzer = NeuralCodeAnalyzer()
        result = analyzer._find_relevant_files(tmp_path, 5)
        assert len(result) <= 5

    def test_find_files_excludes_git(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config.py").write_text("# git config")
        (tmp_path / "main.py").write_text("# main")

        analyzer = NeuralCodeAnalyzer()
        result = analyzer._find_relevant_files(tmp_path, 10)
        file_strs = [str(f) for f in result]
        assert not any(".git" in s for s in file_strs)


class TestParseVulnerabilities:
    """Tests for vulnerability parsing from agent output."""

    def test_parse_empty(self):
        analyzer = NeuralCodeAnalyzer()
        result = analyzer._parse_vulnerabilities({}, Path("/tmp"))
        assert result == []

    def test_parse_single_vuln(self):
        analyzer = NeuralCodeAnalyzer()
        data = {
            "vulnerabilities": [
                {
                    "file_path": "src/lock.rs",
                    "start_line": 10,
                    "end_line": 20,
                    "code_snippet": "fn acquire() {}",
                    "function_name": "acquire",
                    "vulnerability_type": "race_condition",
                    "confidence": 0.85,
                    "explanation": "Non-atomic check-then-act",
                    "suggested_injection": "Add delay between check and act",
                    "data_flow": "request -> check -> acquire",
                }
            ]
        }
        result = analyzer._parse_vulnerabilities(data, Path("/tmp"))
        assert len(result) == 1
        assert result[0].vulnerability_type == "race_condition"
        assert result[0].confidence == 0.85
        assert result[0].affected_functions == ["acquire"]

    def test_parse_missing_fields(self):
        """Missing fields should use defaults, not crash."""
        analyzer = NeuralCodeAnalyzer()
        data = {
            "vulnerabilities": [
                {"vulnerability_type": "unknown"}
            ]
        }
        result = analyzer._parse_vulnerabilities(data, Path("/tmp"))
        assert len(result) == 1
        assert result[0].start_line == 0
        assert result[0].confidence == 0.5


class TestVulnerabilityPoint:
    """Tests for VulnerabilityPoint dataclass."""

    def test_default_fields(self):
        vuln = VulnerabilityPoint(
            file_path="test.py",
            start_line=1,
            end_line=5,
            code_snippet="code",
            vulnerability_type="race_condition",
            confidence=0.8,
            explanation="test",
            suggested_injection="inject",
        )
        assert vuln.affected_functions == []
        assert vuln.data_flow is None
        assert vuln.similar_vulnerabilities == []
        assert vuln.related_incidents == []


class TestNeuralAnalysisResult:
    """Tests for NeuralAnalysisResult dataclass."""

    def test_to_dict(self):
        result = NeuralAnalysisResult(
            codebase_path="/tmp/test",
            files_analyzed=5,
            total_tokens_used=1000,
            vulnerability_points=[],
            architecture_summary="A test project",
            concurrency_model="single-threaded",
            recommended_patterns=[],
        )
        d = result.to_dict()
        assert d["codebase_path"] == "/tmp/test"
        assert d["files_analyzed"] == 5
        assert d["total_tokens_used"] == 1000
        assert d["vulnerability_points"] == []

    def test_to_dict_with_cost(self):
        result = NeuralAnalysisResult(
            codebase_path="/tmp/test",
            files_analyzed=5,
            total_tokens_used=1000,
            total_cost_usd=0.05,
            vulnerability_points=[],
            architecture_summary="",
            concurrency_model="",
            recommended_patterns=[],
        )
        d = result.to_dict()
        assert d["total_cost_usd"] == 0.05
