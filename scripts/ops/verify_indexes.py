#!/usr/bin/env python3
"""
Index verification script for TASK 2.3.

This script verifies that all required indexes have been created correctly
and provides information about their size and usage.

Usage:
    python backend/scripts/verify_indexes.py
"""

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings


class IndexVerifier:
    """Verify database indexes."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.expected_indexes = {
            "opportunities": [
                "idx_opportunities_user_status",
                "idx_opportunities_status_score",
                "idx_opportunities_user_created",
                "idx_opportunities_user_decision",
            ],
            "contacts": [
                "idx_contacts_user_company",
                "idx_contacts_user_active",
                "idx_contacts_email_active",
                "idx_contacts_user_type",
            ],
            "email_threads": [
                "idx_email_threads_status_last_msg",
                "idx_email_threads_category_priority",
                "idx_email_threads_urgent_unread",
            ],
            "assistant_tasks": [
                "idx_assistant_tasks_user_status",
                "idx_assistant_tasks_status_priority",
                "idx_assistant_tasks_user_due",
                "idx_assistant_tasks_overdue",
                "idx_assistant_tasks_user_pending_priority",
            ],
        }
    
    async def get_table_indexes(self, table_name: str) -> list[dict[str, Any]]:
        """Get all indexes for a table."""
        query = text("""
            SELECT
                i.relname as index_name,
                a.attname as column_name,
                ix.indisunique as is_unique,
                ix.indisprimary as is_primary,
                pg_get_indexdef(ix.indexrelid) as index_definition,
                pg_size_pretty(pg_relation_size(i.oid)) as index_size,
                pg_stat_get_numscans(i.oid) as num_scans,
                pg_stat_get_tuples_returned(i.oid) as tuples_read,
                pg_stat_get_tuples_fetched(i.oid) as tuples_fetched
            FROM
                pg_class t,
                pg_class i,
                pg_index ix,
                pg_attribute a
            WHERE
                t.oid = ix.indrelid
                AND i.oid = ix.indexrelid
                AND a.attrelid = t.oid
                AND a.attnum = ANY(ix.indkey)
                AND t.relkind = 'r'
                AND t.relname = :table_name
            ORDER BY
                i.relname,
                a.attnum
        """)
        
        result = await self.session.execute(query, {"table_name": table_name})
        rows = result.fetchall()
        
        # Group by index name
        indexes = {}
        for row in rows:
            index_name = row[0]
            if index_name not in indexes:
                indexes[index_name] = {
                    "name": row[0],
                    "columns": [],
                    "is_unique": row[2],
                    "is_primary": row[3],
                    "definition": row[4],
                    "size": row[5],
                    "num_scans": row[6],
                    "tuples_read": row[7],
                    "tuples_fetched": row[8],
                }
            indexes[index_name]["columns"].append(row[1])
        
        return list(indexes.values())
    
    async def verify_table_indexes(self, table_name: str) -> dict[str, Any]:
        """Verify indexes for a specific table."""
        print(f"\n📋 Verifying indexes for table: {table_name}")
        print("-" * 80)
        
        expected = self.expected_indexes.get(table_name, [])
        indexes = await self.get_table_indexes(table_name)
        
        found_indexes = {idx["name"] for idx in indexes}
        expected_set = set(expected)
        
        missing = expected_set - found_indexes
        extra = found_indexes - expected_set
        
        # Filter to show only our new indexes
        our_indexes = [idx for idx in indexes if idx["name"] in expected_set]
        
        # Print found indexes
        for idx in our_indexes:
            status = "✅"
            print(f"{status} {idx['name']}")
            print(f"   Columns: {', '.join(idx['columns'])}")
            print(f"   Size: {idx['size']}")
            print(f"   Scans: {idx['num_scans']}")
            if idx['definition']:
                # Show partial index condition if exists
                if "WHERE" in idx['definition']:
                    where_clause = idx['definition'].split("WHERE", 1)[1].strip()
                    print(f"   Condition: WHERE {where_clause}")
        
        # Print missing indexes
        if missing:
            print(f"\n❌ Missing indexes:")
            for idx_name in missing:
                print(f"   - {idx_name}")
        
        # Print summary
        print(f"\n📊 Summary:")
        print(f"   Expected: {len(expected)}")
        print(f"   Found: {len(our_indexes)}")
        print(f"   Missing: {len(missing)}")
        
        return {
            "table": table_name,
            "expected": len(expected),
            "found": len(our_indexes),
            "missing": list(missing),
            "indexes": our_indexes,
        }
    
    async def get_database_size_info(self) -> dict[str, Any]:
        """Get database size information."""
        query = text("""
            SELECT
                pg_size_pretty(pg_database_size(current_database())) as db_size,
                pg_size_pretty(sum(pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename)))::bigint) as tables_size,
                pg_size_pretty(sum(pg_indexes_size(quote_ident(schemaname) || '.' || quote_ident(tablename)))::bigint) as indexes_size
            FROM pg_tables
            WHERE schemaname = 'public'
        """)
        
        result = await self.session.execute(query)
        row = result.fetchone()
        
        return {
            "database_size": row[0],
            "tables_size": row[1],
            "indexes_size": row[2],
        }
    
    async def get_table_sizes(self) -> list[dict[str, Any]]:
        """Get size information for each table."""
        query = text("""
            SELECT
                tablename,
                pg_size_pretty(pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename))) as total_size,
                pg_size_pretty(pg_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename))) as table_size,
                pg_size_pretty(pg_indexes_size(quote_ident(schemaname) || '.' || quote_ident(tablename))) as indexes_size,
                pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename)) as total_bytes
            FROM pg_tables
            WHERE schemaname = 'public'
                AND tablename IN ('opportunities', 'contacts', 'email_threads', 'assistant_tasks')
            ORDER BY total_bytes DESC
        """)
        
        result = await self.session.execute(query)
        rows = result.fetchall()
        
        return [
            {
                "table": row[0],
                "total_size": row[1],
                "table_size": row[2],
                "indexes_size": row[3],
            }
            for row in rows
        ]
    
    async def check_index_usage(self) -> list[dict[str, Any]]:
        """Check which indexes are being used."""
        query = text("""
            SELECT
                schemaname,
                tablename,
                indexname,
                idx_scan as scans,
                idx_tup_read as tuples_read,
                idx_tup_fetch as tuples_fetched,
                pg_size_pretty(pg_relation_size(indexrelid)) as size
            FROM pg_stat_user_indexes
            WHERE schemaname = 'public'
                AND tablename IN ('opportunities', 'contacts', 'email_threads', 'assistant_tasks')
                AND indexname LIKE 'idx_%'
            ORDER BY idx_scan DESC
        """)
        
        result = await self.session.execute(query)
        rows = result.fetchall()
        
        return [
            {
                "schema": row[0],
                "table": row[1],
                "index": row[2],
                "scans": row[3],
                "tuples_read": row[4],
                "tuples_fetched": row[5],
                "size": row[6],
            }
            for row in rows
        ]
    
    async def verify_all(self) -> dict[str, Any]:
        """Run all verification checks."""
        print("=" * 80)
        print("INDEX VERIFICATION REPORT")
        print("=" * 80)
        
        # Verify indexes for each table
        results = {}
        for table_name in self.expected_indexes.keys():
            results[table_name] = await self.verify_table_indexes(table_name)
        
        # Get database size info
        print("\n" + "=" * 80)
        print("DATABASE SIZE INFORMATION")
        print("=" * 80)
        
        size_info = await self.get_database_size_info()
        print(f"\n📊 Overall:")
        print(f"   Database Size: {size_info['database_size']}")
        print(f"   Tables Size:   {size_info['tables_size']}")
        print(f"   Indexes Size:  {size_info['indexes_size']}")
        
        # Get table sizes
        print(f"\n📊 Table Sizes:")
        table_sizes = await self.get_table_sizes()
        for table in table_sizes:
            print(f"\n   {table['table']}:")
            print(f"      Total:   {table['total_size']}")
            print(f"      Table:   {table['table_size']}")
            print(f"      Indexes: {table['indexes_size']}")
        
        # Check index usage
        print("\n" + "=" * 80)
        print("INDEX USAGE STATISTICS")
        print("=" * 80)
        
        usage_stats = await self.check_index_usage()
        
        # Group by table
        by_table = {}
        for stat in usage_stats:
            table = stat["table"]
            if table not in by_table:
                by_table[table] = []
            by_table[table].append(stat)
        
        for table, stats in by_table.items():
            print(f"\n📊 {table}:")
            # Show only our new indexes
            our_stats = [s for s in stats if s["index"] in self.expected_indexes.get(table, [])]
            if our_stats:
                for stat in our_stats:
                    print(f"   {stat['index']}")
                    print(f"      Scans: {stat['scans']}")
                    print(f"      Size:  {stat['size']}")
            else:
                print("   (No usage data yet - indexes may be newly created)")
        
        # Final summary
        print("\n" + "=" * 80)
        print("VERIFICATION SUMMARY")
        print("=" * 80)
        
        total_expected = sum(len(indexes) for indexes in self.expected_indexes.values())
        total_found = sum(r["found"] for r in results.values())
        total_missing = sum(len(r["missing"]) for r in results.values())
        
        print(f"\n✅ Total Expected Indexes: {total_expected}")
        print(f"✅ Total Found Indexes:    {total_found}")
        
        if total_missing > 0:
            print(f"❌ Total Missing Indexes:  {total_missing}")
            return {"status": "failed", "results": results}
        else:
            print(f"✅ All indexes verified successfully!")
            return {"status": "passed", "results": results}


async def main():
    """Main verification execution."""
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
        verifier = IndexVerifier(session)
        result = await verifier.verify_all()
        
        # Exit with appropriate code
        exit_code = 0 if result["status"] == "passed" else 1
        return exit_code
    
    await engine.dispose()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
