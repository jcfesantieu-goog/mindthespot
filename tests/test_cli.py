"""Tests for MindTheSpot Typer CLI commands."""

from typer.testing import CliRunner

from mindthespot.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "MindTheSpot" in result.output
    assert "crawl" in result.output
    assert "serve" in result.output
    assert "anomalies" in result.output
    assert "pivots" in result.output


def test_cli_anomalies():
    result = runner.invoke(app, ["anomalies", "--severity", "CRITICAL"])
    assert result.exit_code == 0
    assert "Active Regime Shift" in result.output
    assert "CRITIC" in result.output


def test_cli_pivots():
    result = runner.invoke(
        app,
        ["pivots", "europe-west4", "europe-west4-a", "c4d-standard-16"],
    )
    assert result.exit_code == 0
    assert "Fallback Pivot Recommendations" in result.output
    assert "Savings" in result.output


def test_cli_crawl_dry_run():
    result = runner.invoke(
        app,
        ["crawl", "--dry-run", "--region", "europe-west4", "--family", "c4d"],
    )
    assert result.exit_code == 0
    assert "Crawl Summary" in result.output
