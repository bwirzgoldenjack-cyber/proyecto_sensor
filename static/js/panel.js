// =====================================
// HORA Y FECHA
// =====================================
function actualizarHora() {

    const ahora = new Date();

    const hora = ahora.toLocaleTimeString('es-AR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const fecha = ahora.toLocaleDateString('es-AR', {
        day: '2-digit',
        month: 'long',
        year: 'numeric'
    });

    document.getElementById("hora").innerHTML = hora;
    document.getElementById("fecha").innerHTML = fecha.toUpperCase();
}


// =====================================
// ACTUALIZAR DATOS PUERTAS
// =====================================
function actualizar() {

    fetch("/conn_puertas")
    .then(r => r.json())
    .then(data => {

        let selector = document.getElementById("selectorPuerta");

        let puerta = selector.value.toLowerCase().trim();

        let actual = data.puertas.find(p =>
            p.puerta.toLowerCase().trim() === puerta
        );

        if (!actual) return;

        document.getElementById("personas").innerHTML = actual.personas;
        document.getElementById("entradas").innerHTML = actual.entradas;
        document.getElementById("salidas").innerHTML = actual.salidas;

        // actualizar texto visible de sucursal
        let texto = selector.options[selector.selectedIndex].text;
        document.getElementById("sucursalActual").innerHTML = texto;
    })
    .catch(error => {
        console.log("Error al actualizar:", error);
    });
}


// =====================================
// INICIAR EVENTOS
// =====================================

// actualización automática
setInterval(actualizar, 3000);
setInterval(actualizarHora, 1000);

// iniciar apenas carga la página
actualizar();
actualizarHora();

// actualizar cuando cambia selector
document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("selectorPuerta")
        .addEventListener("change", actualizar);
});