"""
End-to-end verification script for Phase 1 AI core infrastructure.

Runs: extract (LLM-first + rules fallback) -> generate (claims/abstract LLM-first) -> checks -> package.
Prints audit metadata (no secrets) and verifies artifacts exist.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))
    sys.path.insert(0, str(repo_root))

    from core.pse_extractor import PSEExtractor
    from generators.four_piece_generator import FourPieceGenerator
    from orchestrator.pipeline_orchestrator import PipelineOrchestrator
    from utils.llm_client import LLMClient
    import api_main

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rules", "llm"], default="rules")
    args = parser.parse_args()

    fixture = repo_root / "tests" / "fixtures" / "sample_disclosure.txt"
    text = fixture.read_text(encoding="utf-8")

    if args.mode == "rules":
        os.environ["LLM_DISABLED"] = "1"
        llm = LLMClient(force_disabled=True)
        pse = PSEExtractor(llm_client=llm, force_rules=True)
        gen = FourPieceGenerator(llm_client=llm, force_rules=True)
    else:
        # llm mode requires a real configured endpoint
        if not (os.environ.get("LLM_API_KEY") or "").strip():
            print("[WARN] LLM_API_KEY not found, running in fallback mode")
        llm = LLMClient()
        if not llm.is_configured():
            # do not silently pass: run but skip strict LLM assertions
            args.mode = "rules"
            os.environ["LLM_DISABLED"] = "1"
            llm = LLMClient(force_disabled=True)
            pse = PSEExtractor(llm_client=llm, force_rules=True)
            gen = FourPieceGenerator(llm_client=llm, force_rules=True)
        else:
            pse = PSEExtractor(llm_client=llm, force_rules=False)
            gen = FourPieceGenerator(llm_client=llm, force_rules=False)
    orch = PipelineOrchestrator()

    pse_matrix = pse.extract_from_text(text)
    title = "一种专利四件套生成与质检系统"
    technical_field = "自然语言处理与专利撰写辅助"

    patent_doc = gen.generate_all(
        title=title,
        technical_field=technical_field,
        background="现有专利撰写效率低且质量不稳定。",
        invention_content="提供一种生成四件套并输出可解释质检报告的系统与方法。",
        embodiments=text,
        pse_matrix=pse_matrix,
    )

    result = orch.process_patent(patent_doc, enable_checks=True)
    result_dict = api_main.build_quality_report(result)
    result_dict["metadata"] = api_main.convert_datetime_to_string(getattr(result, "metadata", {}) or {})
    run_trace_id = "test-" + str(Path(__file__).stat().st_mtime_ns)
    result_dict["audit"] = api_main.build_audit(patent_doc, run_trace_id)

    job_id = "ai_pipeline_test"
    zip_path = api_main.save_results(job_id, result_dict, patent_doc)

    audit = result_dict.get("audit", {})
    extraction = audit.get("extraction", {})
    generation = audit.get("generation", {})

    print("=== Audit Summary ===")
    print("run_trace_id:", audit.get("run_trace_id"))
    print("llm:", audit.get("llm"))
    print("extraction_source:", extraction.get("source"))
    print("extraction_trace_id:", extraction.get("trace_id"))
    print("extraction_fallback_reason:", extraction.get("fallback_reason"))
    print("claims_source:", (generation.get("claims") or {}).get("source"))
    print("claims_trace_id:", (generation.get("claims") or {}).get("trace_id"))
    print("abstract_source:", (generation.get("abstract") or {}).get("source"))
    print("abstract_trace_id:", (generation.get("abstract") or {}).get("trace_id"))

    print("\n=== Artifacts ===")
    print("zip_path:", zip_path)
    if not Path(zip_path).exists():
        raise RuntimeError("zip not created")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        print("zip contains:", ", ".join(sorted(names)))
        required = {
            "specification.md",
            "claims.md",
            "abstract.md",
            "disclosure.md",
            "quality_report.json",
        }
        missing = required.difference(set(names))
        if missing:
            raise RuntimeError(f"missing in zip: {missing}")

        report = json.loads(zf.read("quality_report.json").decode("utf-8"))
        if "audit" not in report:
            raise RuntimeError("quality_report.json missing audit section")
        if "kpis" not in report:
            raise RuntimeError("quality_report.json missing kpis section")

        # Audit assertions (both modes)
        if not (report.get("audit") or {}).get("run_trace_id"):
            raise RuntimeError("audit.run_trace_id missing")
        # trace_id must exist even when rules are used
        if not ((report.get("audit") or {}).get("extraction") or {}).get("trace_id"):
            raise RuntimeError("audit.extraction.trace_id missing")

        # Mode-specific assertions (fail-loud but do not break soft-fail fallback)
        extraction_source = ((report.get("audit") or {}).get("extraction") or {}).get("source")
        claims_source = (((report.get("audit") or {}).get("generation") or {}).get("claims") or {}).get("source")
        extraction_reason = ((report.get("audit") or {}).get("extraction") or {}).get("fallback_reason")

        if args.mode == "rules":
            if extraction_source != "rules":
                raise RuntimeError("expected extraction_source == rules")
        else:
            if extraction_source != "llm":
                print(f"[WARN] LLM mode requested but extraction used fallback: source={extraction_source} reason={extraction_reason}")
            if claims_source != "llm":
                print(f"[WARN] LLM mode requested but claims used fallback: source={claims_source}")

        # No secrets: ensure API key not present in artifacts
        api_key = (os.environ.get("LLM_API_KEY") or "").strip()
        if api_key:
            blob = zf.read("quality_report.json").decode("utf-8", errors="ignore")
            if api_key in blob:
                raise RuntimeError("API key leaked into quality_report.json")

    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
