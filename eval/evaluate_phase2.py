import asyncio
import json
import random
import statistics
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.data_loader import DataLoader
from app.services.ai_service import AIService

DATASET_PATH = ROOT_DIR / "eval" / "data" / "dataset_cegahscam_master.xlsx"
RESULTS_PATH = ROOT_DIR / "eval" / "data" / "phase2_results.json"

STRATA_QUOTAS = {
    "Bukan Scam (Percakapan Normal)": 7,
    "Undian Palsu (Fake Reward)": 3,
    "Spam Tidak Terklasifikasi": 2,
    "Promo / Potensi Phishing Provider": 2,
    "Modus Penipuan Transfer Uang": 2,
    "Phishing Kredensial / Hadiah": 2,
    "Modus Salah Transfer Uang": 2,
    "Modus Sniffing / Malware APK": 2,
    "Penawaran Pinjol / Kredit Ilegal": 1,
    "Phishing Peringatan Bank / Perubahan Tarif": 1,
    "Penipuan Loker / Tugas Berbayar (Task Scam)": 1,
}


def load_xlsx_rows(path: Path) -> List[Dict[str, str]]:
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as z:
        sst_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        sst = [
            "".join(t.text or "" for t in si.iter(f"{ns}t"))
            for si in sst_root
        ]
        sheet_root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        xml_rows = sheet_root.findall(f".//{ns}row")

        records: List[Dict[str, str]] = []
        for idx, r in enumerate(xml_rows[1:], start=2):
            cell_dict: Dict[str, str] = {}
            for c in r.findall(f"{ns}c"):
                col = "".join(ch for ch in c.get("r", "") if ch.isalpha())
                v = c.find(f"{ns}v")
                val = v.text if v is not None else ""
                if c.get("t") == "s" and val.isdigit():
                    val = sst[int(val)]
                cell_dict[col] = val
            records.append(
                {
                    "row_id": str(idx),
                    "label": cell_dict.get("A", "0"),
                    "text": cell_dict.get("B", ""),
                    "pattern": cell_dict.get("F", ""),
                    "expected_sop": cell_dict.get("G", ""),
                }
            )
        return records


