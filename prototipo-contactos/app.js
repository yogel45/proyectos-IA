/* Prototipo navegable. Sin servidor ni dependencias: se abre con doble clic. */
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const esc = t => String(t ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

/* ---------------- navegacion ---------------- */
function ir(vista) {
  $$('.vista').forEach(v => v.classList.toggle('activa', v.id === 'v-' + vista));
  $$('#nav a').forEach(a => a.classList.toggle('active', a.dataset.vista === vista));
  window.scrollTo({top: 0});
}
$$('#nav a').forEach(a => a.onclick = () => ir(a.dataset.vista));

/* ---------------- 1. buscador ---------------- */
const normal = t => (t || '').toLowerCase()
  .normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9 ]/g, ' ');

function buscar(consulta) {
  const q = normal(consulta).trim();
  if (!q) return [];
  const partes = q.split(/\s+/).filter(Boolean);
  const salida = [];

  PERSONAS.forEach(p => {
    const heno = normal([p.nombre, p.rol, p.lugar, p.telefono, p.correo,
      ...p.casos.map(c => c.rol + ' ' + (CASOS.find(x => x.id === c.id)?.expediente || ''))].join(' '));
    const aciertos = partes.filter(t => heno.includes(t));
    if (!aciertos.length) return;
    // por que aparece: el primer campo que contiene lo buscado
    let por = 'coincide el nombre';
    const t = aciertos[0];
    if (normal(p.telefono).includes(t)) por = 'ese numero es suyo';
    else if (normal(p.rol).includes(t)) por = 'es su rol en el caso';
    else if (normal(p.lugar).includes(t)) por = 'trabaja ahi';
    else if (normal(p.correo).includes(t)) por = 'coincide el correo';
    else if (p.casos.some(c => normal(CASOS.find(x => x.id === c.id)?.expediente || '').includes(t)))
      por = 'participa en ese expediente';
    salida.push({tipo: 'persona', p, por, peso: aciertos.length});
  });

  CASOS.forEach(c => {
    const heno = normal([c.nombre, c.expediente, c.tribunal, c.estado].join(' '));
    if (partes.some(t => heno.includes(t)))
      salida.push({tipo: 'caso', c, por: 'expediente abierto', peso: 2});
  });

  return salida.sort((a, b) => b.peso - a.peso);
}

function pintarResultados(consulta) {
  const cont = $('#resultados');
  const r = buscar(consulta);
  if (!consulta.trim()) {
    cont.innerHTML = `<p class="small muted" style="padding:10px 12px">
      Los resultados aparecen mientras escribes, mezclando personas y casos.</p>`;
    return;
  }
  if (!r.length) {
    cont.innerHTML = `<p class="small muted" style="padding:10px 12px">
      Nada coincide con "${esc(consulta)}".</p>`;
    return;
  }
  cont.innerHTML = r.map(x => x.tipo === 'persona' ? `
    <div class="res" onclick="abrirPersona('${x.p.id}')">
      <div class="avatar">${esc(x.p.iniciales)}</div>
      <div style="flex:1">
        <div><strong>${esc(x.p.nombre)}</strong>
          <span class="tag">${esc(x.p.rol)}</span></div>
        <div class="por">${esc(x.por)} · ${esc(x.p.ultimo)}</div>
      </div>
      <div class="small muted">${esc(x.p.telefono || x.p.correo || '')}</div>
    </div>` : `
    <div class="res" onclick="ir('caso')">
      <div class="avatar">▤</div>
      <div style="flex:1">
        <div><strong>${esc(x.c.nombre)}</strong> <span class="tag acc">caso</span></div>
        <div class="por">${esc(x.c.expediente)} · ${esc(x.c.documentos)} documentos</div>
      </div>
      <div class="small muted">${esc(x.c.estado)}</div>
    </div>`).join('');
}

$('#q').addEventListener('input', e => pintarResultados(e.target.value));
$$('.pista').forEach(el => el.onclick = () => {
  $('#q').value = el.dataset.q;
  pintarResultados(el.dataset.q);
});
pintarResultados('');

