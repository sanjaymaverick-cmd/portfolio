from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from meridian.domain.models import MappedRow
from meridian.recommendations.eod_rules import rule_attribution, validate_payload
from meridian.recommendations.eod_service import EodService
from meridian.scoring.news_filter import Headline, filter_headlines, sentiment_score
from meridian.storage.market import QuoteRepo
from meridian.storage.repositories import AccountRepo, HoldingRepo
from meridian.storage.schema import Base, DailyImpact, DailyNews, DailyPerformance


def test_negation_and_diminishers() -> None:
    beat = sentiment_score("TCS beat estimates")
    flipped = sentiment_score("TCS did not beat estimates")
    modest = sentiment_score("TCS slightly beat estimates")
    assert beat > 0
    assert flipped < 0
    assert 0 < modest < beat


def test_filter_ranks_and_forces_filings() -> None:
    raw = [
        Headline(title="Unrelated cement demand slump in China", source="Wire"),
        Headline(title="TCS profit surge as revenue growth stays strong", source="Economic Times"),
        Headline(title="TCS profit surge as revenue growth stays strong", source="Mirror"),
        Headline(title="TCS outcome of board meeting", source="NSE"),
        Headline(title="Infosys only", source="Blog"),
    ]
    kept = filter_headlines(raw, symbol="TCS", company="Tata Consultancy Services", keep=1)
    titles = [item.title for item in kept]
    assert any("profit surge" in title for title in titles)
    assert any("outcome of board" in title for title in titles)
    assert all(item.kept for item in kept)
    assert len([item for item in kept if "profit surge" in item.title]) == 1


def test_rule_payload_shape() -> None:
    headlines = [
        Headline(
            title="TCS beat quarterly profit estimates",
            source="Mint",
            aspect="Results",
            sentiment=1.0,
            kept=True,
            is_filing=False,
        )
    ]
    payload = rule_attribution(symbol="TCS", day_pct=2.1, headlines=headlines, nifty_chg=0.4)
    assert set(payload) == {"positive", "negative", "market_context", "confidence", "takeaway"}
    assert payload["positive"]
    assert payload["positive"][0]["driver"].startswith("TCS")
    assert 0 <= payload["confidence"] <= 1
    assert "Nifty" in payload["market_context"]
    assert "name-specific" in payload["market_context"]


def test_validate_drops_invented_news() -> None:
    known = [Headline(title="TCS reports Q1 profit beat", source="ET", kept=True)]
    cleaned = validate_payload(
        {
            "positive": [
                {"driver": "TCS colonizes Mars after secret launch", "strength": 0.9, "source": "blog"},
                {"driver": "TCS reports Q1 profit beat, says ET", "strength": 0.7, "source": "ET", "aspect": "Results"},
            ],
            "negative": "bad",
            "confidence": 4,
            "takeaway": "ok",
            "market_context": "Nifty +0.2%.",
        },
        known,
    )
    assert len(cleaned["positive"]) == 1
    assert "profit beat" in cleaned["positive"][0]["driver"]
    assert cleaned["negative"] == []
    assert cleaned["confidence"] == 1.0


def test_eod_service_persists_synthetic(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'eod.db'}", future=True)
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine, future=True)()
    account = AccountRepo(session).create("Core", "zerodha")
    holdings = HoldingRepo(session)
    tcs = holdings.upsert(
        account,
        MappedRow(
            symbol="TCS",
            exchange="NSE",
            company_name="Tata Consultancy Services",
            quantity=Decimal("10"),
            avg_cost=Decimal("3000"),
            last_price=Decimal("3120"),
        ),
    )
    hdfc = holdings.upsert(
        account,
        MappedRow(
            symbol="HDFCBANK",
            exchange="NSE",
            company_name="HDFC Bank",
            quantity=Decimal("20"),
            avg_cost=Decimal("1600"),
            last_price=Decimal("1568"),
        ),
    )
    rel = holdings.upsert(
        account,
        MappedRow(
            symbol="RELIANCE",
            exchange="NSE",
            company_name="Reliance Industries",
            quantity=Decimal("5"),
            avg_cost=Decimal("1400"),
            last_price=Decimal("1402"),
        ),
    )
    tcs.prev_close = Decimal("3000")
    hdfc.prev_close = Decimal("1600")
    rel.prev_close = Decimal("1400")
    QuoteRepo(session).upsert(
        symbol="NIFTY",
        exchange="INDEX",
        yahoo="^NSEI",
        last_price=Decimal("24400"),
        prev_close=Decimal("24300"),
    )
    session.commit()

    weekend = EodService(session).run(datetime(2026, 8, 15), fetch=False)
    assert weekend.skipped == "weekend"

    headlines = {
        "TCS": [
            Headline(
                title="TCS beat profit estimates on strong deal wins",
                source="Mint",
                url="https://example.test/tcs",
            ),
            Headline(title="TCS outcome of board meeting", source="NSE", is_filing=True),
        ]
    }
    result = EodService(session).run(
        datetime(2026, 8, 13),
        fetch=False,
        headlines_by_symbol=headlines,
    )
    session.commit()
    assert result.skipped is None
    assert result.error is None
    assert "TCS" in result.names
    assert "HDFCBANK" in result.names
    assert result.attributed >= 2

    perfs = list(session.scalars(select(DailyPerformance).where(DailyPerformance.symbol == "TCS")))
    assert len(perfs) == 1
    assert perfs[0].selected is True
    assert float(perfs[0].day_pnl_pct) == 4.0

    news = list(session.scalars(select(DailyNews).where(DailyNews.symbol == "TCS")))
    assert news
    assert any(row.is_filing for row in news)

    impact = session.scalar(select(DailyImpact).where(DailyImpact.symbol == "TCS"))
    assert impact is not None
    assert impact.engine == "rules"
    assert impact.takeaway
    assert "TCS" in impact.takeaway
    assert "Nifty" in (impact.market_context or "")