def select_stratified_sample(
    records: List[Dict[str, str]],
    loader: DataLoader,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    by_pattern: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for rec in records:
        kb_matches = loader.match_knowledge_base(rec["text"], min_keywords=3)
        enriched = dict(rec)
        enriched["kb_matches"] = kb_matches
        enriched["has_kb_match"] = len(kb_matches) > 0
        by_pattern[rec["pattern"]].append(enriched)

    selected: List[Dict[str, Any]] = []
    for pattern, quota in STRATA_QUOTAS.items():
        pool = by_pattern.get(pattern, [])
        if not pool:
            continue
        matched_pool = [r for r in pool if r["has_kb_match"]]
        unmatched_pool = [r for r in pool if not r["has_kb_match"]]
        rng.shuffle(matched_pool)
        rng.shuffle(unmatched_pool)

        if pattern == "Bukan Scam (Percakapan Normal)":
            chosen = pool[:quota]
            rng.shuffle(pool)
            chosen = pool[:quota]
        else:
            take_matched = min(len(matched_pool), max(1, (quota + 1) // 2))
            take_unmatched = quota - take_matched
            chosen = matched_pool[:take_matched] + unmatched_pool[:take_unmatched]
            if len(chosen) < quota:
                rem = [r for r in pool if r not in chosen]
                chosen.extend(rem[: quota - len(chosen)])

        selected.extend(chosen)

    return selected


def compute_metrics(
    items: List[Dict[str, Any]],
    score_key: str,
    threshold: int,
    scenario: str,
) -> Dict[str, Any]:
    tp = fp = tn = fn = 0
    for item in items:
        pattern = item["pattern"]
        if scenario == "B_exclude_spam_promo" and pattern in (
            "Spam Tidak Terklasifikasi",
            "Promo / Potensi Phishing Provider",
        ):
            continue

        if scenario == "B_spam_promo_as_non_scam" and pattern in (
            "Spam Tidak Terklasifikasi",
            "Promo / Potensi Phishing Provider",
        ):
            y_true = 0
        else:
            y_true = int(item["label"])

        score = item[score_key]["risk_score"]
        y_pred = 1 if score >= threshold else 0

        if y_true == 1 and y_pred == 1:
            tp += 1
        elif y_true == 0 and y_pred == 1:
            fp += 1
        elif y_true == 0 and y_pred == 0:
            tn += 1
        elif y_true == 1 and y_pred == 0:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    accuracy = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) > 0 else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "total": tp + fp + tn + fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


async def call_with_retry(
    ai: AIService,
    text: str,
    use_kb: bool,
    max_retries: int = 3,
) -> tuple[Dict[str, Any], float]:
    for attempt in range(1, max_retries + 1):
        t0 = time.perf_counter()
        try:
            res = await ai.analyze_text_and_image(
                text,
                None,
                use_knowledge_base=use_kb,
            )
            elapsed = time.perf_counter() - t0
            return res, round(elapsed, 3)
        except Exception as err:
            elapsed = time.perf_counter() - t0
            print(f"  [Attempt {attempt}/{max_retries}] Error after {elapsed:.2f}s: {err}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(5 * attempt)
    raise RuntimeError("Unreachable")


async def main() -> None:
    loader = DataLoader()
    ai = AIService(loader)
    records = load_xlsx_rows(DATASET_PATH)
    sample = select_stratified_sample(records, loader, seed=42)

    existing: Dict[str, Any] = {}
    if RESULTS_PATH.exists():
        try:
            saved = json.loads(RESULTS_PATH.read_text("utf-8"))
            for item in saved.get("items", []):
                existing[item["row_id"]] = item
        except Exception:
            existing = {}

    results_items: List[Dict[str, Any]] = []
    kb_matched_count = sum(1 for s in sample if s["has_kb_match"])
    print(
        f"Selected {len(sample)} stratified rows "
        f"({kb_matched_count} rows match KB >= 3 keywords)."
    )

    for idx, item in enumerate(sample, start=1):
        row_id = item["row_id"]
        if row_id in existing and "baseline" in existing[row_id] and "optimized" in existing[row_id]:
            print(f"[{idx}/{len(sample)}] Row {row_id} ({item['pattern']}): cached")
            results_items.append(existing[row_id])
            continue

        print(
            f"[{idx}/{len(sample)}] Row {row_id} | Label={item['label']} | "
            f"Pattern={item['pattern']} | KB_Match={item['has_kb_match']}"
        )
        base_res, base_lat = await call_with_retry(ai, item["text"], use_kb=False)
        await asyncio.sleep(3.5)

        if item["has_kb_match"]:
            opt_res, opt_lat = await call_with_retry(ai, item["text"], use_kb=True)
            await asyncio.sleep(3.5)
        else:
            opt_res, opt_lat = base_res, base_lat

        entry = {
            "row_id": row_id,
            "label": item["label"],
            "pattern": item["pattern"],
            "expected_sop": item["expected_sop"],
            "has_kb_match": item["has_kb_match"],
            "kb_matches": item["kb_matches"],
            "baseline": {
                "risk_score": base_res["risk_score"],
                "risk_category": base_res["risk_category"],
                "scam_type": base_res["scam_type"],
                "reasons": base_res["reasons"],
                "recommendations": base_res["recommendations"],
                "official_contact": base_res["official_contact"],
                "latency_s": base_lat,
            },
            "optimized": {
                "risk_score": opt_res["risk_score"],
                "risk_category": opt_res["risk_category"],
                "scam_type": opt_res["scam_type"],
                "reasons": opt_res["reasons"],
                "recommendations": opt_res["recommendations"],
                "official_contact": opt_res["official_contact"],
                "latency_s": opt_lat,
            },
        }
        results_items.append(entry)
        RESULTS_PATH.write_text(
            json.dumps({"items": results_items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    summary: Dict[str, Any] = {"thresholds": {}}
    for th in (40, 50, 60):
        summary["thresholds"][str(th)] = {
            "scenario_A_strict": {
                "baseline": compute_metrics(results_items, "baseline", th, "A_strict"),
                "optimized": compute_metrics(results_items, "optimized", th, "A_strict"),
            },
            "scenario_B_fraud_only": {
                "baseline": compute_metrics(results_items, "baseline", th, "B_exclude_spam_promo"),
                "optimized": compute_metrics(results_items, "optimized", th, "B_exclude_spam_promo"),
            },
            "scenario_B_spam_promo_non_scam": {
                "baseline": compute_metrics(results_items, "baseline", th, "B_spam_promo_as_non_scam"),
                "optimized": compute_metrics(results_items, "optimized", th, "B_spam_promo_as_non_scam"),
            },
        }

    base_lats = [x["baseline"]["latency_s"] for x in results_items]
    opt_lats = [x["optimized"]["latency_s"] for x in results_items if x["has_kb_match"]]

    summary["latency"] = {
        "baseline_mean_s": round(statistics.mean(base_lats), 3),
        "baseline_p50_s": round(statistics.median(base_lats), 3),
        "baseline_max_s": round(max(base_lats), 3),
        "optimized_kb_mean_s": round(statistics.mean(opt_lats), 3) if opt_lats else 0.0,
    }

    full_output = {
        "sample_size": len(results_items),
        "kb_matched_rows": kb_matched_count,
        "summary": summary,
        "items": results_items,
    }
    RESULTS_PATH.write_text(
        json.dumps(full_output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n=== EVALUATION SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
