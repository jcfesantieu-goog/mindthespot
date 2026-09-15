"""Command-line interface for MindTheSpot."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mindthespot.config.loader import load_catalog, load_watchlist
from mindthespot.crawler.client import GCPCapacityHistoryClient
from mindthespot.crawler.extractor import CrawlEngine

app = typer.Typer(
    name="mindthespot",
    help="MindTheSpot: GCP Spot VM Regime Shift Warning & Fallback Pivot Engine",
    add_completion=False,
)
console = Console()


@app.callback()
def main() -> None:
    """MindTheSpot CLI root."""
    pass


@app.command("crawl")
def crawl(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Simulate or perform crawl without writing to BigQuery"),
    ] = False,
    output: Annotated[
        str,
        typer.Option("--output", help="Output destination: 'console' or 'bigquery'"),
    ] = "console",
    project: Annotated[
        str,
        typer.Option("--project", envvar="GCP_PROJECT_ID", help="GCP project ID"),
    ] = "mindthespot-default",
    dataset: Annotated[
        str,
        typer.Option("--dataset", envvar="BIGQUERY_DATASET_RAW", help="Target BigQuery raw dataset"),
    ] = "mindthespot_raw",
    catalog_path: Annotated[
        Path | None,
        typer.Option("--catalog", help="Custom catalog YAML path"),
    ] = None,
    watchlist_path: Annotated[
        Path | None,
        typer.Option("--watchlist", help="Custom watchlist YAML path"),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option("--region", help="Filter crawl to a specific region"),
    ] = None,
    family: Annotated[
        str | None,
        typer.Option("--family", help="Filter crawl to a specific instance family"),
    ] = None,
) -> None:
    """Crawl GCP Spot preemption rates and interval pricing."""
    console.print(f"[bold cyan]🚀 Starting MindTheSpot Crawler (Project: {project}, Dataset: {dataset})...[/bold cyan]")

    catalog = load_catalog(catalog_path)
    watchlist = load_watchlist(watchlist_path)

    async def _run():
        client = GCPCapacityHistoryClient()
        engine = CrawlEngine(
            client=client,
            catalog=catalog,
            watchlist=watchlist,
            project=project,
        )

        preempt_records, price_records, summary = await engine.run(
            region_filter=region,
            family_filter=family,
        )

        # Print summary table
        table = Table(title="📊 MindTheSpot Crawl Summary", border_style="cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Value", style="green")

        table.add_row("Snapshot Date", summary.snapshot_date)
        table.add_row("Duration", f"{summary.duration_seconds:.2f}s")
        table.add_row("Preemption Pools Target", str(summary.total_preemption_pools))
        table.add_row("Preemption Queries OK", str(summary.successful_preemption_queries))
        table.add_row("Price Pools Target", str(summary.total_price_pools))
        table.add_row("Price Queries OK", str(summary.successful_price_queries))
        table.add_row("Failed Queries", str(summary.failed_queries))

        console.print(table)

        if not dry_run and output == "bigquery":
            console.print(
                f"[bold cyan]📦 Persisting {len(preempt_records)} preemption and "
                f"{len(price_records)} price records to BigQuery [{project}.{dataset}]...[/bold cyan]"
            )
            from mindthespot.storage.bigquery_client import BigQueryStorageClient

            storage = BigQueryStorageClient(project=project, dataset=dataset)
            storage.ensure_dataset_and_tables()
            p_rows = [r.model_dump() for r in preempt_records]
            pr_rows = [r.model_dump() for r in price_records]
            # Convert dates and intervals to JSON-serializable strings
            for r in p_rows:
                r["snapshot_date"] = str(r["snapshot_date"])
                r["date"] = str(r["date"])
            for r in pr_rows:
                r["snapshot_date"] = str(r["snapshot_date"])
                r["start_time"] = str(r["start_time"])
                if r.get("end_time"):
                    r["end_time"] = str(r["end_time"])

            p_count = storage.insert_preemption_rows(p_rows)
            pr_count = storage.insert_price_rows(pr_rows)
            console.print(
                f"[bold green]✅ Successfully persisted {p_count} preemption records and "
                f"{pr_count} price records into BigQuery.[/bold green]"
            )
        elif dry_run or output == "console":
            console.print(
                f"[yellow]ℹ️ Dry-run mode active. {len(preempt_records)} preemption and "
                f"{len(price_records)} price records collected (no database writes).[/yellow]"
            )

    asyncio.run(_run())


@app.command("serve")
def serve(
    host: Annotated[str, typer.Option("--host", help="Bind host address")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", help="Port to listen on")] = 8000,
    reload: Annotated[bool, typer.Option("--reload", help="Enable auto-reload on code change")] = False,
) -> None:
    """Launch MindTheSpot FastAPI backend server."""
    import uvicorn

    console.print(f"[bold green]⚡ Launching MindTheSpot API at http://{host}:{port}...[/bold green]")
    uvicorn.run("mindthespot.api.app:app", host=host, port=port, reload=reload)


@app.command("anomalies")
def list_anomalies_cli(
    severity: Annotated[
        str | None,
        typer.Option("--severity", help="Filter by severity: CRITICAL, ELEVATED"),
    ] = None,
    region: Annotated[str | None, typer.Option("--region", help="Filter by region")] = None,
    watchlist_only: Annotated[
        bool,
        typer.Option("--watchlist", help="Filter only to watchlist pools"),
    ] = False,
) -> None:
    """Query and display active regime shift warning anomalies."""
    from mindthespot.api.service import SpotDataService

    service = SpotDataService()
    anomalies = service.get_anomalies(
        severity=severity,
        region=region,
        watchlist_only=watchlist_only,
    )

    table = Table(title="🚨 Active Regime Shift Warning Anomalies", border_style="red")
    table.add_column("Pool Key", style="bold cyan")
    table.add_column("Severity", style="bold")
    table.add_column("7d Rate", justify="right")
    table.add_column("Baseline", justify="right")
    table.add_column("Delta (Δ)", justify="right")
    table.add_column("Z-Score", justify="right")
    table.add_column("Spot Price", justify="right")
    table.add_column("Pivots", justify="center")

    for a in anomalies:
        sev_color = "red" if a.severity == "CRITICAL" else "yellow"
        table.add_row(
            a.pool_key,
            f"[{sev_color}]{a.severity}[/{sev_color}]",
            f"{a.recent_7d_rate * 100:.1f}%",
            f"{a.baseline_rate * 100:.1f}%",
            f"[bold {sev_color}]+{a.rate_delta * 100:.1f}%[/bold {sev_color}]",
            f"+{a.z_score:.2f}σ",
            f"${a.hourly_price:.4f}/hr",
            f"[green]{a.pivot_count}[/green]",
        )

    console.print(table)


@app.command("pivots")
def list_pivots_cli(
    region: Annotated[str, typer.Argument(help="Target region, e.g. europe-west4")],
    zone: Annotated[str, typer.Argument(help="Target zone, e.g. europe-west4-a")],
    machine_type: Annotated[str, typer.Argument(help="Target machine type, e.g. c4d-standard-16")],
) -> None:
    """Find and rank sibling zone and equivalent family pivot recommendations."""
    from mindthespot.api.service import SpotDataService

    service = SpotDataService()
    res = service.get_pivot_recommendations(region, zone, machine_type)

    if not res or not res.pivots:
        console.print(f"[yellow]No fallback pivots found for {region}/{zone}/{machine_type}[/yellow]")
        return

    table = Table(
        title=f"🔄 Fallback Pivot Recommendations for {region}/{zone}/{machine_type}",
        border_style="cyan",
    )
    table.add_column("Type", style="bold")
    table.add_column("Pivot Target", style="cyan")
    table.add_column("7d Rate", justify="right")
    table.add_column("Risk Savings", justify="right", style="green")
    table.add_column("Hourly Price", justify="right")
    table.add_column("Cost Delta", justify="right")
    table.add_column("Rationale")

    for p in res.pivots:
        cost_str = (
            f"-${p.cost_difference:.4f}/hr"
            if p.cost_difference >= 0
            else f"+${abs(p.cost_difference):.4f}/hr"
        )
        table.add_row(
            p.pivot_type,
            f"{p.pivot_zone} / {p.pivot_machine_type}",
            f"{p.pivot_7d_rate * 100:.1f}%",
            f"-{p.preemption_savings * 100:.1f}%",
            f"${p.pivot_hourly_price:.4f}",
            cost_str,
            p.recommendation_reason,
        )

    console.print(table)


if __name__ == "__main__":
    app()

