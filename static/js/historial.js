function actualizarHora(){

    const ahora = new Date();

    const hora = ahora.toLocaleTimeString('es-AR');

    const fecha = ahora.toLocaleDateString('es-AR',{
        day:'2-digit',
        month:'long',
        year:'numeric'
    });

    document.getElementById("hora").innerHTML = hora;

    document.getElementById("fecha").innerHTML =
    fecha.toUpperCase();

}

setInterval(actualizarHora,1000);

actualizarHora();


// =====================================
// VARIABLES
// =====================================

let historialCompleto = [];


// =====================================
// CARGAR HISTORIAL
// =====================================

async function cargarHistorial(){

    try{

        const response = await fetch("/obtener_historial");

        const datos = await response.json();

        historialCompleto = datos;

        // IMPORTANTE:
        // vuelve a aplicar filtros
        filtrarTabla();

    }catch(error){

        console.log("ERROR HISTORIAL:",error);

    }

}


// =====================================
// MOSTRAR TABLA
// =====================================

function mostrarTabla(datos){

    const tabla = document.getElementById("tablaBody");

    tabla.innerHTML = "";

    if(datos.length == 0){

        tabla.innerHTML = `
        
            <tr>

                <td colspan="4" style="text-align:center;">
                    NO HAY EVENTOS
                </td>

            </tr>
        
        `;

        return;

    }

    datos.forEach(evento=>{

        let badge = "";

        if(evento.tipo.toUpperCase() == "ENTRADA"){

            badge = `
            
                <span class="entrada">
                    ↑ ENTRADA
                </span>
            
            `;

        }else{

            badge = `
            
                <span class="salida">
                    ↓ SALIDA
                </span>
            
            `;

        }

        tabla.innerHTML += `
        
            <tr>

                <td>${evento.hora}</td>

                <td>${badge}</td>

                <td>${evento.sucursal}</td>

                <td>${evento.puerta}</td>

            </tr>
        
        `;

    });

}


// =====================================
// ACTUALIZAR CARDS
// =====================================

function actualizarCards(datos){

    let entradas = datos.filter(
        e => e.tipo.toUpperCase() == "ENTRADA"
    ).length;

    let salidas = datos.filter(
        e => e.tipo.toUpperCase() == "SALIDA"
    ).length;

    document.querySelectorAll(".card h2")[0]
    .innerHTML = datos.length;

    document.querySelectorAll(".card h2")[1]
    .innerHTML = entradas;

    document.querySelectorAll(".card h2")[2]
    .innerHTML = salidas;

}


// =====================================
// FILTRAR
// =====================================

function filtrarTabla(){

    const texto = document
    .getElementById("buscarSucursal")
    .value
    .toLowerCase();

    const tipo = document
    .getElementById("filtroTipo")
    .value;

    const fecha = document
    .getElementById("filtroFecha")
    .value;

    let filtrados = historialCompleto.filter(evento=>{

        let coincideSucursal =
        evento.sucursal
        .toLowerCase()
        .includes(texto);

        let coincideTipo =

        tipo == "TODOS" ||

        evento.tipo.toUpperCase() == tipo;

        let coincideFecha = true;

        if(fecha != ""){

            coincideFecha =
            evento.fecha == fecha;

        }

        return coincideSucursal &&
               coincideTipo &&
               coincideFecha;

    });

    mostrarTabla(filtrados);

    actualizarCards(filtrados);

}


// =====================================
// EVENTOS FILTROS
// =====================================

document
.getElementById("buscarSucursal")
.addEventListener("keyup",filtrarTabla);

document
.getElementById("filtroTipo")
.addEventListener("change",filtrarTabla);

document
.getElementById("filtroFecha")
.addEventListener("change",filtrarTabla);


// =====================================
// PDF
// =====================================

document
.querySelector(".pdf")
.addEventListener("click",()=>{

    window.open("/exportar_pdf","_blank");

});


// =====================================
// EXCEL
// =====================================

document
.querySelector(".excel")
.addEventListener("click",()=>{

    window.open("/exportar_excel","_blank");

});


// =====================================
// LOGOUT
// =====================================

document
.querySelector(".logout")
.addEventListener("click",()=>{

    window.location.href = "/logout";

});


// =====================================
// AUTO UPDATE
// =====================================

cargarHistorial();

setInterval(cargarHistorial,5000);