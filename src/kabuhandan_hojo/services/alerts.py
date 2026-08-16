"""Alert generation logic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kabuhandan_hojo.core.config import Settings
from kabuhandan_hojo.models.entities import EventFact, ScoreDaily, TechnicalFeatureDaily


@dataclass(slots=True)
class AlertPayload:
    ticker_code: str
    alert_type: str
    severity: str
    message: str


class AlertService:
    """Create explainable alerts from numeric state transitions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_alerts(
        self,
        *,
        ticker_code: str,
        current_score: ScoreDaily,
        previous_score: ScoreDaily | None,
        technical_feature: TechnicalFeatureDaily | None,
        recent_events: list[EventFact],
    ) -> list[AlertPayload]:
        alerts: list[AlertPayload] = []
        if current_score.total_score >= Decimal(str(self.settings.high_priority_threshold)):
            alerts.append(
                AlertPayload(
                    ticker_code=ticker_code,
                    alert_type="high_priority",
                    severity="high",
                    message=f"監視優先度が高水準です。total_score={current_score.total_score:.2f}",
                )
            )

        if previous_score is not None:
            delta = current_score.total_score - previous_score.total_score
            if abs(delta) >= Decimal(str(self.settings.score_change_alert_threshold)):
                direction = "上昇" if delta > 0 else "低下"
                alerts.append(
                    AlertPayload(
                        ticker_code=ticker_code,
                        alert_type="score_change",
                        severity="medium",
                        message=f"総合点が急変しました。{direction}幅={delta:.2f}",
                    )
                )

        if technical_feature and technical_feature.breakout_20d and technical_feature.volume_ratio_20:
            if technical_feature.volume_ratio_20 >= Decimal("1.5"):
                alerts.append(
                    AlertPayload(
                        ticker_code=ticker_code,
                        alert_type="breakout_volume",
                        severity="high",
                        message="20日高値更新と出来高増加を検知しました。",
                    )
                )

        if any(event.event_type in {"downward_revision", "dilution_risk"} for event in recent_events):
            alerts.append(
                AlertPayload(
                    ticker_code=ticker_code,
                    alert_type="risk_event",
                    severity="high",
                    message="悪材料イベントを検知しました。要因確認を優先してください。",
                )
            )

        return alerts

