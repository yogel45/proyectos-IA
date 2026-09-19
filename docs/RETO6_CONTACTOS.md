# Análisis crítico y rediseño de plataformas de contactos

**Reto 6.** Qué sobra, qué estorba y qué falta en las plataformas de contactos y de
gestión profesional, y cómo sería una experiencia más simple para un despacho.

Entregables de este documento:

1. Análisis crítico de plataformas existentes (§2 y §3).
2. Listado de funcionalidades y flujos a eliminar, simplificar, rediseñar o mantener (§4).
3. Propuesta de experiencia y flujo mejorado, con **prototipo navegable** (§5 y §6).

---

## 1. Método y alcance

Se analizaron tres libretas de contactos de uso masivo —**Google Contacts**, **Apple
Contacts** y **Microsoft Outlook (People)**— y la categoría de **software jurídico de
gestión** (Clio, MyCase), por ser el tipo de herramienta que un despacho como el de este
proyecto acabaría comprando.

El análisis se apoya en tres fuentes:

* la **documentación oficial** de cada plataforma y los foros de soporte donde los
  propios usuarios describen sus fricciones (ver §9);
* las **comparativas del sector legal** de 2026, que discuten explícitamente la
  complejidad como factor de adopción;
* los **datos reales de este despacho** que ya se procesaron en los retos anteriores:
  25 personas en nómina, 4 000 llamadas de RingCentral, 13 documentos clasificados del
  expediente `3:24-cv-05148-MGL`. Eso permite contrastar cada crítica con un caso
  concreto en lugar de opinar en abstracto.

**Lo que este análisis no es:** no es una auditoría de usabilidad con usuarios reales.
No se hicieron pruebas moderadas ni se midieron tiempos de tarea. Las estimaciones de
impacto de §7 son hipótesis a validar, y están señaladas como tales.

---

## 2. Análisis crítico por plataforma

### Google Contacts

**Lo que hace bien:** sincroniza en todas partes, la búsqueda es rápida, y la fusión de
duplicados al menos existe.

**Dónde falla:**

| Fricción | Qué pasa |
|---|---|
| **"Otros contactos"** | Cada dirección a la que se escribe se convierte en contacto automáticamente, en una lista paralela. El usuario tiene que saber en cuál de las dos listas buscar, y la libreta se llena de direcciones que nunca fueron una relación. |
| **Fusión ciega** | El botón *Combinar y corregir* anuncia un número de duplicados y fusiona en bloque. Los usuarios reportan que **borra contactos de forma inesperada** y que no se puede saber cuáles. Es la función con más quejas de la plataforma. |
| **Fusión imposible entre cuentas** | No se pueden fusionar contactos de cuentas distintas, que es justo el caso de quien tiene correo personal y del despacho. |
| **Duplicados que reaparecen** | Cuando varias fuentes (teléfono, WhatsApp, correo) crean la misma persona, la detección automática falla y los duplicados vuelven tras cada sincronización. |
| **Etiquetas manuales** | La única forma de agrupar es crear etiquetas a mano y mantenerlas. En un despacho con rotación de casos, esa taxonomía muere en semanas. |

### Apple Contacts

**Lo que hace bien:** es la más limpia visualmente y la que menos pide al usuario.

**Dónde falla:**

| Fricción | Qué pasa |
|---|---|
| **Sin campos propios en iPhone** | No se pueden añadir campos personalizados desde el teléfono, aunque sí desde el Mac. Un despacho que quiere anotar "número de colegiado" o "expediente" no tiene dónde. |
| **Etiquetas fijas** | Los rótulos de teléfono están limitados a un catálogo cerrado (trabajo, casa, fax). Poner "extensión de la central" no es posible sin recurrir a trucos. |
| **Grupos a medias** | Durante años no se pudieron crear ni editar grupos desde el iPhone; sólo desde ordenador o mediante apps de terceros. La gestión sigue siendo incómoda. |

Apple acierta al no abrumar, pero su simplicidad es **por omisión**: no resuelve el
problema, lo deja fuera.

### Microsoft Outlook (People)

**Lo que hace bien:** integra contactos con calendario y correo corporativo, y la versión
nueva ha mejorado la búsqueda.

**Dónde falla:**

