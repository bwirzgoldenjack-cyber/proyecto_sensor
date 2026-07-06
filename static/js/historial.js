let historialCompleto = [];

function cargarHistorial() {
    // Antes esto pedía siempre "/obtener_historial" sin fecha, y el
    // backend por defecto devuelve solo el dia de HOY (ver app.py:
    // fecha_filtro = fecha if fecha else datetime.now()...). Como acá
    // nunca se mandaba la fecha elegida en el filtro, el array
    // historialCompleto jamás tenia los datos de otros dias, y el
    // filtro de fecha en el cliente (filtrarTabla) no tenia nada para
    // encontrar -> siempre "NO HAY EVENTOS" para cualquier dia que no
    // fuera hoy.
    //
    // Ahora se le pide al backend directamente la fecha seleccionada
    // en el input #filtroFecha (o "hoy" si no eligieron ninguna).
    const fecha = document.getElementById("filtroFecha").value;
    const params = new URLSearchParams();
    if (fecha) params.set("fecha", fecha);

    fetch("/obtener_historial?" + params.toString())
        .then(res => res.json())
        .then(data => {
            historialCompleto = data;
            filtrarTabla();
        })
        .catch(err => console.error("Error cargando historial:", err));
}

function mostrarTabla(datos) {
    const tabla = document.getElementById("tablaBody");
    tabla.innerHTML = "";
    if (datos.length === 0) {
        tabla.innerHTML = `
            <tr>
                <td colspan="4" style="text-align:center;">NO HAY EVENTOS</td>
            </tr>`;
        return;
    }
    const html = datos.map(evento => {
        const badge = evento.tipo.toUpperCase() === "ENTRADA"
            ? `<span class="entrada">↑ ENTRADA</span>`
            : `<span class="salida">↓ SALIDA</span>`;
        return `
            <tr>
                <td>${evento.hora}</td>
                <td>${badge}</td>
                <td>${evento.sucursal}</td>
                <td>${evento.puerta}</td>
            </tr>`;
    }).join("");
    tabla.innerHTML = html;
}

function actualizarCards(datos) {
    const entradas = datos.filter(e => e.tipo.toUpperCase() === "ENTRADA").length;
    const salidas  = datos.filter(e => e.tipo.toUpperCase() === "SALIDA").length;
    document.querySelectorAll(".card h2")[0].innerHTML = datos.length;
    document.querySelectorAll(".card h2")[1].innerHTML = entradas;
    document.querySelectorAll(".card h2")[2].innerHTML = salidas;
}

function filtrarTabla() {
    // La fecha YA vino filtrada desde el backend (cargarHistorial),
    // así que acá solo quedan por filtrar en el cliente: texto de
    // sucursal y tipo. Ya no hay que volver a comparar fechas.
    const texto = document.getElementById("buscarSucursal").value.toLowerCase();
    const tipo  = document.getElementById("filtroTipo").value;

    let filtrados = historialCompleto.filter(evento => {
        const coincideSucursal = evento.sucursal.toLowerCase().includes(texto);
        const coincideTipo = tipo === "TODOS" || evento.tipo.toUpperCase() === tipo;
        return coincideSucursal && coincideTipo;
    });

    mostrarTabla(filtrados);
    actualizarCards(filtrados);
}

function obtenerFiltros() {
    const sucursal = document.getElementById("buscarSucursal").value.trim();
    const tipo  = document.getElementById("filtroTipo").value;
    const fecha = document.getElementById("filtroFecha").value;
    const params = new URLSearchParams();
    if (sucursal) params.set("sucursal", sucursal);
    if (tipo !== "TODOS") params.set("tipo", tipo);
    if (fecha) params.set("fecha", fecha);
    return params.toString();
}

document.addEventListener("DOMContentLoaded", () => {
    iniciarReloj();     // ← utils.js
    iniciarLogout();    // ← utils.js

    document.getElementById("buscarSucursal").addEventListener("keyup", filtrarTabla);
    document.getElementById("filtroTipo").addEventListener("change", filtrarTabla);

    // El filtro de fecha ahora dispara una nueva consulta al backend,
    // no solo un re-filtrado en el cliente.
    document.getElementById("filtroFecha").addEventListener("change", cargarHistorial);

    document.querySelector(".pdf").addEventListener("click", () => {
        window.open("/exportar_pdf?" + obtenerFiltros(), "_blank");
    });
    document.querySelector(".excel").addEventListener("click", () => {
        window.open("/exportar_excel?" + obtenerFiltros(), "_blank");
    });

    cargarHistorial();
    setInterval(cargarHistorial, 5000);
});
