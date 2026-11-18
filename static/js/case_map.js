// HU-08: mapa interactivo de avistamientos aprobados (ubicación aproximada, vista cronológica opcional).
(function () {
  var urlEl = document.getElementById('mapa-url');
  var cont = document.getElementById('mapa');
  if (!urlEl || !cont) return;
  var url = JSON.parse(urlEl.textContent);
  var map = L.map('mapa');
  crearMapaBase(map);
  var capa = L.layerGroup().addTo(map);
  var datos = null;

  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  function dibujar(cronologico) {
    capa.clearLayers();
    var pts = datos.puntos, coords = [];
    pts.forEach(function (p) {
      var ll = [p.lat, p.lng];
      coords.push(ll);
      L.circle(ll, { radius: datos.radio, color: '#b91c1c', fillOpacity: 0.15 }).addTo(capa);
      var icon = cronologico
        ? L.divIcon({ className: '', html: '<div style="background:#b91c1c;color:#fff;border-radius:50%;width:26px;height:26px;line-height:26px;text-align:center;font-weight:700">' + p.n + '</div>', iconSize: [26, 26] })
        : undefined;
      var m = L.marker(ll, icon ? { icon: icon, title: 'Avistamiento ' + p.n } : { title: 'Avistamiento ' + p.n }).addTo(capa);
      m.bindPopup('<strong>' + esc(p.fecha) + ' ' + esc(p.hora) + '</strong><br>' + esc(p.descripcion) + '<br><small>' + esc(p.ubicacion) + ' (aprox.)</small>');
    });
    if (cronologico && coords.length > 1) L.polyline(coords, { color: '#b91c1c', dashArray: '6 6' }).addTo(capa);
  }

  fetch(url, { headers: { 'Accept': 'application/json' } }).then(function (r) { return r.json(); }).then(function (d) {
    datos = d;
    if (!d.puntos.length) {
      cont.classList.add('d-none');
      document.getElementById('mapa-vacio').classList.remove('d-none');
      return;
    }
    dibujar(false);
    map.fitBounds(L.latLngBounds(d.puntos.map(function (p) { return [p.lat, p.lng]; })).pad(0.3), { maxZoom: 17 });
  });
  document.getElementById('cronologia').addEventListener('change', function (e) { if (datos && datos.puntos.length) dibujar(e.target.checked); });
})();
