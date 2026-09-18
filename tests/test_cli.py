"""Tests for MindTheSpot Typer CLI commands."""

from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from mindthespot.cli import app
from mindthespot.crawler.client import GCPCapacityHistoryClient

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


def test_cli_crawl_dry_run(mock_preemption_api_response, mock_price_api_response):
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        content = request.read().decode("utf-8")
        if "PREEMPTION" in content:
            return httpx.Response(200, json=mock_preemption_api_response)
        return httpx.Response(200, json=mock_price_api_response)

    mock_transport = httpx.MockTransport(mock_handler)

    with patch("mindthespot.cli.GCPCapacityHistoryClient") as mock_client_cls:
        mock_client = GCPCapacityHistoryClient(
            token_provider="fake-token",
            http_client=httpx.AsyncClient(transport=mock_transport),
            base_backoff_sec=0.01,
        )
        mock_client_cls.return_value = mock_client
        result = runner.invoke(
            app,
            ["crawl", "--dry-run", "--region", "europe-west4", "--family", "c4d"],
        )
        assert result.exit_code == 0
        assert "Crawl Summary" in result.output


def test_cli_seed_pricing_missing_project(monkeypatch):
    monkeypatch.delenv("MINDTHESPOT_GCP_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    result = runner.invoke(app, ["seed-pricing"])
    assert result.exit_code == 1
    assert "Error: GCP project ID must be specified" in result.output


def test_cli_seed_pricing_success():
    with patch("mindthespot.storage.bigquery_client.BigQueryStorageClient") as mock_storage_cls:
        mock_storage = mock_storage_cls.return_value
        mock_storage.seed_on_demand_pricing.return_value = 142
        result = runner.invoke(app, ["seed-pricing", "--project", "test-project"])
        assert result.exit_code == 0
        assert "Successfully seeded 142 on-demand pricing rows" in result.output

