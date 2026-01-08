"""
Minimal state persistence layer for Phase 2.1 (human-in-the-loop).

Storage layout (per job):
results/<job_id>/
  patent_metadata.json          # persisted PatentDocument (JSON)
  quality_report.json           # latest report
  edit_events.jsonl             # append-only events (one JSON per line)
results/<job_id>_results.zip    # packaged artifacts (updated on save_results)
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.patent_document import PatentDocument


class JobNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class EditSummary:
    counts_by_actor: Dict[str, int]
    last_event: Optional[Dict[str, Any]]


class StateManager:
    def __init__(self, results_dir: Optional[Path] = None):
        self.results_dir = results_dir or Path("results")

    def job_dir(self, job_id: str) -> Path:
        return self.results_dir / job_id

    def load(self, job_id: str) -> PatentDocument:
        job_dir = self.job_dir(job_id)
        metadata_path = job_dir / "patent_metadata.json"
        if not metadata_path.exists():
            raise JobNotFoundError(f"Job {job_id} not found (missing {metadata_path})")
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        # tolerate missing fields via defaults
        return PatentDocument.model_validate(data)

    def save(self, job_id: str, patent_doc: PatentDocument) -> None:
        job_dir = self.job_dir(job_id)
        if not job_dir.exists():
            raise JobNotFoundError(f"Job {job_id} not found (missing {job_dir})")

        patent_doc.document_version = int(getattr(patent_doc, "document_version", 1) or 1) + 1
        metadata_path = job_dir / "patent_metadata.json"
        metadata_path.write_text(
            json.dumps(patent_doc.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append_edit_event(self, job_id: str, event: Dict[str, Any]) -> None:
        job_dir = self.job_dir(job_id)
        if not job_dir.exists():
            raise JobNotFoundError(f"Job {job_id} not found (missing {job_dir})")
        path = job_dir / "edit_events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def get_edit_summary(self, job_id: str) -> EditSummary:
        path = self.job_dir(job_id) / "edit_events.jsonl"
        if not path.exists():
            return EditSummary(counts_by_actor={}, last_event=None)
        counts: Dict[str, int] = {}
        last: Optional[Dict[str, Any]] = None
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                actor = str(ev.get("actor") or "")
                if actor:
                    counts[actor] = counts.get(actor, 0) + 1
                last = ev
        return EditSummary(counts_by_actor=counts, last_event=last)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def sha256_text(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

