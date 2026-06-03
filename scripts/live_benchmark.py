import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.models import FieldType, SchemaField  # noqa: E402
from app.scraper_recovery_integration import scrape_url_with_recovery  # noqa: E402

# Default sandbox targets
DEFAULT_TARGETS = [
    {
        "url": "http://quotes.toscrape.com",
        "intent": "Extract quotes and authors",
        "schema": [
            {"name": "text", "field_type": "string", "description": "The quote content text"},
            {"name": "author", "field_type": "string", "description": "The author of the quote"},
        ],
    },
    {
        "url": "http://quotes.toscrape.com/tableful/",
        "intent": "Extract tableful quotes",
        "schema": [
            {"name": "text", "field_type": "string", "description": "Quote text"},
            {"name": "author", "field_type": "string", "description": "Author"},
        ],
    },
]


async def run_benchmark(targets, min_score, max_attempts):
    print("======================================================================")
    print("🌟 STARTING DATA FORGE LIVE EXTRACTION BENCHMARK RUNNER")
    print("======================================================================")
    print(f"Loaded {len(targets)} benchmark targets.\n")

    results_summary = []
    total_start = time.time()

    for idx, target in enumerate(targets, start=1):
        url = target["url"]
        intent = target["intent"]
        schema = [
            SchemaField(
                name=f["name"],
                field_type=FieldType(f["field_type"]),
                description=f.get("description", ""),
                required=f.get("required", True),
            )
            for f in target["schema"]
        ]

        print(f"[{idx}/{len(targets)}] Scraping: {url}")
        print(f"      Intent: '{intent}'")

        start_time = time.time()
        try:
            records, stats = await scrape_url_with_recovery(
                url=url, schema_fields=schema, min_record_score=min_score, user_intent=intent, max_recovery_attempts=max_attempts
            )
            elapsed = time.time() - start_time

            success = stats.get("success", False) or len(records) > 0
            attempts = stats.get("attempts", 1)
            recoveries = stats.get("recovery_attempts", 0)

            results_summary.append(
                {
                    "url": url,
                    "success": success,
                    "runtime_sec": elapsed,
                    "records_count": len(records),
                    "attempts": attempts,
                    "recoveries": recoveries,
                    "error": stats.get("final_failure_category") or "None",
                }
            )

            status_str = "\033[92mSUCCESS\033[0m" if success else "\033[91mFAILED\033[0m"
            print(f"      Status: {status_str} | Records: {len(records)} | Runtime: {elapsed:.2f}s | Attempts: {attempts}")

        except Exception as e:
            elapsed = time.time() - start_time
            results_summary.append(
                {
                    "url": url,
                    "success": False,
                    "runtime_sec": elapsed,
                    "records_count": 0,
                    "attempts": 1,
                    "recoveries": 0,
                    "error": str(e),
                }
            )
            print(f"      \033[91mError occurred: {e}\033[0m")
        print("-" * 70)

    total_duration = time.time() - total_start

    # Compute aggregate metrics
    total_targets = len(results_summary)
    successful_runs = sum(1 for r in results_summary if r["success"])
    success_rate = (successful_runs / total_targets * 100) if total_targets > 0 else 0
    avg_runtime = (sum(r["runtime_sec"] for r in results_summary) / total_targets) if total_targets > 0 else 0
    total_records = sum(r["records_count"] for r in results_summary)
    total_attempts = sum(r["attempts"] for r in results_summary)
    total_recoveries = sum(r["recoveries"] for r in results_summary)

    # Draw premium summary console table
    print("\n" + "=" * 70)
    print("📊 DATA FORGE LIVE BENCHMARK AGGREGATE METRICS SUMMARY")
    print("=" * 70)
    print(f"  • Overall Success Rate   : {success_rate:.1f}% ({successful_runs}/{total_targets} URLs)")
    print(f"  • Average Scrape Runtime : {avg_runtime:.2f} seconds")
    print(f"  • Total Extracted Records: {total_records} records")
    print(f"  • Cooldown / Retries Done: {total_recoveries} recoveries (out of {total_attempts} total attempts)")
    print(f"  • Total Benchmark Time   : {total_duration:.2f} seconds")
    print("=" * 70 + "\n")

    # Detailed target table
    print(f"{'Target URL':<40} | {'Status':<8} | {'Records':<7} | {'Time':<6} | {'Attempts':<8}")
    print("-" * 75)
    for r in results_summary:
        short_url = r["url"] if len(r["url"]) <= 38 else r["url"][:35] + "..."
        status_lbl = "OK" if r["success"] else "FAIL"
        print(f"{short_url:<40} | {status_lbl:<8} | {r['records_count']:<7} | {r['runtime_sec']:.1f}s  | {r['attempts']:<8}")
    print("-" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataForge Scraper Live Benchmark Utility")
    parser.add_argument("--url", type=str, help="Single target URL to benchmark")
    parser.add_argument("--intent", type=str, default="Extract information", help="User intent for custom URL")
    parser.add_argument("--min-score", type=float, default=0.35, help="Minimum record score barrier")
    parser.add_argument("--max-attempts", type=int, default=3, help="Max retry attempts for failures")
    args = parser.parse_args()

    # Determine targets
    if args.url:
        targets = [
            {
                "url": args.url,
                "intent": args.intent,
                "schema": [{"name": "title", "field_type": "string", "description": "Title or main text"}],
            }
        ]
    else:
        targets = DEFAULT_TARGETS

    asyncio.run(run_benchmark(targets, args.min_score, args.max_attempts))
