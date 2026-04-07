#!/usr/bin/env python3
"""CLI entrypoint for the public order ingestion demo."""

from __future__ import annotations

import json

import click

from order_info_extractor import create_pipeline, load_config


@click.command()
@click.option("--config", "config_path", help="Path to a config JSON file.")
@click.option(
    "--source",
    type=click.Choice(["fixture", "graph"]),
    help="Override the configured message source.",
)
@click.option("--limit", default=25, show_default=True, help="Maximum messages to process.")
@click.option("--subject-filter", help="Only process messages whose subject contains this text.")
@click.option("--from-date", help="Only process messages received on or after YYYY-MM-DD.")
@click.option("--force", is_flag=True, help="Ignore idempotency state and process everything again.")
@click.option("--json-output", is_flag=True, help="Print the pipeline summary as JSON.")
def main(
    config_path: str,
    source: str,
    limit: int,
    subject_filter: str,
    from_date: str,
    force: bool,
    json_output: bool,
) -> None:
    """Run the ingestion pipeline and emit ERP-ready artifacts."""

    config = load_config(config_path)
    if source:
        config.source.provider = source

    pipeline = create_pipeline(config)
    summary = pipeline.run(
        limit=limit,
        subject_filter=subject_filter,
        from_date=from_date,
        force=force,
    )

    if json_output:
        click.echo(json.dumps(summary.model_dump(), indent=2))
        return

    click.echo(f"Run ID: {summary.run_id}")
    click.echo(
        f"Approved: {summary.approved_count} | "
        f"Manual review: {summary.review_count} | "
        f"Skipped: {summary.skipped_count}"
    )
    if summary.export_path:
        click.echo(f"ERP export: {summary.export_path}")
    if summary.manifest_path:
        click.echo(f"Run manifest: {summary.manifest_path}")


if __name__ == "__main__":
    main()
