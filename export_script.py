"""
export_script.py
Export all tables from a DuckDB database to individual Parquet files.

Usage:
    python export_script.py caminho/para/meu_banco.duckdb [pasta_saida]

Defaults:
    - pasta_saida: ./export/
"""

import sys
import os
from pathlib import Path
import duckdb


def export_tables(db_path: str, out_dir: str = "export") -> None:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"ERRO: Banco não encontrado: {db_path}")
        sys.exit(1)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(db_path))

    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()

    if not tables:
        print("Nenhuma tabela encontrada no schema 'main'.")
        conn.close()
        return

    print(f"Tabelas encontradas: {len(tables)}")

    for (tbl,) in tables:
        parquet_path = out / f"{tbl}.parquet"
        print(f"Exportando '{tbl}' -> {parquet_path} ...", end=" ", flush=True)

        try:
            row_count = conn.execute(
                f"SELECT count(*) FROM \"{tbl}\""
            ).fetchone()[0]

            if row_count == 0:
                print(f"0 linhas, pulando.")
                continue

            conn.execute(
                f"""COPY (SELECT * FROM "{tbl}") TO '{parquet_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
            )

            size_mb = parquet_path.stat().st_size / 1024 / 1024
            print(f"{row_count:,} linhas, {size_mb:.1f} MB")

        except Exception as e:
            print(f"ERRO: {e}")

    conn.close()

    total_mb = sum(f.stat().st_size for f in out.glob("*.parquet")) / 1024 / 1024
    print(f"\nConcluído. Pasta '{out_dir}' com {total_mb:.1f} MB total.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python export_script.py <caminho_do_banco.duckdb> [pasta_saida]")
        sys.exit(1)

    db_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "export"
    export_tables(db_path, out_dir)
