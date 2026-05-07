import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def run_migrations():
    db_url = os.getenv("DATABASE_URL", "postgresql://bravos:bravos_pass@localhost:5432/bravos_db")
    migrations_dir = Path("db/migrations")
    
    if not migrations_dir.exists():
        print(f"❌ Migrations directory {migrations_dir} not found.")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # 1. Create migrations tracking table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        
        # 2. Get applied versions
        cur.execute("SELECT version FROM _schema_migrations")
        applied_versions = {row[0] for row in cur.fetchall()}
        
        # 3. Apply pending migrations
        migration_files = sorted(migrations_dir.glob("*.sql"))
        for file in migration_files:
            version = file.name
            if version not in applied_versions:
                print(f"🚀 Applying migration: {version}...")
                with open(file, 'r', encoding='utf-8') as f:
                    cur.execute(f.read())
                cur.execute("INSERT INTO _schema_migrations (version) VALUES (%s)", (version,))
                print(f"✅ Applied {version}")
            else:
                print(f"⏩ Skipping {version} (already applied)")
                
        conn.commit()
        print("\n✨ Database is up to date.")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if conn: conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

if __name__ == "__main__":
    run_migrations()
