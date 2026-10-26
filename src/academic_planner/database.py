from pathlib import Path
from sqlalchemy import create_engine, text
from .config import DATABASE_URL
def get_engine(url=None):
    return create_engine(url or DATABASE_URL, future=True, pool_pre_ping=True)
def initialize_database(engine):
    sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        for stmt in sql.split(";"):
            if stmt.strip(): conn.execute(text(stmt))
