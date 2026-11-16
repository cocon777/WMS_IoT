"""Schema MySQL (database/migrations) phải khớp models.py: cùng bộ bảng và cùng bộ cột."""
import importlib.util
import pathlib
import re

from app.db import Base
import app.models  # noqa: F401  (đăng ký bảng vào Base.metadata)

DB_DIR = pathlib.Path(__file__).resolve().parents[1] / "database"
SKIP = ("--", "PRIMARY", "UNIQUE", "KEY", "INDEX", "CONSTRAINT", "FOREIGN", "CHECK")


def sql_tables(sql: str) -> dict[str, set[str]]:
    out = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\)\s*ENGINE", sql, re.S):
        cols = set()
        for line in m.group(2).splitlines():
            line = line.strip()
            if not line or line.startswith(SKIP):
                continue
            col = re.match(r"`?(\w+)`?\s+[A-Za-z]", line)
            if col:
                cols.add(col.group(1))
        out[m.group(1)] = cols
    return out


def schema_after_all_migrations() -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for f in sorted((DB_DIR / "migrations").glob("*.sql")):
        sql = f.read_text(encoding="utf-8")
        tables.update(sql_tables(sql))
        for alter in re.finditer(r"ALTER TABLE\s+(\w+)\s+(.*?);", sql, re.S):
            for col in re.finditer(r"ADD COLUMN\s+`?(\w+)`?", alter.group(2)):
                tables[alter.group(1)].add(col.group(1))
            for col in re.finditer(r"DROP COLUMN\s+`?(\w+)`?", alter.group(2)):
                tables[alter.group(1)].discard(col.group(1))
    return tables


def test_tables_and_columns_match_models():
    ddl = schema_after_all_migrations()
    ddl.pop("schema_migrations")
    assert set(ddl) == set(Base.metadata.tables), "bảng trong SQL và models.py lệch nhau"
    for name, table in Base.metadata.tables.items():
        assert ddl[name] == set(table.columns.keys()), f"cột của bảng {name} lệch nhau"


def _load_migrate():
    spec = importlib.util.spec_from_file_location("migrate", DB_DIR / "migrate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sql_splitter_handles_quotes_and_comments():
    split = _load_migrate().split_statements
    sql = "-- c\nSELECT 'a;b'; /* x; y */ SELECT `k;`, \"q;\" # tail\n;SELECT 'it''s';"
    assert split(sql) == ["SELECT 'a;b'", 'SELECT `k;`, "q;"', "SELECT 'it''s'"]


def test_migrations_are_numbered_contiguously_and_record_themselves():
    split = _load_migrate().split_statements
    files = sorted((DB_DIR / "migrations").glob("*.sql"))
    assert [f.name[:3] for f in files] == [f"{i:03d}" for i in range(1, len(files) + 1)]
    for f in files:
        stmts = split(f.read_text(encoding="utf-8"))
        assert stmts and stmts[-1] == f"INSERT IGNORE INTO schema_migrations (version) VALUES ('{f.stem}')"
        assert all(s.count("(") == s.count(")") for s in stmts)
