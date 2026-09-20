#!/usr/bin/env python3
"""Arma el directorio desde cero y mide lo que sale.

    python scripts/contactos_demo.py            # importa y reporta
    python scripts/contactos_demo.py --limpio   # borra la base y empieza de cero

Sirve como demostracion reproducible: importa la nomina, las llamadas de la
central y lo que DocuFlow AI ya clasifico, da de alta una ficha leyendo una
firma de correo y muestra los duplicados que se detectan solos.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contactos import busqueda, db, duplicados, extraccion, fuentes, modelo  # noqa: E402
from contactos.config import DB_PATH  # noqa: E402

FIRMA = """McWHIRTER, BELLINGER & ASSOCIATES, P.A.
Christopher M. Cunningham, Esq.
Federal Bar No. 12383
2437 Mineral Springs Road
Lexington, South Carolina 29072
P: (803) 359-5523  F: (803) 996-9080
ccunningham@mbalaw.com"""


def titulo(texto: str) -> None:
    print(f"\n{texto}\n{'-' * len(texto)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Demostracion de Directorio vivo")
    parser.add_argument("--limpio", action="store_true", help="borrar la base y empezar de cero")
    args = parser.parse_args()

    if args.limpio and DB_PATH.exists():
        db.cerrar()
        for sufijo in ("", "-wal", "-shm"):
            Path(str(DB_PATH) + sufijo).unlink(missing_ok=True)
        print(f"Base borrada: {DB_PATH}")
    db.init_db()

    titulo("1. Importar lo que ya existe")
    inicio = time.time()
    for r in fuentes.importar_todo():
        print(f"  {r['fuente']:<11} {r['creados']:>5} fichas  {r['actualizados']:>4} completadas  "
              f"{r['interacciones']:>6} hitos   {r['detalle']}")
    print(f"  ({time.time() - inicio:.1f} s)")

    total = db.query_one(
        "SELECT (SELECT COUNT(*) FROM personas WHERE activo=1) p, "
        "(SELECT COUNT(*) FROM casos) c, (SELECT COUNT(*) FROM interacciones) i, "
        "(SELECT COUNT(*) FROM interacciones WHERE persona_id IS NULL) s")
    print(f"  -> {total['p']} fichas, {total['c']} expedientes, {total['i']} hitos "
          f"({total['s']} de numeros que llamaron poco, buscables pero sin ficha)")

    titulo("2. Alta leyendo una firma de correo")
    lectura = extraccion.leer(FIRMA)
    for clave, valor in lectura["campos"].items():
        print(f"  {clave:<13} {valor}")
    for ident in lectura["identificadores"]:
        print(f"  {ident['tipo']:<13} {ident['valor']} ({ident['etiqueta']})")
    persona_id = modelo.crear_persona(
        lectura["campos"]["nombre"], organizacion=lectura["campos"].get("organizacion", ""),
        rol=lectura["campos"].get("rol", ""), lugar=lectura["campos"].get("lugar", ""),
        origen="manual", notas=f"Numero de colegiado: {lectura['campos'].get('colegiado','')}")
    for ident in lectura["identificadores"]:
        modelo.agregar_identificador(persona_id, ident["tipo"], ident["valor"],
                                     ident["etiqueta"], "manual")
    caso_id = modelo.asegurar_caso("3:24-cv-05148-MGL")
    modelo.asegurar_participacion(persona_id, caso_id, "Abogado del demandado", "alta manual")
    modelo.registrar_interaccion(persona_id, "hecho", db.now_iso(),
                                 "Ficha creada leyendo una firma de correo",
                                 detalle=FIRMA.splitlines()[0], origen="manual")
    print(f"  -> ficha #{persona_id} creada y vinculada al expediente")

    titulo("3. Buscar tirando de cualquier hilo")
    for consulta in ("(803) 359-5523", "Fry", "3:24-cv-05148-MGL", "demandante"):
        r = busqueda.buscar(consulta)
        print(f"  [{consulta}]")
        for ficha in r["resultados"][:3]:
            print(f"      {ficha['nombre']:<42} porque {ficha['por']}")
        for hito in r["historial"][:2]:
            print(f"      (sin ficha) {hito['ts'][:16]} {hito['titulo']}")
        if not r["resultados"] and not r["historial"]:
            print("      sin resultados")

    titulo("4. Duplicados que se detectan solos")
    propuestas = duplicados.detectar()
    for d in propuestas[:5]:
        print(f"  {int(d['confianza'] * 100)}%  {d['a']['nombre']}  <->  {d['b']['nombre']}")
        for motivo in d["motivos"]:
            print(f"        porque {motivo}")
    if not propuestas:
        print("  ninguno por revisar")

    titulo("5. La persona decide (y el sistema lo recuerda)")
    falsos = [d for d in propuestas
              if "telefono" in " ".join(d["motivos"]) and
              not any("nombres" in m for m in d["motivos"])]
    for d in falsos:
        duplicados.descartar(d["a"]["id"], d["b"]["id"])
        print(f"  descartado: {d['a']['nombre']} y {d['b']['nombre']} comparten el "
              f"conmutador, pero no son la misma")
    quedan = duplicados.detectar()
    print(f"  -> quedan {len(quedan)} propuesta(s) por revisar en la aplicacion")

    print(f"\nListo. Arranca la aplicacion con:  python run_contactos.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