| Fricción | Qué pasa |
|---|---|
| **Categorías recortadas** | En el Outlook nuevo sólo se ven **diez categorías** en el panel lateral, mientras que en el clásico se veían todas. Además **no se pueden renombrar ni cambiar de color** una vez creadas. |
| **Se perdió la tarjeta de contacto** | Los usuarios reportan que las tarjetas desaparecieron, que el puesto de trabajo ya no se muestra de forma visible y que los contactos quedaron como **una lista plana de nombres**: para encontrar a quien hace determinada función hay que abrirlos uno por uno. |
| **Rediseño con pérdida** | El patrón se repite: la versión nueva se ve mejor y hace menos. Quien dependía de esas funciones tiene que cambiar su forma de trabajar o buscarse otra herramienta. |

### Software jurídico de gestión (Clio, MyCase)

Aquí el problema no es la falta de funciones, sino el exceso:

* Clio tiene una **curva de aprendizaje pronunciada**: más potencia, pero también más
  tiempo en ajustes, configurando flujos y averiguando dónde está cada cosa. Hay
  abogados que **se cambiaron a MyCase porque Clio "era demasiado"**.
* Las comparativas del sector recomiendan MyCase precisamente cuando el objetivo es
  *"instalarlo y empezar a trabajar"*.
* Y aun así, el catálogo de integraciones manda: se reporta como carencia la **falta de
  integración VOIP con RingCentral** — exactamente la central telefónica que usa este
  despacho, cuyos 4 000 registros de llamada ya están en este proyecto.

La lección para el rediseño: **la complejidad es el principal enemigo de la adopción**, y
el valor no está en el número de funciones sino en cuántas se usan el primer día.

---

## 3. Los siete supuestos que hay que cuestionar

El hallazgo central del análisis es que las tres libretas comparten la misma herencia de
diseño: son **la agenda de papel digitalizada**. De ahí salen sus problemas.

1. **"Un contacto es una ficha de campos."** Treinta o más casillas por persona: fax,
   apodo, perfiles sociales, cumpleaños, tres direcciones. Casi todas vacías, y las
   llenas envejecen sin avisar. Lo que de verdad define una relación profesional —cuándo
   hablamos, de qué caso, qué documento mandó— no cabe en ningún campo.
2. **"El usuario organiza."** Grupos, etiquetas y categorías que hay que crear y
   mantener a mano. Nadie sostiene una taxonomía viva; a los tres meses la mitad de las
   etiquetas sobran y la otra mitad falta.
3. **"Completitud es calidad."** La interfaz premia rellenar. Veinte campos vacíos gritan
   que hay trabajo pendiente, cuando en realidad esos datos no existen y no hacen falta.
4. **"Los duplicados son problema del usuario."** El sistema los detecta, anuncia una
   cifra y delega la decisión en un botón de fe que no explica nada y no se puede deshacer.
5. **"Buscar es recordar el nombre."** En un despacho casi nunca se empieza por el
   nombre: se empieza por el teléfono que está sonando, por el expediente que se tiene
   abierto o por el rol (*"la ajustadora"*, *"el perito"*).
6. **"Sincronizar todo es mejor."** Cada dirección tocada se convierte en contacto. La
   libreta deja de ser el directorio de las personas con las que se trabaja.
7. **"La persona es la unidad de trabajo."** No lo es. En un despacho la unidad es el
   **asunto**: quién participa en este expediente, con qué papel. Ninguna libreta
   responde a esa pregunta sin grupos manuales.

---

## 4. Qué eliminar, simplificar, rediseñar y mantener

### Eliminar

| Funcionalidad | Por qué se elimina | Riesgo asumido |
|---|---|---|
| Lista paralela de "otros contactos" | Duplica el lugar donde buscar y llena la libreta de direcciones que nunca fueron una relación | Perder el autocompletado de direcciones ocasionales; se resuelve buscando en el correo, que es donde viven |
| Campos de catálogo fijo poco usados (fax, apodo, perfiles sociales, tres direcciones) | Ocupan la ficha, envejecen y nadie los consulta | Algún despacho aún usa fax: se admite como campo libre, no como casilla fija |
| Grupos y etiquetas manuales | Exigen mantenimiento constante y se desactualizan | Se pierde la agrupación arbitraria; se sustituye por roles derivados del caso |
| Botón de fusión masiva de duplicados | Es la función con más quejas: fusiona en bloque y borra sin explicar | Menos velocidad al limpiar libretas enormes; se gana no perder datos |
| Importación con mapeo de 40 columnas | Barrera de entrada altísima para un uso puntual | Migraciones grandes necesitan asistencia; se acepta |
| Pestañas y vistas múltiples del mismo listado | Fragmentan la búsqueda sin aportar | Ninguno relevante |

### Simplificar