/* ---------------- 2. ficha de persona ---------------- */
function pintarFicha(id) {
  const p = PERSONAS.find(x => x.id === id) || PERSONAS[0];
  const caso = CASOS.find(c => c.id === (p.casos[0] || {}).id);
  const dato = (etiqueta, valor) => valor
    ? `<div style="margin-bottom:6px"><span class="muted small">${etiqueta}:</span> ${esc(valor)}</div>` : '';
  $('#ficha').innerHTML = `
    <div class="ficha-cab">
      <div class="avatar">${esc(p.iniciales)}</div>
      <div style="flex:1">
        <h2 style="font-size:20px">${esc(p.nombre)}</h2>
        <div class="muted small">${esc(p.rol)}${p.lugar ? ' · ' + esc(p.lugar) : ''}</div>
      </div>
      <div class="row" style="flex:0 0 auto">
        <button class="ghost">Llamar</button>
        <button class="ghost">Escribir</button>
      </div>
    </div>
    <div class="sep"></div>
    ${dato('Telefono', p.telefono)}${dato('Correo', p.correo)}
    ${caso ? `<div style="margin-bottom:6px"><span class="muted small">Caso:</span>
      ${esc(caso.nombre)} <span class="tag acc">${esc(p.casos[0].rol)}</span></div>` : ''}
    <div class="muted small">En el despacho desde ${esc(p.desde)}</div>
    <div class="sep"></div>
    <h3>Historia <small>${p.linea.length} hitos</small></h3>
    <div class="linea">
      ${p.linea.map(h => `
        <div class="hito ${esc(h.t)}">
          <div class="fecha">${esc(h.f)}</div>
          <div class="punto"></div>
          <div><div class="que">${esc(h.x)}</div><div class="det">${esc(h.d)}</div></div>
        </div>`).join('')}
    </div>`;
}
function abrirPersona(id) { $('#sel-persona').value = id; pintarFicha(id); ir('persona'); }
$('#sel-persona').innerHTML = PERSONAS.map(p =>
  `<option value="${p.id}">${esc(p.nombre)} — ${esc(p.rol)}</option>`).join('');
$('#sel-persona').onchange = e => pintarFicha(e.target.value);
pintarFicha(PERSONAS[0].id);

/* ---------------- 3. quien es quien ---------------- */
(function pintarCaso() {
  const c = CASOS[0];
  const gente = PERSONAS.filter(p => p.casos.some(x => x.id === c.id));
  $('#caso').innerHTML = `
    <div class="row" style="justify-content:space-between;align-items:flex-start">
      <div>
        <h2 style="font-size:18px">${esc(c.nombre)}</h2>
        <div class="muted small mono">${esc(c.expediente)} · ${esc(c.tribunal)}</div>
      </div>
      <div class="small muted">${esc(c.documentos)} documentos · reclamo ${esc(c.monto)}</div>
    </div>
    <div class="sep"></div>
    <div class="linea">
      ${gente.map(p => `
        <div class="res" onclick="abrirPersona('${p.id}')">
          <div class="avatar">${esc(p.iniciales)}</div>
          <div style="flex:1">
            <div><strong>${esc(p.nombre)}</strong>
              <span class="tag ok">${esc(p.casos.find(x => x.id === c.id).rol)}</span></div>
            <div class="por">${esc(p.lugar || '')} · ${esc(p.ultimo)}</div>
          </div>
          <div class="small muted">${esc(p.telefono || '—')}</div>
        </div>`).join('')}
    </div>`;
})();

/* ---------------- 4. alta en un paso ---------------- */
function leerFirma(texto) {
  const lineas = texto.split('\n').map(l => l.trim()).filter(Boolean);
  const campos = {};
  const correo = texto.match(/[\w.+-]+@[\w-]+\.[\w.]{2,}/);
  if (correo) campos.Correo = correo[0];
  const tels = texto.match(/\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b/g) || [];
  if (tels[0]) campos.Telefono = tels[0];
  if (tels[1]) campos.Fax = tels[1];
  const org = lineas.find(l => /LLP|LLC|P\.A\.|& ASSOCIATES|INC\b|COMPANY|CENTER|DEPARTMENT/i.test(l));
  if (org) campos.Organizacion = org.replace(/,\s*$/, '');
  const persona = lineas.find(l =>
    /^[A-Z][a-zA-Z.'-]+(\s+[A-Z][a-zA-Z.'-]*){1,3},?\s*(Esquire|Esq\.?|MD|PhD)?$/.test(l) && l !== org);
  if (persona) campos.Nombre = persona.replace(/,\s*(Esquire|Esq\.?)$/i, '');
  if (persona && /Esquire|Esq\./i.test(persona)) campos.Rol = 'Abogado';
  const dir = lineas.find(l => /\d+\s+[A-Za-z].*(Road|Rd|Street|St|Avenue|Ave|Drive|Blvd)/i.test(l));
  if (dir) campos.Direccion = dir;
  const ciudad = lineas.find(l => /,\s*(South Carolina|SC|North Carolina|NC|New York|NY)\s*\d{5}/i.test(l));
  if (ciudad) campos.Ciudad = ciudad;
  const barra = texto.match(/Federal Bar No\.?\s*(\d+)/i);
  if (barra) campos['Numero de colegiado'] = barra[1];
  return campos;
}

