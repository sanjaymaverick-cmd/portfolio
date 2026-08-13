from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from meridian.domain.models import AccountView, BookSummary, HoldingView, MappedRow
from meridian.domain.money import safe_div
from meridian.domain.reference import enrich
from meridian.domain.symbols import normalize_symbol
from meridian.storage.schema import Account, Holding, ImportJob


class AccountRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_active(self) -> list[Account]:
        return list(self.session.scalars(select(Account).order_by(Account.name)))

    def get(self, account_id: int) -> Account | None:
        return self.session.get(Account, account_id)

    def get_by_name(self, name: str) -> Account | None:
        return self.session.scalar(select(Account).where(Account.name == name))

    def create(self, name: str, broker: str = "generic", client_id: str | None = None) -> Account:
        existing = self.get_by_name(name)
        if existing:
            return existing
        account = Account(name=name, broker=broker, client_id=client_id)
        self.session.add(account)
        self.session.flush()
        return account

    def views(self) -> list[AccountView]:
        accounts = self.list_active()
        out: list[AccountView] = []
        for account in accounts:
            holdings = list(account.holdings)
            mv = Decimal("0")
            for holding in holdings:
                if holding.last_price is not None:
                    mv += holding.quantity * holding.last_price
            out.append(
                AccountView(
                    id=account.id,
                    name=account.name,
                    broker=account.broker,
                    client_id=account.client_id,
                    is_active=account.is_active,
                    holding_count=len(holdings),
                    market_value=mv,
                )
            )
        return out


class HoldingRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        account_id: int | None = None,
        query: str | None = None,
        sector: str | None = None,
    ) -> list[Holding]:
        stmt = select(Holding).options(joinedload(Holding.account)).order_by(Holding.symbol)
        if account_id:
            stmt = stmt.where(Holding.account_id == account_id)
        if sector and sector != "all":
            stmt = stmt.where(Holding.sector == sector)
        if query:
            like = f"%{query.strip().upper()}%"
            stmt = stmt.where(
                func.upper(Holding.symbol).like(like)
                | func.upper(Holding.company_name).like(like)
            )
        return list(self.session.scalars(stmt).unique())

    def get(self, holding_id: int) -> Holding | None:
        return self.session.scalar(
            select(Holding).options(joinedload(Holding.account)).where(Holding.id == holding_id)
        )

    def upsert(self, account: Account, row: MappedRow, source: str = "import") -> Holding:
        parsed = normalize_symbol(row.symbol, row.exchange)
        meta = enrich(parsed.symbol, row.company_name, row.sector)
        existing = self.session.scalar(
            select(Holding).where(
                Holding.account_id == account.id,
                Holding.symbol == parsed.symbol,
                Holding.exchange == parsed.exchange,
            )
        )
        if existing:
            existing.quantity = row.quantity
            existing.avg_cost = row.avg_cost
            if row.last_price is not None:
                existing.last_price = row.last_price
            existing.company_name = meta["name"]
            existing.sector = meta["sector"]
            existing.mcap = meta["mcap"]
            existing.isin = row.isin or existing.isin
            existing.source = source
            existing.yahoo = parsed.yahoo
            return existing
        holding = Holding(
            account_id=account.id,
            symbol=parsed.symbol,
            exchange=parsed.exchange,
            yahoo=parsed.yahoo,
            isin=row.isin,
            company_name=meta["name"],
            sector=meta["sector"],
            mcap=meta["mcap"],
            quantity=row.quantity,
            avg_cost=row.avg_cost,
            last_price=row.last_price,
            source=source,
        )
        self.session.add(holding)
        self.session.flush()
        return holding

    def update_manual(
        self,
        holding: Holding,
        *,
        quantity: Decimal | None = None,
        avg_cost: Decimal | None = None,
        last_price: Decimal | None = None,
        notes: str | None = None,
        company_name: str | None = None,
        sector: str | None = None,
    ) -> Holding:
        if quantity is not None:
            holding.quantity = quantity
        if avg_cost is not None:
            holding.avg_cost = avg_cost
        if last_price is not None:
            holding.last_price = last_price
        if notes is not None:
            holding.notes = notes
        if company_name:
            holding.company_name = company_name
        if sector:
            holding.sector = sector
        holding.source = "manual" if holding.source == "manual" else holding.source
        self.session.flush()
        return holding

    def delete(self, holding: Holding) -> None:
        self.session.delete(holding)

    def to_view(self, holding: Holding) -> HoldingView:
        return HoldingView(
            id=holding.id,
            account_id=holding.account_id,
            account_name=holding.account.name,
            broker=holding.account.broker,
            symbol=holding.symbol,
            exchange=holding.exchange,
            yahoo=holding.yahoo,
            isin=holding.isin,
            company_name=holding.company_name,
            sector=holding.sector,
            mcap=holding.mcap,
            quantity=holding.quantity,
            avg_cost=holding.avg_cost,
            last_price=holding.last_price,
            prev_close=holding.prev_close,
            price_asof=holding.price_asof,
            source=holding.source,
            notes=holding.notes,
            updated_at=holding.updated_at,
        )

    def summary(self, holdings: list[Holding] | None = None) -> BookSummary:
        rows = holdings if holdings is not None else self.list()
        invested = Decimal("0")
        market_value = Decimal("0")
        day_pnl = Decimal("0")
        day_basis = Decimal("0")
        day_defined = False
        tape_asof = None
        account_ids: set[int] = set()
        sector_mv: dict[str, Decimal] = {}
        mcap_mv: dict[str, Decimal] = {}
        top_symbol: str | None = None
        top_value = Decimal("0")
        for holding in rows:
            account_ids.add(holding.account_id)
            book = holding.quantity * holding.avg_cost
            invested += book
            value = holding.quantity * holding.last_price if holding.last_price is not None else book
            market_value += value
            if holding.prev_close is not None and holding.last_price is not None:
                day_pnl += holding.quantity * (holding.last_price - holding.prev_close)
                day_basis += holding.quantity * holding.prev_close
                day_defined = True
            if holding.price_asof and (tape_asof is None or holding.price_asof > tape_asof):
                tape_asof = holding.price_asof
            sector_mv[holding.sector] = sector_mv.get(holding.sector, Decimal("0")) + value
            mcap_mv[holding.mcap] = mcap_mv.get(holding.mcap, Decimal("0")) + value
            if value > top_value:
                top_value = value
                top_symbol = holding.symbol
        pnl = market_value - invested
        denom = market_value if market_value else Decimal("1")
        sectors = sorted(
            ((name, (value / denom) * Decimal("100")) for name, value in sector_mv.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        mcaps = sorted(
            ((name, (value / denom) * Decimal("100")) for name, value in mcap_mv.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        return BookSummary(
            market_value=market_value,
            invested=invested,
            pnl=pnl,
            pnl_pct=safe_div(pnl, invested) * Decimal("100") if invested else None,
            names=len(rows),
            accounts=len(account_ids),
            day_pnl=day_pnl if day_defined else None,
            day_pnl_pct=safe_div(day_pnl, day_basis) * Decimal("100") if day_defined and day_basis else None,
            day_undefined=not day_defined,
            tape_asof=tape_asof,
            sector_weights=sectors,
            mcap_weights=mcaps,
            top_weight=(top_value / denom) * Decimal("100") if rows else None,
            top_symbol=top_symbol,
        )


class ImportRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        account_id: int | None,
        broker: str,
        filename: str,
        status: str,
        accepted: int,
        rejected: int,
        notes: str | None = None,
    ) -> ImportJob:
        job = ImportJob(
            account_id=account_id,
            broker=broker,
            filename=filename,
            status=status,
            accepted=accepted,
            rejected=rejected,
            notes=notes,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def recent(self, limit: int = 8) -> list[ImportJob]:
        return list(
            self.session.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit))
        )
