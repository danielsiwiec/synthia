import argparse
import asyncio

import asyncpg

from synthia.agents.episodic.backfill import apply_backfill, plan_backfill
from synthia.main import Config


async def _run(apply: bool, all_threads: bool) -> None:
    config = Config()
    conn = await asyncpg.connect(config.postgres_connection_string)
    try:
        plan = await plan_backfill(conn, attachments_only=not all_threads)
        print(f"Proposed links: {len(plan)} (attachments_only={not all_threads})\n")
        for entry in plan:
            flag = " [ambiguous→timestamp]" if entry["ambiguous"] else ""
            print(f"  {entry['conversation_id']} -> thread {entry['thread_id']}{flag}")
            print(f"      first prompt: {entry['first_prompt']!r}")

        if not apply:
            print("\nDry run. Re-run with --apply to write these thread_ids.")
            return

        updated = await apply_backfill(conn, plan)
        print(f"\nApplied {updated} updates.")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill conversations.thread_id from transcripts.")
    parser.add_argument("--apply", action="store_true", help="Write the changes (default is dry run).")
    parser.add_argument(
        "--all-threads",
        action="store_true",
        help="Match all threads, not only those with attachments.",
    )
    args = parser.parse_args()
    asyncio.run(_run(apply=args.apply, all_threads=args.all_threads))


if __name__ == "__main__":
    main()
