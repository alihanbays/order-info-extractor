"""Factory for building a fully-wired pipeline from config."""

from __future__ import annotations

from order_info_extractor.catalog import ProductCatalog
from order_info_extractor.clients.llm import FixtureLLMClient, OpenAILLMClient
from order_info_extractor.clients.outlook import FixtureInboxClient, GraphInboxClient
from order_info_extractor.config import AppConfig
from order_info_extractor.exporters import ERPExporter
from order_info_extractor.observability import configure_logging
from order_info_extractor.pipeline import IngestionPipeline
from order_info_extractor.state import SQLiteStateStore


def create_pipeline(config: AppConfig) -> IngestionPipeline:
    """Build the pipeline and all of its runtime dependencies."""

    catalog = ProductCatalog(config.resolve_path(config.catalog_path))
    logger, _ = configure_logging(config.output_path(config.paths.logs_dir))
    state_store = SQLiteStateStore(config.output_path(config.paths.state_db))
    exporter = ERPExporter(config.output_path(config.paths.exports_dir))

    if config.source.provider == "graph":
        inbox_client = GraphInboxClient(config.source, config.retry)
        llm_client = OpenAILLMClient(
            config=config.openai,
            retry_config=config.retry,
            catalog_prompt=catalog.compact_prompt_view(),
        )
    else:
        inbox_client = FixtureInboxClient(config.resolve_path(config.source.fixture_path))
        if config.openai.api_key:
            llm_client = OpenAILLMClient(
                config=config.openai,
                retry_config=config.retry,
                catalog_prompt=catalog.compact_prompt_view(),
            )
        else:
            llm_client = FixtureLLMClient(config.resolve_path(config.source.fixture_llm_path))

    return IngestionPipeline(
        config=config,
        inbox_client=inbox_client,
        llm_client=llm_client,
        catalog=catalog,
        exporter=exporter,
        state_store=state_store,
        logger=logger,
    )
