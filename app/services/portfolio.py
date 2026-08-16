"""Portfolio holding service."""

from __future__ import annotations

import csv
from io import StringIO
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.portfolio import PortfolioHolding
from app.models.security import SecurityMaster
from app.schemas.portfolio import (
    PortfolioHoldingRead,
    PortfolioHoldingUpsert,
    PortfolioImportCsvRequest,
    PortfolioImportCsvResponse,
)
from app.services.security_profile import security_profile_service
from kabuhandan_hojo.services.securities import SecurityService


ZERO = Decimal("0")


class PortfolioService:
    """Manage manually maintained portfolio holdings."""

    def __init__(self) -> None:
        self.security_service = SecurityService()

    def list_items(self, db: Session) -> list[PortfolioHoldingRead]:
        statement = (
            select(PortfolioHolding)
            .options(selectinload(PortfolioHolding.security))
            .where(PortfolioHolding.is_active.is_(True))
            .order_by(PortfolioHolding.sort_order.asc(), PortfolioHolding.created_at.asc())
        )
        items = db.scalars(statement).all()
        return [self._to_schema(db, item) for item in items]

    def upsert_item(self, db: Session, payload: PortfolioHoldingUpsert) -> PortfolioHoldingRead:
        profile = security_profile_service.resolve(payload.ticker_code, session=db)
        security = db.get(SecurityMaster, payload.ticker_code)
        if security is None:
            security = SecurityMaster(
                ticker_code=payload.ticker_code,
                local_code=profile.local_code if profile is not None else payload.ticker_code,
                name=profile.name if profile is not None else payload.ticker_code,
                name_english=profile.name_english if profile is not None else None,
                market=profile.market if profile is not None else None,
                industry_17=profile.industry_17 if profile is not None else None,
                industry_33=profile.industry_33 if profile is not None else None,
                listed_date=profile.listed_date if profile is not None else None,
                is_active=True,
            )
            db.add(security)
            db.flush()
        else:
            if security.local_code is None and profile is not None:
                security.local_code = profile.local_code
            if security_profile_service.prefers_profile_name(security.name, payload.ticker_code, profile.name if profile else None):
                security.name = profile.name
            if security.name_english is None and profile is not None:
                security.name_english = profile.name_english
            if security.market is None and profile is not None:
                security.market = profile.market
            if security.industry_17 is None and profile is not None:
                security.industry_17 = profile.industry_17
            if security.industry_33 is None and profile is not None:
                security.industry_33 = profile.industry_33
            if security.listed_date is None and profile is not None:
                security.listed_date = profile.listed_date

        holding = db.scalar(select(PortfolioHolding).where(PortfolioHolding.ticker_code == payload.ticker_code))
        if holding is None:
            holding = PortfolioHolding(
                ticker_code=payload.ticker_code,
                quantity=payload.quantity,
                average_cost=payload.average_cost,
                note=payload.note,
                sort_order=payload.sort_order,
                is_active=True,
            )
            db.add(holding)
        else:
            holding.quantity = payload.quantity
            holding.average_cost = payload.average_cost
            holding.note = payload.note
            holding.sort_order = payload.sort_order
            holding.is_active = True

        db.commit()
        db.refresh(holding)
        return self._to_schema(db, holding)

    def archive_item(self, db: Session, ticker_code: str) -> None:
        holding = db.scalar(select(PortfolioHolding).where(PortfolioHolding.ticker_code == ticker_code))
        if holding is None:
            return
        holding.is_active = False
        db.commit()

    def import_csv(self, db: Session, payload: PortfolioImportCsvRequest) -> PortfolioImportCsvResponse:
        reader = csv.DictReader(StringIO(payload.csv_text.strip()))
        imported_codes: list[str] = []
        imported_count = 0
        for index, row in enumerate(reader, start=1):
            ticker_code = str(row.get("ticker_code") or "").strip()
            quantity = str(row.get("quantity") or "").strip()
            if not ticker_code or not quantity:
                continue
            average_cost_text = str(row.get("average_cost") or "").strip()
            note_text = str(row.get("note") or "").strip()
            sort_order_text = str(row.get("sort_order") or "").strip()
            holding = self.upsert_item(
                db,
                PortfolioHoldingUpsert(
                    ticker_code=ticker_code,
                    quantity=Decimal(quantity),
                    average_cost=Decimal(average_cost_text) if average_cost_text else None,
                    note=note_text or None,
                    sort_order=int(sort_order_text) if sort_order_text else index,
                ),
            )
            imported_codes.append(holding.ticker_code)
            imported_count += 1

        archived_count = 0
        if payload.replace_existing and imported_codes:
            active_holdings = db.scalars(
                select(PortfolioHolding).where(PortfolioHolding.is_active.is_(True))
            ).all()
            for holding in active_holdings:
                if holding.ticker_code in imported_codes:
                    continue
                holding.is_active = False
                archived_count += 1
            db.commit()

        return PortfolioImportCsvResponse(imported_count=imported_count, archived_count=archived_count)

    def _to_schema(self, db: Session, holding: PortfolioHolding) -> PortfolioHoldingRead:
        security = holding.security or db.get(SecurityMaster, holding.ticker_code)
        prices = self.security_service.latest_prices(db, holding.ticker_code, limit=1)
        last_price = prices[-1].close_price if prices else None
        quantity = Decimal(str(holding.quantity))
        average_cost = Decimal(str(holding.average_cost)) if holding.average_cost is not None else None
        market_value = (last_price * quantity).quantize(Decimal("0.01")) if last_price is not None else None
        cost_basis = (average_cost * quantity).quantize(Decimal("0.01")) if average_cost is not None else None
        unrealized_pnl = None
        unrealized_return_pct = None
        if market_value is not None and cost_basis not in {None, ZERO}:
            unrealized_pnl = (market_value - cost_basis).quantize(Decimal("0.01"))
            unrealized_return_pct = ((unrealized_pnl / cost_basis) * Decimal("100")).quantize(Decimal("0.01"))

        return PortfolioHoldingRead(
            id=holding.id,
            ticker_code=holding.ticker_code,
            name=security.name if security is not None else holding.ticker_code,
            market=security.market if security is not None else None,
            quantity=quantity,
            average_cost=average_cost,
            last_price=last_price,
            market_value=market_value,
            cost_basis=cost_basis,
            unrealized_pnl=unrealized_pnl,
            unrealized_return_pct=unrealized_return_pct,
            note=holding.note,
            sort_order=holding.sort_order,
            updated_at=holding.updated_at,
        )


portfolio_service = PortfolioService()
