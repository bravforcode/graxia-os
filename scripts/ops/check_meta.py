import sqlite3

def check_db(db_path):
    print(f"Checking DB: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(opportunities);")
        columns = cursor.fetchall()
        if not columns:
            print("  -> Table 'opportunities' not found.")
            return
        
        has_org_id = any(col[1] == 'organization_id' for col in columns)
        print(f"  -> has organization_id: {has_org_id}")
        
        for col in columns:
            print(f"    - {col[1]} ({col[2]})")
            
        cursor.execute("SELECT count(*) FROM opportunities;")
        count = cursor.fetchone()[0]
        print(f"  -> Total rows: {count}")
    except Exception as e:
        print(f"  -> Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

check_db(r"C:\Users\menum\graxia_db\test.db")
check_db(r"graxia_os_production.db")
check_db(r"C:\Users\menum\graxia os\backend\graxia_os_production.db")
