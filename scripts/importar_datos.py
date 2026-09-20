#!/usr/bin/env python3
"""Importa datos operativos a la base de datos desde la linea de comandos.

    python scripts/importar_datos.py                      # usa sample_data/
    python scripts/importar_datos.py --biometrico ruta.xlsx --llamadas otro.xlsx
    python scripts/importar_datos.py --forzar             # reimporta aunque ya existan
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import business, db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Importador de biometrico y llamadas")
    ap.add_argument("--biometrico", help="Excel de nomina + marcajes")
    ap.add_argument("--llamadas", help="Excel de historico de llamadas")
    ap.add_argument("--forzar", action="store_true", help="reimportar los archivos de ejemplo")
    args = ap.parse_args()

    db.init_db()
    if not args.biometrico and not args.llamadas:
        print("Importando desde sample_data/ …")
        print(" ->", business.import_samples(force=args.forzar))
        return 0
    if args.biometrico:
        print(" -> biometrico:", business.import_biometric(Path(args.biometrico)))
    if args.llamadas:
        print(" -> llamadas:", business.import_calls(Path(args.llamadas)))
    resumen = business.business_summary()
    print(f"\nEmpleados: {resumen['empleados']} · "
          f"marcajes: {resumen['asistencia'].get('n', 0)} · "
          f"llamadas: {resumen['llamadas'].get('n', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
