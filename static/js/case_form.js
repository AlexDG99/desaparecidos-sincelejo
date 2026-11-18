// Muestra los campos de autorización solo cuando la persona desaparecida es menor de edad (HU-14).
(function () {
  var edad = document.getElementById('id_edad');
  var calidad = document.getElementById('id_calidad_declarada');
  var auth = document.getElementById('id_autorizacion_menor');
  if (!edad || !calidad || !auth) return;
  var bloques = [calidad.closest('.mb-3'), auth.closest('.mb-3')];
  function actualizar() {
    var esMenor = edad.value !== '' && parseInt(edad.value, 10) < 18;
    bloques.forEach(function (b) { if (b) b.classList.toggle('d-none', !esMenor); });
  }
  edad.addEventListener('input', actualizar);
  actualizar();
})();
