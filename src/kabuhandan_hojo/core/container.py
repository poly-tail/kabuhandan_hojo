"""Dependency container."""

from __future__ import annotations

from dataclasses import dataclass

from kabuhandan_hojo.connectors.edinet import EdinetConnector
from kabuhandan_hojo.connectors.jquants import JQuantsConnector
from kabuhandan_hojo.connectors.tdnet import TdnetConnector
from kabuhandan_hojo.connectors.youtube import YouTubeConnector
from kabuhandan_hojo.core.config import Settings
from kabuhandan_hojo.features.technical import TechnicalFeatureCalculator
from kabuhandan_hojo.llm.base import SummaryGenerator
from kabuhandan_hojo.llm.template import TemplateSummaryGenerator
from kabuhandan_hojo.normalizers.events import EdinetEventNormalizer
from kabuhandan_hojo.scoring.engine import WeightedScoreEngine
from kabuhandan_hojo.services.alerts import AlertService


@dataclass(slots=True)
class ServiceContainer:
    """Runtime objects shared across routes and jobs."""

    score_engine: WeightedScoreEngine
    technical_feature_calculator: TechnicalFeatureCalculator
    alert_service: AlertService
    summary_generator: SummaryGenerator
    event_normalizer: EdinetEventNormalizer
    jquants_connector: JQuantsConnector
    edinet_connector: EdinetConnector
    tdnet_connector: TdnetConnector
    youtube_connector: YouTubeConnector


def build_container(settings: Settings) -> ServiceContainer:
    """Construct application dependencies."""

    return ServiceContainer(
        score_engine=WeightedScoreEngine.from_settings(settings),
        technical_feature_calculator=TechnicalFeatureCalculator(),
        alert_service=AlertService(settings=settings),
        summary_generator=TemplateSummaryGenerator(),
        event_normalizer=EdinetEventNormalizer(),
        jquants_connector=JQuantsConnector(
            base_url=settings.jquants_base_url,
            api_key=settings.jquants_api_key,
        ),
        edinet_connector=EdinetConnector(
            base_url=settings.edinet_base_url,
            api_key=settings.edinet_api_key,
        ),
        tdnet_connector=TdnetConnector(
            base_url=settings.tdnet_base_url,
            api_key=settings.tdnet_api_key,
        ),
        youtube_connector=YouTubeConnector(
            base_url=settings.youtube_base_url,
            api_key=settings.youtube_api_key,
        ),
    )
