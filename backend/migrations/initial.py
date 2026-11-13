from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models

# 已上线表结构的增量列；create_all 只建新表，不会给旧表补列。
_ADDED_COLUMNS = {
    'datasets': [
        ('revisions', "JSON NOT NULL DEFAULT '{}'"),
        ('supplement_count', 'INTEGER NOT NULL DEFAULT 0'),
    ],
    'jobs': [
        ('records_snapshot', 'JSON NOT NULL DEFAULT \'[]\''),
    ],
}

def migrate():
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing:
                continue
            present = {c['name'] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        # 历史批次没有修订号，按业务口径视作首版 revision=1。
        if 'datasets' in existing:
            conn.execute(text(
                "UPDATE datasets SET revisions = '{}' WHERE revisions IS NULL"
            ))
if __name__=='__main__':migrate()
