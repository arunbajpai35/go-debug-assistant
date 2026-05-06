import logging
from pathlib import Path

from backend.db import conn, init_pool

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations() -> None:
    init_pool(minconn=1, maxconn=2)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        log.warning("no migrations found in %s", MIGRATIONS_DIR)
        return
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            create table if not exists schema_migrations (
                filename   text primary key,
                applied_at timestamptz not null default now()
            )
            """
        )
        cur.execute("select filename from schema_migrations")
        applied = {r[0] for r in cur.fetchall()}
        for f in files:
            if f.name in applied:
                continue
            log.info("applying migration %s", f.name)
            cur.execute(f.read_text())
            cur.execute("insert into schema_migrations (filename) values (%s)", (f.name,))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run_migrations()