| Funcionalidad | Cómo queda |
|---|---|
| Alta de contacto | De un formulario de treinta campos a **pegar una firma, tarjeta o pie de escrito**: el sistema propone y la persona confirma |
| Búsqueda | De varios buscadores por sección a **una sola caja** que acepta nombre, teléfono, expediente o rol |
| Ficha | Cabecera con **sólo los datos que existen**; lo vacío no se muestra |
| Edición | Sin modo edición aparte: se edita donde se lee |
| Fusión | De un botón masivo a **propuestas de una en una, explicadas y reversibles** |

### Rediseñar

| Funcionalidad | De qué a qué |
|---|---|
| Organización | De taxonomía manual a **roles derivados** de los documentos y llamadas que la oficina ya genera |
| Ficha de persona | De formulario a **línea de tiempo**: llamadas, documentos y eventos del caso en orden |
| Entrada al sistema | De lista alfabética a **resultados por relevancia de la relación**, con el motivo de cada resultado escrito |
| Vista de asunto | Nueva: **"quién es quién en este expediente"**, con el papel de cada persona |
| Detección de duplicados | De coincidencia de nombre a **coincidencia con evidencia** (mismo teléfono, mismo expediente, misma firma) |

### Mantener

Sincronización entre dispositivos, búsqueda instantánea, exportación estándar (vCard y
CSV), historial de cambios y control de acceso por usuario. Son la base sobre la que se
apoya todo lo demás y no hay razón para tocarlos.

---

## 5. La propuesta: "Directorio vivo"

> **Una persona no es una ficha: es una relación con historia.
> Y en un despacho, la unidad de trabajo no es la persona: es el asunto.**

De esas dos frases salen los cinco flujos de la propuesta.

### 5.1 Una sola entrada

Una caja que acepta **cualquier hilo del que tires**: un nombre a medias, el teléfono que
está entrando, un número de expediente o un rol. Los resultados mezclan personas y casos,
se ordenan por lo reciente de la relación —no alfabéticamente— y **cada uno dice por qué
aparece**: *"ese número es suyo"*, *"participa en ese expediente"*, *"es su rol en el caso"*.

### 5.2 La ficha es la historia

Cabecera mínima —sólo lo que existe— y debajo la línea de tiempo: llamadas de la central,
documentos clasificados, hitos del caso. El dato que envejece (un teléfono viejo) queda en
segundo plano frente al hecho que no envejece (esta persona llamó el 16 de septiembre y
hablamos 18 minutos).

### 5.3 Quién es quién en el caso

La vista que ninguna libreta tiene. Lista las personas del expediente con su papel
—demandante, abogado, ajustadora, perito médico, contraparte— **derivado de los documentos
ya clasificados**: quien firma la demanda es el abogado; quien aparece en la póliza, la
aseguradora; quien firma el expediente médico, el médico tratante.

### 5.4 Alta en un paso

Pegar la firma de un correo o el pie de un escrito. El sistema extrae nombre, despacho,
teléfonos, correo, dirección y número de colegiado, y sólo pide confirmar. Es el mismo
extractor que ya funciona en la aplicación de documentos de este repositorio.

### 5.5 Duplicados explicados

