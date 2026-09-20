"""Saca del registro de ContactHub lo que sostiene el diagnostico.

El registro completo de una sesion son decenas de miles de lineas. Esto
extrae el recuento de errores por tipo y una traza completa de cada clase,
que es lo que hay que poder ensenar.

    python pruebas/extraer_log.py data/pruebas/<fecha>/logs/contacthub.log
"""
from pathlib import Path
import re, collections, sys

t = Path(sys.argv[1]).read_text(errors="replace")
lineas = t.splitlines()
miles = lambda n: f"{n:,}".replace(",", " ")

print("Registro de ContactHub durante las pruebas del reto 7")
print("=" * 70)
print()
print("Extracto. El registro completo de la sesion tiene", miles(len(lineas)),
      "lineas; aqui va")
print("lo que sostiene los apartados 5 y 8.8 del informe.")
print()
print("1. RECUENTO DE ERRORES DEL SERVIDOR")
print("-" * 70)
c = collections.Counter()
for l in lineas:
    m = re.search(r"(sqlalchemy\.exc\.\w+|sqlite3\.\w+Error): ?([^(]{0,80})", l)
    if m:
        c[f"{m.group(1)}: {m.group(2).strip()}"] += 1
for k, v in c.most_common():
    print(f"  {v:>6}  {k}")
print()
print("  Causas:")
print()
print("  - Las esperas de conexion que caducan (TimeoutError) son la saturacion")
print("    del pool: 15 conexiones para 40 hilos. Apartado 5 del informe.")
if any("labels" in k for k in c):
    print("  - El fallo de UNIQUE en labels es una carrera al crear una etiqueta")
    print("    nueva desde dos peticiones a la vez. Apartado 8.8. Se reproduce")
    print("    con solo dos altas simultaneas.")
print()
print("2. LA ESPERA DE CONEXION QUE CADUCA, TRAZA COMPLETA")
print("-" * 70)
ini = next(i for i, l in enumerate(lineas) if "Exception in ASGI application" in l)
fin = next(i for i in range(ini, len(lineas)) if "sqlalchemy.exc.TimeoutError" in lineas[i])
print("\n".join(lineas[ini:fin + 1]))
print()
print("3. LA CARRERA DE LA ETIQUETA, TRAZA COMPLETA")
print("-" * 70)
u = next((i for i, l in enumerate(lineas) if "UNIQUE constraint failed: labels" in l), None)
if u is None:
    print("  En esta sesion no aparece: el escenario de escrituras corre a 8")
    print("  peticiones/s y la carrera necesita dos altas coincidiendo en el")
    print("  mismo instante con una etiqueta que todavia no existe.")
    print()
    print("  La traza completa, y la reproduccion deliberada que la provoca con")
    print("  solo dos peticiones simultaneas, estan en el apartado 8.8 del")
    print("  informe. Es un defecto real y reproducible al 100 %, aunque una")
    print("  sesion de carga normal no siempre lo dispare.")
else:
    arr = max(i for i in range(0, u) if "Exception in ASGI application" in lineas[i])
    fin2 = next(i for i in range(u, len(lineas)) if "sqlalchemy.exc.IntegrityError" in lineas[i])
    print("\n".join(lineas[arr:fin2 + 1]))
print()
print("4. PETICIONES ATENDIDAS CORRECTAMENTE (muestra)")
print("-" * 70)
patron = re.compile(r"-> 2\d\d \d+ms")
for l in [l for l in lineas if patron.search(l)][:10]:
    print(" ", l)
print()
dos_xx = sum(1 for l in lineas if re.search(r"-> 2\d\d ", l))
print("  Total de respuestas 2xx en el registro:", miles(dos_xx))
