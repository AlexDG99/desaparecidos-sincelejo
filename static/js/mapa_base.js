// Mapa base con respaldo automático: si un proveedor de teselas no responde, se pasa al siguiente.
// Todos son gratuitos y no requieren clave de API.
(function () {
  var PROVEEDORES = [
    { url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', opts: { maxZoom: 19,
      attribution: '&copy; Colaboradores de <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' } },
    { url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', opts: { maxZoom: 19, subdomains: 'abcd',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>' } },
    { url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', opts: { maxZoom: 19,
      attribution: 'Tiles &copy; Esri' } }
  ];

  window.crearMapaBase = function (map) {
    var actual = -1, capa = null, errores = 0, cargadas = 0;

    function aviso(texto) {
      var el = map.getContainer().querySelector('.mapa-aviso');
      if (!texto) { if (el) el.remove(); return; }
      if (!el) {
        el = document.createElement('div');
        el.className = 'mapa-aviso';
        el.setAttribute('role', 'status');
        map.getContainer().appendChild(el);
      }
      el.textContent = texto;
    }

    function usar(i) {
      if (capa) map.removeLayer(capa);
      if (i >= PROVEEDORES.length) {
        aviso('No se pudo cargar el mapa base. Revise su conexión a internet; igualmente puede escribir la dirección o el barrio.');
        return;
      }
      actual = i; errores = 0; cargadas = 0;
      capa = L.tileLayer(PROVEEDORES[i].url, PROVEEDORES[i].opts).addTo(map);
      capa.on('tileload', function () { cargadas++; aviso(null); });
      capa.on('tileerror', function () {
        errores++;
        if (errores >= 3 && cargadas === 0) usar(actual + 1);
      });
    }
    usar(0);
    return map;
  };
})();