Cada propuesta de fusión trae **el motivo escrito** (*"el mismo número aparece en las dos
fichas"*, *"las dos están ligadas al mismo expediente"*), un porcentaje de coincidencia,
se acepta de una en una y se puede deshacer.

---

## 6. Prototipo navegable

El prototipo está en [`prototipo-contactos/`](../prototipo-contactos/). Se abre con doble
clic en `index.html` —no necesita servidor ni instalación— y lleva datos del mismo
expediente que usan las otras dos aplicaciones del repositorio.

### Una sola entrada

![Buscar por teléfono, expediente o rol](img/reto6-buscar.png)

Buscando `(929) 876` —un número entrante— aparece la ajustadora de la aseguradora con la
explicación *"ese número es suyo"* y su última interacción. Ninguna de las tres libretas
analizadas llega a esa persona por ese camino.

### La ficha es la historia

![Ficha con línea de tiempo](img/reto6-ficha.png)

Cinco hitos en orden: demanda presentada, llamada de 18 minutos atendida por la extensión
9, declaración jurada, reclamación de $265 271 y la colisión que originó el caso. Ningún
campo vacío a la vista.

### Quién es quién en el caso

![Vista por expediente](img/reto6-caso.png)

### Alta en un paso

![Alta pegando una firma de correo](img/reto6-alta.png)

De la firma del escrito real salen ocho datos: nombre, organización, rol, teléfono, fax,
correo, dirección y número de colegiado federal.

### Duplicados explicados

![Fusión con su motivo](img/reto6-duplicados.png)

### Antes y después

![Comparativa de supuestos](img/reto6-comparativa.png)

---

## 7. Impacto esperado

Son **hipótesis a validar**, no resultados medidos. Cada una lleva la forma de comprobarla:

| Cambio | Impacto esperado | Cómo se mide |
|---|---|---|
| Alta pegando una firma | De ~14 campos tecleados a 1 pegar + 1 confirmar | Tiempo medio de alta antes y después |
| Búsqueda de una sola caja | Encontrar a alguien por teléfono entrante deja de ser imposible | % de llamadas entrantes identificadas al primer intento |
| Roles derivados | Cero mantenimiento de etiquetas | Nº de etiquetas creadas a mano al mes (objetivo: 0) |
| Fusión explicada | Ninguna pérdida de datos por fusión | Incidencias de "se borró un contacto" (objetivo: 0) |
| Ficha sin campos vacíos | Menos ruido visual | Nº de campos visibles por ficha (de ~30 a los que existan) |
| Vista por expediente | Responder "quién participa" sin preguntar a nadie | Tiempo hasta localizar al perito de un caso |

---

## 8. Riesgos y limitaciones

* **Roles derivados = dependencia del clasificador.** Si la aplicación de documentos
  clasifica mal, el papel de una persona sale mal. Mitigación: el rol se muestra como
  propuesta editable, no como dato incuestionable.
* **Menos campos puede doler en casos raros.** Habrá despachos que sí usen fax o que
  necesiten un dato exótico. Mitigación: un campo libre con nombre propio, en vez de
  treinta casillas fijas.
* **Eliminar "otros contactos" quita una red de seguridad.** Quien esperaba autocompletado
  de cualquier dirección tocada lo echará de menos. Mitigación: esa búsqueda se hace en el
  correo, que es donde esos datos viven de verdad.
* **La línea de tiempo requiere integraciones.** Sin la central telefónica y sin los
  documentos clasificados, la propuesta pierde la mitad de su valor. En este proyecto
  ambas fuentes ya existen, pero en otro despacho hay que conectarlas primero.
* **Migrar desde una libreta sucia no es trivial.** Un directorio con años de duplicados
  necesita una pasada asistida antes de estrenar el sistema nuevo.
* **No se ha validado con usuarios.** El siguiente paso natural es sentar a dos paralegales
  con el prototipo y cronometrar las cinco tareas de §7.

---

## 9. Fuentes

* Google Contacts — fusión de duplicados y sus límites: [guía de fusión de duplicados](https://sharedcontacts.com/blog/how-to-merge-duplicate-google-contacts) · [ayuda oficial](https://support.google.com/contacts/answer/7078226) · [duplicados que reaparecen](https://sharedcontacts.com/faq/my-contacts-are-duplicating-what-should-i-do) · [comportamiento inesperado al fusionar](https://www.justanswer.com/computer/6v3ap-when-using-gmail-s-merge-duplicate-contacts-says.html)
* Outlook (People) — categorías y tarjetas de contacto: [categorías que faltan](https://learn.microsoft.com/en-us/answers/questions/4671037/new-outlook-category-missing-under-people) · [no se pueden editar categorías](https://learn.microsoft.com/en-us/answers/questions/4726119/no-ability-to-edit-people-contact-categories-in-ne) · [funcionalidad ausente](https://learn.microsoft.com/en-us/answers/questions/4737386/missing-functionality-in-new-outlook) · [rediseño de People](https://www.neowin.net/news/latest-feature-in-new-outlook-may-finally-make-you-ditch-outlook-classic/)
* Apple Contacts — campos y grupos: [campos personalizados](https://discussions.apple.com/thread/253211972) · [gestión de grupos en iPhone](https://ios.gadgethacks.com/how-to/trick-managing-icloud-contact-groups-right-from-your-iphone-since-apples-contacts-app-wont-let-you-0385037/) · [etiquetas personalizadas](https://www.iphonefaq.org/archives/971988)
* Software jurídico — complejidad y adopción: [comparativa Clio vs MyCase](https://www.timeminer.com/blog/clio-vs-mycase-which-practice-management-software-is-right-for-your-firm-in-2026-27) · [comparativa de gestión de casos 2026](https://mylegalacademy.com/kb/case-management-software-comparison-2026) · [integraciones y carencias](https://ustechautomations.com/resources/blog/clio-vs-mycase-legal-practice-management-comparison-2026)
