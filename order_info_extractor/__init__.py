"""Public package surface for the order ingestion demo."""

from order_info_extractor.config import AppConfig, load_config
from order_info_extractor.factory import create_pipeline
from order_info_extractor.pipeline import IngestionPipeline

__all__ = ["AppConfig", "IngestionPipeline", "create_pipeline", "load_config"]

__version__ = "1.0.0"
