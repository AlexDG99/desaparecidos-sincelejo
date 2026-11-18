// HU-04 / HU-05: selector de ubicación en mapa, geolocalización y carga con progreso cancelable.
(function () {
  var form = document.getElementById('form-avistamiento');
  if (!form) return;
  var centro = JSON.parse(document.getElementById('centro-mapa').textContent);
  var lat = document.getElementById('id_latitud'), lng = document.getElementById('id_longitud');
  var map = L.map('mapa-selector').setView(centro, 14);
  crearMapaBase(map);
  var marker = null;
  function fijar(ll) {
    lat.value = ll.lat.toFixed(6); lng.value = ll.lng.toFixed(6);
    if (marker) marker.setLatLng(ll); else marker = L.marker(ll).addTo(map);
  }
  if (lat.value && lng.value) { var ini = L.latLng(parseFloat(lat.value), parseFloat(lng.value)); fijar(ini); map.setView(ini, 16); }
  map.on('click', function (e) { fijar(e.latlng); });
  document.getElementById('btn-ubicacion').addEventListener('click', function () {
    if (!navigator.geolocation) { alert('Su navegador no permite obtener la ubicación.'); return; }
    navigator.geolocation.getCurrentPosition(function (pos) {
      var ll = L.latLng(pos.coords.latitude, pos.coords.longitude); fijar(ll); map.setView(ll, 16);
    }, function () { alert('No fue posible obtener su ubicación. Márquela en el mapa o escriba una dirección.'); });
  });

  // Carga con indicador de progreso y opción de cancelar (HU-05 CA3); el formulario conserva sus datos al cancelar.
  var archivos = document.getElementById('id_evidencias');
  var caja = document.getElementById('progreso');
  var barra = caja.querySelector('.progress-bar');
  var contenedorBarra = caja.querySelector('.progress');
  var enviar = document.getElementById('btn-enviar');
  var xhr = null;
  form.addEventListener('submit', function (e) {
    if (!archivos || !archivos.files.length || !window.XMLHttpRequest || !window.FormData) return;
    e.preventDefault();
    xhr = new XMLHttpRequest();
    xhr.open('POST', form.action || window.location.href);
    xhr.upload.onprogress = function (ev) {
      if (!ev.lengthComputable) return;
      var pct = Math.round(ev.loaded / ev.total * 100);
      barra.style.width = pct + '%'; barra.textContent = pct + '%'; contenedorBarra.setAttribute('aria-valuenow', pct);
    };
    xhr.onload = function () { document.open(); document.write(xhr.responseText); document.close(); };
    xhr.onerror = function () { caja.classList.add('d-none'); enviar.disabled = false; alert('Error de conexión. Intente de nuevo.'); };
    caja.classList.remove('d-none'); enviar.disabled = true;
    xhr.send(new FormData(form));
  });
  document.getElementById('btn-cancelar').addEventListener('click', function () {
    if (xhr) xhr.abort();
    caja.classList.add('d-none'); enviar.disabled = false; barra.style.width = '0%'; barra.textContent = '0%';
  });
})();
