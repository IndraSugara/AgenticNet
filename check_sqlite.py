"""
check_sqlite.py -- Inspect semua SQLite database di folder data/

Jalankan: python check_sqlite.py
Opsional: python check_sqlite.py chat_history.db   <- hanya satu file
"""
import sqlite3
import os
import sys
import io
from pathlib import Path

# Force UTF-8 output di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─── Warna terminal ──────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"

def c(text, color): return f"{color}{text}{RESET}"

DATA_DIR = Path(__file__).parent / "data"
MAX_ROWS = 5      # baris sample yang ditampilkan per tabel
MAX_COL_WIDTH = 40  # lebar kolom maksimal


# ─── Helper ───────────────────────────────────────────────────────────────────

def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def truncate(value, width=MAX_COL_WIDTH):
    s = str(value) if value is not None else "NULL"
    return s if len(s) <= width else s[:width - 3] + "..."


def print_table(headers, rows):
    """Print rows as a simple ASCII table."""
    col_widths = [max(len(str(h)), 4) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(truncate(val)))

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    fmt = "|" + "|".join(f" {{:<{w}}} " for w in col_widths) + "|"

    print(sep)
    print(fmt.format(*[str(h) for h in headers]))
    print(sep)
    for row in rows:
        print(fmt.format(*[truncate(v) for v in row]))
    print(sep)


# ─── Core Inspector ───────────────────────────────────────────────────────────

def inspect_db(db_path: Path):
    size = db_path.stat().st_size
    print()
    print("=" * 70)
    print(c(f"  [DB] {db_path.name}", BOLD + CYAN) +
          c(f"  ({human_size(size)})", DIM))
    print("=" * 70)

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Daftar tabel
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]

        if not tables:
            print(c("  (tidak ada tabel)", YELLOW))
            conn.close()
            return

        print(c(f"  Tabel ({len(tables)}): ", BOLD) + ", ".join(tables))
        print()

        for table in tables:
            # Jumlah baris
            cur.execute(f"SELECT COUNT(*) FROM [{table}]")
            count = cur.fetchone()[0]

            print(c(f"  +-- {table}", BOLD + GREEN) +
                  c(f"  [{count} baris]", DIM))

            # Kolom
            cur.execute(f"PRAGMA table_info([{table}])")
            cols_info = cur.fetchall()
            col_names = [c_["name"] for c_ in cols_info]
            col_types = [c_["type"] for c_ in cols_info]

            print(c("  |  Kolom: ", DIM) +
                  ", ".join(f"{n} ({t})" for n, t in zip(col_names, col_types)))

            if count == 0:
                print(c("  |  (tabel kosong)", YELLOW))
            else:
                cur.execute(f"SELECT * FROM [{table}] LIMIT {MAX_ROWS}")
                rows = cur.fetchall()
                sample = [tuple(row) for row in rows]

                print(c(f"  |  Sample ({min(MAX_ROWS, count)} baris):", DIM))
                # Indent table
                import contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    print_table(col_names, sample)
                for line in buf.getvalue().splitlines():
                    print("  |  " + line)

                if count > MAX_ROWS:
                    print(c(f"  |  ... dan {count - MAX_ROWS} baris lainnya (gunakan LIMIT lebih besar)", DIM))

            print(c("  +" + "-" * 60, DIM))
            print()

        conn.close()

    except sqlite3.OperationalError as e:
        print(c(f"  ❌ Error membuka DB: {e}", RED))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        # Mode: satu file tertentu
        target = sys.argv[1]
        db_path = DATA_DIR / target
        if not db_path.exists():
            db_path = Path(target)  # coba path absolut
        if not db_path.exists():
            print(c(f"File tidak ditemukan: {target}", RED))
            sys.exit(1)
        db_files = [db_path]
    else:
        # Mode: semua file .db di folder data/
        db_files = sorted(DATA_DIR.glob("*.db"))

    if not db_files:
        print(c(f"Tidak ada file .db di {DATA_DIR}", YELLOW))
        sys.exit(0)

    print()
    print(c(" AgenticNet - SQLite Database Inspector", BOLD + CYAN))
    print(c(f" Folder: {DATA_DIR}", DIM))
    print(c(f" File ditemukan: {len(db_files)}", DIM))

    for db_path in db_files:
        inspect_db(db_path)

    print()
    print(c(" [OK] Selesai.", BOLD + GREEN))
    print()


if __name__ == "__main__":
    main()
