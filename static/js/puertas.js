let sucursalActual = "quilmes";
let todasLasPuertas = [];
let buscador = "";

/* =========================
   RELOJ
========================= */
function actualizarHora() {

    const ahora = new Date();

    const hora = ahora.toLocaleTimeString('es-AR');

    const fecha = ahora.toLocaleDateString('es-AR', {
        day: '2-digit',
        month: 'long',
        year: 'numeric'
    });

    document.getElementById("hora").innerHTML = hora;
    document.getElementById("fecha").innerHTML = fecha.toUpperCase();
}

setInterval(actualizarHora, 1000);
actualizarHora();

/* =========================
   FETCH DATOS
========================= */
function actualizarPuertas() {

    fetch("/conn_puertas")
        .then(r => r.json())
        .then(data => {
            todasLasPuertas = data.puertas;
            renderPuertas();
        });
}

/* =========================
   RENDER
========================= */
function renderPuertas() {

    let grid = document.getElementById("puertasGrid");

    let filtradas = todasLasPuertas.filter(p => {

        return p.sucursal === sucursalActual &&
               p.puerta.toLowerCase().includes(buscador);
    });

    grid.innerHTML = "";

    filtradas.forEach(p => {

        grid.innerHTML += `
            <div class="puerta-card">

                <div class="card-top">

                    <div>
                        <h3>${p.puerta}</h3>
                        <span>${p.sucursal}</span>
                    </div>

                    <div class="estado ${p.online ? "online" : "offline"}">
                        ● ${p.online ? "ONLINE" : "OFFLINE"}
                    </div>

                </div>

                <div class="stats">

                    <div class="box entradas">
                        <span>ENTRADAS HOY</span>
                        <h2>${p.entradas}</h2>
                    </div>

                    <div class="box salidas">
                        <span>SALIDAS HOY</span>
                        <h2>${p.salidas}</h2>
                    </div>

                </div>

                <div class="ultimo-evento">
                    Último evento: ${p.ultimo}
                </div>
<div class="card-actions">

    <button
        class="btn-activar ${p.online ? 'activa' : 'inactiva'}"
        onclick="togglePuerta(${p.id})">

        ${p.online ? "DESACTIVAR" : "ACTIVAR"}

    </button>

    <button
        class="btn-editar"
        onclick="editarPuerta(${p.id}, '${p.puerta}')">

        ✎

    </button>

    <button
        class="btn-eliminar"
        onclick="eliminarPuerta(${p.id})">

        🗑

    </button>

</div>

            </div>
        `;
    });
}

/* =========================
   TOGGLE PUERTA
========================= */
function togglePuerta(id) {

    fetch(`/toggle_puerta/${id}`, {
        method: "POST"
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) actualizarPuertas();
    });
}

/* =========================
   AGREGAR PUERTA
========================= */
function agregarPuerta() {

    let nombre = document.getElementById("nuevaPuerta").value.trim();

    if (nombre === "") {
        alert("Ingresá un nombre");
        return;
    }

    fetch("/agregar_puerta", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            nombre: nombre,
            sucursal: sucursalActual
        })
    })
    .then(r => r.json())
    .then(data => {

        if (data.ok) {
            document.getElementById("nuevaPuerta").value = "";
            actualizarPuertas();
        }
    });
}
/*======================================
editar puerta
========================================*/
function editarPuerta(id, nombreActual){

    let nuevoNombre = prompt(
        "Nuevo nombre de la puerta:",
        nombreActual
    );

    if(!nuevoNombre){
        return;
    }

    fetch(`/editar_puerta/${id}`,{
        method:"POST",
        headers:{
            "Content-Type":"application/json"
        },
        body:JSON.stringify({
            nombre:nuevoNombre
        })
    })
    .then(r => r.json())
    .then(data => {

        if(data.ok){
            actualizarPuertas();
        }

    });

}

function eliminarPuerta(id){

    if(!confirm("¿Eliminar puerta?")){
        return;
    }

    fetch(`/eliminar_puerta/${id}`,{
        method:"POST"
    })
    .then(r => r.json())
    .then(data => {

        if(data.ok){
            actualizarPuertas();
        }

    });

}
/* =========================
   EVENTOS
========================= */
document.addEventListener("DOMContentLoaded", () => {

    const botones = document.querySelectorAll(".sucursal-btn");

    document.querySelector(".logout").addEventListener("click", () => {
        window.location.href = "/logout";
    });

    document.getElementById("buscar").addEventListener("input", (e) => {
        buscador = e.target.value.toLowerCase().trim();
        renderPuertas();
    });

    botones[0].addEventListener("click", () => {

        sucursalActual = "quilmes";

        botones.forEach(b => b.classList.remove("active"));
        botones[0].classList.add("active");

        renderPuertas();
    });

    botones[1].addEventListener("click", () => {

        sucursalActual = "solano";

        botones.forEach(b => b.classList.remove("active"));
        botones[1].classList.add("active");

        renderPuertas();
    });

    actualizarPuertas();
});

/* =========================
   REFRESH CONTROLADO
========================= */
setTimeout(function loop() {
    actualizarPuertas();
    setTimeout(loop, 3000);
}, 3000);