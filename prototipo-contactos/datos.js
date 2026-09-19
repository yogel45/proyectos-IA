/* Datos de ejemplo del despacho, tomados del mismo caso que usan las otras
   aplicaciones del repositorio (expediente 3:24-cv-05148-MGL). */
const PERSONAS = [
  {
    id: 'p1', nombre: 'Dona M. Fry', rol: 'Cliente', iniciales: 'DF',
    casos: [{ id: 'c1', rol: 'Demandante' }],
    telefono: '(803) 622-1184', correo: 'dona.fry@email.com',
    lugar: 'Lexington, SC', desde: '2024-02-08',
    ultimo: 'Llamada de 18 min · hace 2 dias',
    linea: [
      { f: '2024-09-18', t: 'documento', x: 'Demanda presentada', d: 'DEMANDA · 3:24-cv-05148-MGL' },
      { f: '2024-09-16', t: 'llamada', x: 'Llamada entrante · 18 min', d: 'Ext. 9 — Camila Flores · atendida' },
      { f: '2024-05-20', t: 'documento', x: 'Declaracion jurada del testigo', d: 'DECLARACION' },
      { f: '2024-02-08', t: 'documento', x: 'Reclamacion Standard Form 95', d: 'RECLAMACION · $265,271.00' },
      { f: '2023-01-15', t: 'hecho', x: 'Colision en Park Rd y Dupre Mill Rd', d: 'Origen del caso' },
    ],
  },
  {
    id: 'p2', nombre: 'Christopher M. Cunningham', rol: 'Abogado responsable', iniciales: 'CC',
    casos: [{ id: 'c1', rol: 'Representa al demandante' }],
    telefono: '(803) 359-5523', correo: 'ccunningham@mbalaw.com',
    lugar: 'McWhirter, Bellinger & Associates, P.A.', desde: '2024-02-01',
    ultimo: 'Firmo la demanda · hace 1 dia',
    linea: [
      { f: '2024-09-18', t: 'documento', x: 'Firma la demanda', d: 'DEMANDA' },
      { f: '2024-04-18', t: 'correo', x: 'Envia expediente medico a la contraparte', d: 'CORRESPONDENCIA' },
    ],
  },
  {
    id: 'p3', nombre: 'J. Alvarez', rol: 'Ajustadora de seguros', iniciales: 'JA',
    casos: [{ id: 'c1', rol: 'State Mutual Insurance' }],
    telefono: '(929) 876-9687', correo: 'jalvarez@statemutual.com',
    lugar: 'State Mutual Insurance Company', desde: '2024-03-05',
    ultimo: 'Llamada perdida · hace 6 dias',
    linea: [
      { f: '2024-03-05', t: 'documento', x: 'Carta de acuse del reclamo', d: 'SEGURO · Poliza SM-4471902' },
      { f: '2024-03-04', t: 'llamada', x: 'Llamada entrante · sin atender', d: 'Ext. 19 — Fernanda Vega' },
    ],
  },
  {
    id: 'p4', nombre: 'Dr. A. Patel', rol: 'Medico tratante', iniciales: 'AP',
    casos: [{ id: 'c1', rol: 'Perito medico' }],
    telefono: '(803) 791-2000', correo: 'records@lexmed.com',
    lugar: 'Lexington Medical Center', desde: '2023-01-15',
    ultimo: 'Expediente medico recibido · hace 3 semanas',
    linea: [
      { f: '2023-01-15', t: 'documento', x: 'Expediente medico de urgencias', d: 'EXPEDIENTE-MEDICO' },
      { f: '2023-02-02', t: 'documento', x: 'Factura por $8,430.00', d: 'FACTURA' },
    ],
  },
  {
    id: 'p5', nombre: 'Michelle M. Livingston', rol: 'Contraparte', iniciales: 'ML',
    casos: [{ id: 'c1', rol: 'Conductora USPS' }],
    telefono: '', correo: '',
    lugar: 'United States Postal Service', desde: '2023-01-15',
    ultimo: 'Mencionada en el reporte policial',
    linea: [
      { f: '2023-01-15', t: 'documento', x: 'Reporte de colision', d: 'REPORTE-POLICIAL · TC-2023-004512' },
    ],
  },
];

const CASOS = [
  {
    id: 'c1', nombre: 'Fry v. United States of America',
    expediente: '3:24-cv-05148-MGL', estado: 'En tramite',
    tribunal: 'U.S. District Court · District of South Carolina',
    monto: '$265,271.00', documentos: 13, desde: '2024-02-08',
  },
];

const DUPLICADOS = [
  {
    id: 'd1', nombre: 'Dona M. Fry',
    a: { origen: 'Libreta del telefono', datos: 'Dona Fry · (803) 622-1184' },
    b: { origen: 'Importado de Gmail', datos: 'dona.fry@email.com · Fry, Dona M.' },
    porque: [
      'El mismo numero aparece en las dos fichas',
      'Las dos estan ligadas al expediente 3:24-cv-05148-MGL',
      'El correo de una coincide con la firma de los correos de la otra',
    ],
    confianza: 0.96,
  },
  {
    id: 'd2', nombre: 'State Mutual (aseguradora)',
    a: { origen: 'Creada a mano', datos: 'State Mutual Ins. · (929) 876-9687' },
    b: { origen: 'Creada desde una llamada', datos: '(929) 876-9687 · sin nombre' },
    porque: ['Mismo numero de telefono', 'La llamada ocurrio el dia de la carta de acuse'],
    confianza: 0.88,
  },
];

const FIRMA_EJEMPLO = `McWHIRTER, BELLINGER & ASSOCIATES, P.A.
Christopher M. Cunningham, Esquire
Federal Bar No. 12383
2437 Mineral Springs Road
Lexington, South Carolina 29072
P: (803) 359-5523  F: (803) 996-9080
ccunningham@mbalaw.com`;