function pintarPropuesta(texto) {
  const campos = leerFirma(texto);
  const n = Object.keys(campos).length;
  $('#alta-estado').textContent = n ? `${n} datos reconocidos` : 'no se reconocio nada';
  $('#propuesta').innerHTML = n ? `
    <table>${Object.entries(campos).map(([k, v]) => `
      <tr><td class="muted small" style="width:38%">${esc(k)}</td>
          <td><strong>${esc(v)}</strong></td></tr>`).join('')}</table>
    <div class="row" style="margin-top:14px">
      <button>Guardar contacto</button>
      <button class="ghost">Ligar a un caso</button>
    </div>
    <p class="small muted" style="margin-top:10px">
      Ningun campo vacio que rellenar: lo que no aparece en el texto, no se pide.</p>`
    : '<p class="small muted">No se reconocio ningun dato en ese texto.</p>';
}
$('#btn-leer').onclick = () => pintarPropuesta($('#firma').value);
$('#btn-ejemplo').onclick = () => { $('#firma').value = FIRMA_EJEMPLO; pintarPropuesta(FIRMA_EJEMPLO); };
$('#firma').placeholder = FIRMA_EJEMPLO;

/* ---------------- 5. duplicados ---------------- */
$('#duplicados').innerHTML = DUPLICADOS.map(d => `
  <div class="dup">
    <div class="lado">
      <div class="muted small">${esc(d.a.origen)}</div>
      <div>${esc(d.a.datos)}</div>
    </div>
    <div class="flecha">⟷</div>
    <div class="lado">
      <div class="muted small">${esc(d.b.origen)}</div>
      <div>${esc(d.b.datos)}</div>
    </div>
  </div>
  <div style="padding:2px 0 16px">
    <div class="row" style="justify-content:space-between">
      <strong>${esc(d.nombre)}</strong>
      <span class="tag ${d.confianza > 0.9 ? 'ok' : 'warn'}">coincidencia ${Math.round(d.confianza * 100)}%</span>
    </div>
    <ul class="porque">${d.porque.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
    <div class="row" style="margin-top:10px">
      <button>Unir las dos</button>
      <button class="ghost">Son personas distintas</button>
      <span class="small muted" style="align-self:center">Se puede deshacer despues</span>
    </div>
  </div>`).join('');

/* ---------------- 6. comparativa ---------------- */
const COMPARATIVA = [
  ['Un contacto es una ficha de campos',
   'Treinta o mas campos por contacto (fax, apodo, perfiles sociales, cumpleanos). Casi todos vacios y envejecen sin avisar.',
   'Cabecera minima con lo que existe, mas una linea de tiempo de lo que ha pasado. La historia no envejece.'],
  ['El usuario organiza a mano',
   'Grupos, etiquetas y categorias que hay que crear y mantener. En el Outlook nuevo solo se ven diez categorias y no se pueden renombrar.',
   'El rol de cada persona se deriva de los documentos y las llamadas que el despacho ya genera. Cero mantenimiento.'],
  ['Buscar es recordar el nombre',
   'El buscador espera un nombre; el telefono entrante o el numero de expediente no llevan a nadie.',
   'Una sola caja que acepta nombre, telefono, expediente o rol, y explica por que aparece cada resultado.'],
  ['Los duplicados los resuelve el usuario',
   'Un boton "combinar y corregir" que fusiona en bloque. Cuando se equivoca, borra datos sin decir cuales.',
   'Propuestas de una en una, con el motivo escrito, y reversibles.'],
  ['Sincronizar todo es mejor',
   'Cada direccion que se toca se vuelve contacto ("otros contactos"), y el usuario tiene que saber en que lista buscar.',
   'Una sola lista. Lo que no tiene historia ni caso no ocupa sitio en el directorio.'],
  ['La persona es la unidad de trabajo',
   'Ninguna libreta responde "quien participa en este asunto" sin grupos manuales.',
   'Vista por expediente: quien es quien, con su rol y su ultimo contacto.'],
  ['Dar de alta es rellenar un formulario',
   'Mas de treinta campos repartidos en pestanas. Se teclea nombre y telefono y el resto queda vacio.',
   'Pegar una firma, una tarjeta o un pie de escrito: el sistema propone y la persona confirma.'],
];
$('#tabla-comparativa').innerHTML = COMPARATIVA.map(([s, a, b]) => `
  <tr><td><strong>${esc(s)}</strong></td>
      <td class="antes">${esc(a)}</td>
      <td class="despues">${esc(b)}</td></tr>`).join('');
