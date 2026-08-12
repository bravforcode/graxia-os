#!/usr/bin/env python3
"""
Benchmark script for measuring query performance improvements.

This script measures the performance of common query patterns before and after
adding composite indexes. It helps validate that the indexes provide the expected
performance improvements (>50% for filtered list operations).

Usage:
    python backend/scripts/benchmark_queries.py --before  # Run before migration
    python backend/scripts/benchmark_queries.py --after   # Run after migration
    python backend/scripts/benchmark_queries.py --compare # Compare results
"""

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.models.assistant_task import AssistantTask
from app.models.contact import Contact
from app.models.email_thread import EmailThread
from app.models.opportunity import Opportunity


class QueryBenchmark:
    """Benchmark common query patterns."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.results: dict[str, dict[str, Any]] = {}
    
    async def run_query_benchmark(
        self, 
        name: str, 
        query: Any, 
        iterations: int = 10
    ) -> dict[str, Any]:
        """
        Run a query multiple times and collect timing statistics.
        
        Args:
            name: Name of the query being benchmarked
            query: SQLAlchemy query to execute
            iterations: Number of times to run the query
            
        Returns:
            Dictionary with timing statistics
        """
        timings = []
        
        # Warm-up run
        await self.session.execute(query)
        
        # Benchmark runs
        for _ in range(iterations):
            start = time.perf_counter()
            result = await self.session.execute(query)
            _ = result.scalars().all()  # Fetch all results
            end = time.perf_counter()
            timings.append((end - start) * 1000)  # Convert to milliseconds
        
        stats = {
            "name": name,
            "iterations": iterations,
            "min_ms": min(timings),
            "max_ms": max(timings),
            "mean_ms": statistics.mean(timings),
            "median_ms": statistics.median(timings),
            "stdev_ms": statistics.stdev(timings) if len(timings) > 1 else 0,
            "total_ms": sum(timings),
        }
        
        self.results[name] = stats
        return stats
    
    async def benchmark_opportunities(self) -> None:
        """Benchmark opportunity queries."""
        print("\n📊 Benchmarking Opportunities queries...")
        
        # Get a sample user_id
        user_result = await self.session.execute(
            select(Opportunity.user_id).limit(1)
        )
        user_id = user_result.scalar()
        
        if not user_id:
            print("⚠️  No opportunities found, skipping opportunity benchmarks")
            return
        
        # Query 1: Filter by user_id and status
        query1 = select(Opportunity).where(
            Opportunity.user_id == user_id,
            Opportunity.status == "found",
            Opportunity.is_deleted == False
        )
        await self.run_query_benchmark("opportunities_user_status", query1)
        
        # Query 2: Filter by status and order by score
        query2 = select(Opportunity).where(
            Opportunity.status == "scored",
            Opportunity.is_deleted == False
        ).order_by(Opportunity.total_score.desc())
        await self.run_query_benchmark("opportunities_status_score", query2)
        
        # Query 3: User's opportunity feed (ordered by created_at)
        query3 = select(Opportunity).where(
            Opportunity.user_id == user_id,
            Opportunity.is_deleted == False
        ).order_by(Opportunity.found_at.desc()).limit(50)
        await self.run_query_benchmark("opportunities_user_feed", query3)
        
        # Query 4: Filter by user and decision
        query4 = select(Opportunity).where(
            Opportunity.user_id == user_id,
            Opportunity.decision == "do_now",
            Opportunity.is_deleted == False
        )
        await self.run_query_benchmark("opportunities_user_decision", query4)
    
    async def benchmark_contacts(self) -> None:
        """Benchmark contact queries."""
        print("\n📊 Benchmarking Contacts queries...")
        
        # Get a sample user_id and company
        result = await self.session.execute(
            select(Contact.user_id, Contact.company)
            .where(Contact.company.isnot(None))
            .limit(1)
        )
        row = result.first()
        
        if not row:
            print("⚠️  No contacts found, skipping contact benchmarks")
            return
        
        user_id, company = row
        
        # Query 1: Filter by user_id and company
        query1 = select(Contact).where(
            Contact.user_id == user_id,
            Contact.company == company,
            Contact.is_deleted == False
        )
        await self.run_query_benchmark("contacts_user_company", query1)
        
        # Query 2: Get user's active contacts
        query2 = select(Contact).where(
            Contact.user_id == user_id,
            Contact.is_deleted == False
        ).limit(100)
        await self.run_query_benchmark("contacts_user_active", query2)
        
        # Query 3: Email lookup
        email_result = await self.session.execute(
            select(Contact.email).where(Contact.email.isnot(None)).limit(1)
        )
        email = email_result.scalar()
        
        if email:
            query3 = select(Contact).where(
                Contact.email == email,
                Contact.is_deleted == False
            )
            await self.run_query_benchmark("contacts_email_lookup", query3)
        
        # Query 4: Filter by user and contact type
        query4 = select(Contact).where(
            Contact.user_id == user_id,
            Contact.contact_type == "client",
            Contact.is_deleted == False
        )
        await self.run_query_benchmark("contacts_user_type", query4)
    
    async def benchmark_email_threads(self) -> None:
        """Benchmark email thread queries."""
        print("\n📊 Benchmarking Email Threads queries...")
        
        # Check if table has data
        count_result = await self.session.execute(
            select(EmailThread).limit(1)
        )
        if not count_result.scalar():
            print("⚠️  No email threads found, skipping email thread benchmarks")
            return
        
        # Query 1: Filter by status and order by last_message_at
        query1 = select(EmailThread).where(
            EmailThread.status == "unread"
        ).order_by(EmailThread.last_message_at.desc()).limit(50)
        await self.run_query_benchmark("email_threads_status_recent", query1)
        
        # Query 2: Filter by category and order by priority
        query2 = select(EmailThread).where(
            EmailThread.category == "important"
        ).order_by(EmailThread.priority.desc()).limit(50)
        await self.run_query_benchmark("email_threads_category_priority", query2)
        
        # Query 3: Urgent unread emails
        query3 = select(EmailThread).where(
            EmailThread.status == "unread",
            EmailThread.priority >= 8
        ).order_by(EmailThread.priority.desc())
        await self.run_query_benchmark("email_threads_urgent_unread", query3)
    
    async def benchmark_assistant_tasks(self) -> None:
        """Benchmark assistant task queries."""
        print("\n📊 Benchmarking Assistant Tasks queries...")
        
        # Get a sample user_id
        user_result = await self.session.execute(
            select(AssistantTask.user_id).limit(1)
        )
        user_id = user_result.scalar()
        
        if not user_id:
            print("⚠️  No assistant tasks found, skipping task benchmarks")
            return
        
        # Query 1: Filter by user_id and status
        query1 = select(AssistantTask).where(
            AssistantTask.user_id == user_id,
            AssistantTask.status == "pending"
        )
        await self.run_query_benchmark("tasks_user_status", query1)
        
        # Query 2: Filter by status and order by priority
        query2 = select(AssistantTask).where(
            AssistantTask.status == "pending"
        ).order_by(AssistantTask.priority.desc()).limit(50)
        await self.run_query_benchmark("tasks_status_priority", query2)
        
        # Query 3: User's upcoming tasks
        query3 = select(AssistantTask).where(
            AssistantTask.user_id == user_id
        ).order_by(AssistantTask.due_date.asc()).limit(50)
        await self.run_query_benchmark("tasks_user_upcoming", query3)
        
        # Query 4: Overdue tasks
        query4 = select(AssistantTask).where(
            AssistantTask.status == "pending",
            AssistantTask.due_date < datetime.utcnow()
        ).order_by(AssistantTask.due_date.asc())
        await self.run_query_benchmark("tasks_overdue", query4)
        
        # Query 5: User's pending tasks by priority
        query5 = select(AssistantTask).where(
            AssistantTask.user_id == user_id,
            AssistantTask.status == "pending"
        ).order_by(AssistantTask.priority.desc())
        await self.run_query_benchmark("tasks_user_pending_priority", query5)
    
    async def benchmark_explain_analyze(self) -> None:
        """Run EXPLAIN ANALYZE on key queries to show query plans."""
        print("\n🔍 Running EXPLAIN ANALYZE on key queries...")
        
        explains = {}
        
        # Get sample IDs
        user_result = await self.session.execute(
            select(Opportunity.user_id).limit(1)
        )
        user_id = user_result.scalar()
        
        if user_id:
            # Opportunity query with composite index
            query = f"""
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT * FROM opportunities 
            WHERE user_id = '{user_id}' AND status = 'found' AND is_deleted = false
            """
            result = await self.session.execute(text(query))
            explains["opportunities_user_status"] = result.scalar()
        
        self.results["explain_analyze"] = explains
    
    def print_results(self) -> None:
        """Print benchmark results in a formatted table."""
        print("\n" + "=" * 80)
        print("BENCHMARK RESULTS")
        print("=" * 80)
        
        for name, stats in self.results.items():
            if name == "explain_analyze":
                continue
            
            print(f"\n{stats['name']}")
            print(f"  Iterations: {stats['iterations']}")
            print(f"  Mean:       {stats['mean_ms']:.2f} ms")
            print(f"  Median:     {stats['median_ms']:.2f} ms")
            print(f"  Min:        {stats['min_ms']:.2f} ms")
            print(f"  Max:        {stats['max_ms']:.2f} ms")
            print(f"  Std Dev:    {stats['stdev_ms']:.2f} ms")
    
    def save_results(self, filename: str) -> None:
        """Save results to JSON file."""
        output_path = Path(__file__).parent / filename
        with open(output_path, "w") as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "results": self.results
            }, f, indent=2)
        print(f"\n💾 Results saved to: {output_path}")


def compare_results(before_file: str, after_file: str) -> None:
    """Compare before and after benchmark results."""
    before_path = Path(__file__).parent / before_file
    after_path = Path(__file__).parent / after_file
    
    if not before_path.exists() or not after_path.exists():
        print("❌ Missing benchmark files. Run with --before and --after first.")
        return
    
    with open(before_path) as f:
        before_data = json.load(f)
    
    with open(after_path) as f:
        after_data = json.load(f)
    
    print("\n" + "=" * 80)
    print("PERFORMANCE COMPARISON")
    print("=" * 80)
    
    before_results = before_data["results"]
    after_results = after_data["results"]
    
    improvements = []
    
    for name in before_results:
        if name == "explain_analyze" or name not in after_results:
            continue
        
        before_mean = before_results[name]["mean_ms"]
        after_mean = after_results[name]["mean_ms"]
        improvement = ((before_mean - after_mean) / before_mean) * 100
        
        improvements.append({
            "name": name,
            "before": before_mean,
            "after": after_mean,
            "improvement": improvement
        })
    
    # Sort by improvement percentage
    improvements.sort(key=lambda x: x["improvement"], reverse=True)
    
    print(f"\n{'Query':<40} {'Before':<12} {'After':<12} {'Improvement':<12}")
    print("-" * 80)
    
    for item in improvements:
        status = "✅" if item["improvement"] > 50 else "⚠️" if item["improvement"] > 0 else "❌"
        print(
            f"{item['name']:<40} "
            f"{item['before']:>10.2f}ms "
            f"{item['after']:>10.2f}ms "
            f"{status} {item['improvement']:>8.1f}%"
        )
    
    avg_improvement = statistics.mean([i["improvement"] for i in improvements])
    print("-" * 80)
    print(f"{'Average Improvement':<40} {'':<12} {'':<12} {avg_improvement:>8.1f}%")
    
    # Check acceptance criteria
    print("\n" + "=" * 80)
    print("ACCEPTANCE CRITERIA")
    print("=" * 80)
    
    passed = sum(1 for i in improvements if i["improvement"] > 50)
    total = len(improvements)
    
    print(f"\n✅ Queries with >50% improvement: {passed}/{total}")
    
    if avg_improvement > 50:
        print(f"✅ Average improvement: {avg_improvement:.1f}% (Target: >50%)")
    else:
        print(f"⚠️  Average improvement: {avg_improvement:.1f}% (Target: >50%)")


async def main():
    """Main benchmark execution."""
    parser = argparse.ArgumentParser(description="Benchmark query performance")
    parser.add_argument(
        "--before",
        action="store_true",
        help="Run benchmarks before migration"
    )
    parser.add_argument(
        "--after",
        action="store_true",
        help="Run benchmarks after migration"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare before and after results"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of iterations per query (default: 10)"
    )
    
    args = parser.parse_args()
    
    if args.compare:
        compare_results("benchmark_before.json", "benchmark_after.json")
        return
    
    if not args.before and not args.after:
        print("❌ Please specify --before, --after, or --compare")
        return
    
    # Create async engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        benchmark = QueryBenchmark(session)
        
        print("🚀 Starting query benchmarks...")
        print(f"   Iterations per query: {args.iterations}")
        
        # Run all benchmarks
        await benchmark.benchmark_opportunities()
        await benchmark.benchmark_contacts()
        await benchmark.benchmark_email_threads()
        await benchmark.benchmark_assistant_tasks()
        
        # Print results
        benchmark.print_results()
        
        # Save results
        filename = "benchmark_before.json" if args.before else "benchmark_after.json"
        benchmark.save_results(filename)
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
