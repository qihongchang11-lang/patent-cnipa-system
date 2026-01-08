"""
Phase 2.1 verification script: interactive flow (stateful editing + recheck).

Creates a job via the existing pipeline, then:
- GET /jobs/{job_id}/document
- PATCH /jobs/{job_id}/edit (claim:1) with optimistic locking
- POST /jobs/{job_id}/recheck
Asserts version increment + audit indicates human edit + report persists.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "src"))

    from fastapi.testclient import TestClient
    import api_main

    client = TestClient(api_main.app)

    payload = {
        "title": "一种交互式专利编辑与质检系统",
        "technical_field": "专利撰写辅助与质量检查",
        "background": "现有专利撰写修改成本高，缺少即时复检能力。",
        "invention_content": "提供一种可对权利要求进行逐条编辑并可按需复检的系统与方法。",
        "embodiments": "实施例：用户修改权利要求1后触发复检，系统输出更新后的质检报告。",
        "enable_checks": True,
    }

    # create job via existing endpoint (background task will not run inside TestClient reliably)
    r = client.post("/process/text", json=payload)
    r.raise_for_status()
    job_id = r.json()["job_id"]

    # run the background task synchronously to persist outputs
    api_main.process_patent_text_sync(job_id, payload)

    # load document + version
    r = client.get(f"/jobs/{job_id}/document")
    r.raise_for_status()
    doc_version = r.json()["document_version"]
    assert doc_version >= 1

    # edit claim:1 (simulate human fix)
    edit_req = {
        "section": "claims",
        "target": "claim:1",
        "value": "一种专利撰写辅助系统，其特征在于，包括：文本解析模块、编辑模块、质量复检模块以及导出模块。",
        "if_version": doc_version,
    }
    r = client.patch(f"/jobs/{job_id}/edit", json=edit_req)
    r.raise_for_status()
    new_version = r.json()["document_version"]
    assert new_version == doc_version + 1

    # recheck only
    r = client.post(f"/jobs/{job_id}/recheck")
    r.raise_for_status()
    report = r.json()
    assert report.get("document_version") == new_version
    assert (report.get("audit") or {}).get("document_version") == new_version
    assert (report.get("audit") or {}).get("run_trace_id")
    assert ((report.get("audit") or {}).get("last_edit") or {}).get("actor") == "human_edit"
    assert report.get("kpis") is not None

    # no secrets
    api_key = (os.environ.get("LLM_API_KEY") or "").strip()
    if api_key:
        blob = json.dumps(report, ensure_ascii=False)
        assert api_key not in blob

    print("OK job_id=", job_id, "version=", new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
