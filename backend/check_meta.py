from app.models import Base

print(f"Metadata tables: {sorted(list(Base.metadata.tables.keys()))}")
