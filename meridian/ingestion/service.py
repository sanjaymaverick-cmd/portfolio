from __future__ import annotations

from pathlib import Path
from shutil import copy2

from meridian.config import get_settings
from meridian.domain.models import ImportPreview, MappedRow
from meridian.ingestion.columns import detect_broker, infer_mapping
from meridian.ingestion.normalize import map_rows
from meridian.ingestion.pdf import read_pdf_tables
from meridian.ingestion.tabular import read_tabular
from meridian.storage.repositories import AccountRepo, HoldingRepo, ImportRepo


class ImportService:
    def __init__(self, session) -> None:  # noqa: ANN001
        self.session = session
        self.accounts = AccountRepo(session)
        self.holdings = HoldingRepo(session)
        self.jobs = ImportRepo(session)

    def preview(
        self,
        path: Path,
        *,
        mapping: dict[str, str] | None = None,
        broker: str | None = None,
    ) -> ImportPreview:
        headers, records = parse_statement(path)
        resolved_broker = broker or detect_broker(headers, path.name)
        resolved_mapping = mapping or infer_mapping(headers)
        rows = map_rows(records, resolved_mapping)
        accepted = sum(1 for row in rows if not row.error)
        rejected = len(rows) - accepted
        return ImportPreview(
            broker=resolved_broker,
            filename=path.name,
            headers=headers,
            mapping=resolved_mapping,
            rows=rows,
            accepted=accepted,
            rejected=rejected,
        )

    def commit(
        self,
        preview: ImportPreview,
        *,
        account_name: str,
        broker: str | None = None,
        source_path: Path | None = None,
    ) -> tuple[int, int]:
        broker_name = broker or preview.broker
        account = self.accounts.create(account_name, broker=broker_name)
        accepted = 0
        rejected = 0
        for row in preview.rows:
            if row.error:
                rejected += 1
                continue
            self.holdings.upsert(account, row, source="import")
            accepted += 1
        archived = None
        if source_path and source_path.exists():
            dest_dir = get_settings().import_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            archived = dest_dir / source_path.name
            try:
                copy2(source_path, archived)
            except OSError:
                archived = None
        self.jobs.record(
            account_id=account.id,
            broker=broker_name,
            filename=preview.filename,
            status="committed",
            accepted=accepted,
            rejected=rejected,
            notes=str(archived) if archived else None,
        )
        return accepted, rejected

    def add_manual(self, account_name: str, row: MappedRow, broker: str = "manual") -> None:
        account = self.accounts.create(account_name, broker=broker)
        self.holdings.upsert(account, row, source="manual")


def parse_statement(path: Path) -> tuple[list[str], list[dict]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf_tables(path)
    return read_tabular(path)
