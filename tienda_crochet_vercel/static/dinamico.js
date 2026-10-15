/* ==========================================================
   Animaciones de entrada al hacer scroll (IntersectionObserver)
   ========================================================== */

function iniciarAnimacionesEntrada() {
    const elementos = document.querySelectorAll('.animar-entrada');
    if (!elementos.length) return;

    if (!('IntersectionObserver' in window)) {
        elementos.forEach(function (el) { el.classList.add('visible'); });
        return;
    }

    const observador = new IntersectionObserver(function (entradas) {
        entradas.forEach(function (entrada) {
            if (entrada.isIntersecting) {
                entrada.target.classList.add('visible');
                observador.unobserve(entrada.target);
            }
        });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    elementos.forEach(function (el) { observador.observe(el); });
}


/* ==========================================================
   Carrusel / galería de imágenes del producto:
   avanza automáticamente y también se puede mover manualmente
   (flechas, puntos o deslizando con el dedo).
   ========================================================== */

function iniciarGaleriasProducto() {
    document.querySelectorAll('.galeria-producto').forEach(function (galeria) {
        const pista = galeria.querySelector('.galeria-pista');
        const slides = galeria.querySelectorAll('.galeria-slide');
        const puntos = galeria.querySelectorAll('.galeria-punto');
        const btnAnterior = galeria.querySelector('.galeria-anterior');
        const btnSiguiente = galeria.querySelector('.galeria-siguiente');
        const totalSlides = slides.length;

        if (totalSlides <= 1) return; // una sola imagen: no hace falta carrusel

        let indiceActual = 0;
        let temporizador = null;
        const intervaloMs = parseInt(galeria.dataset.autoplay || '4500', 10);

        function irASlide(indice) {
            indiceActual = (indice + totalSlides) % totalSlides;
            pista.style.transform = `translateX(-${indiceActual * 100}%)`;
            puntos.forEach(function (punto, i) {
                punto.classList.toggle('activo', i === indiceActual);
            });
        }

        function reiniciarAutoplay() {
            if (temporizador) clearInterval(temporizador);
            temporizador = setInterval(function () {
                irASlide(indiceActual + 1);
            }, intervaloMs);
        }

        // Interacción manual del usuario: mueve la imagen Y reinicia el temporizador
        // (así el carrusel sigue avanzando solo después de que el usuario la mueva)
        function interaccionManual(nuevoIndice) {
            irASlide(nuevoIndice);
            reiniciarAutoplay();
        }

        if (btnSiguiente) {
            btnSiguiente.addEventListener('click', function () { interaccionManual(indiceActual + 1); });
        }
        if (btnAnterior) {
            btnAnterior.addEventListener('click', function () { interaccionManual(indiceActual - 1); });
        }
        puntos.forEach(function (punto, i) {
            punto.addEventListener('click', function () { interaccionManual(i); });
        });

        // Deslizar con el dedo (móvil) o con el mouse
        let inicioX = null;
        galeria.addEventListener('touchstart', function (e) { inicioX = e.touches[0].clientX; }, { passive: true });
        galeria.addEventListener('touchend', function (e) {
            if (inicioX === null) return;
            const deltaX = e.changedTouches[0].clientX - inicioX;
            if (Math.abs(deltaX) > 40) {
                interaccionManual(indiceActual + (deltaX < 0 ? 1 : -1));
            }
            inicioX = null;
        });

        // Pausar mientras el mouse está encima (el usuario está mirando esa imagen)
        galeria.addEventListener('mouseenter', function () { if (temporizador) clearInterval(temporizador); });
        galeria.addEventListener('mouseleave', reiniciarAutoplay);

        irASlide(0);
        reiniciarAutoplay();
    });
}


/* ==========================================================
   Selector de variantes (medida/tamaño) en la ficha de producto:
   actualiza el precio, el stock y la cantidad máxima al elegir.
   ========================================================== */

function iniciarSelectorVariantes() {
    document.querySelectorAll('.selector-variantes').forEach(function (selector) {
        const radios = selector.querySelectorAll('input[type="radio"]');
        const precioMostrado = document.getElementById('precio-mostrado');
        const stockMostrado = document.getElementById('stock-mostrado');
        const inputCantidad = document.getElementById('cantidad');

        function actualizar(radioSeleccionado) {
            const precio = parseInt(radioSeleccionado.dataset.precio, 10);
            const stock = parseInt(radioSeleccionado.dataset.stock, 10);

            if (precioMostrado) {
                precioMostrado.textContent = `$${precio.toLocaleString('en-US')} COP`;
            }
            if (stockMostrado) {
                stockMostrado.textContent = stock > 0 ? `✓ ${stock} disponibles` : 'Agotado por el momento';
            }
            if (inputCantidad) {
                inputCantidad.max = stock > 0 ? stock : 1;
                if (parseInt(inputCantidad.value, 10) > stock) {
                    inputCantidad.value = stock > 0 ? 1 : 1;
                }
            }

            // Respaldo visual por si el navegador no soporta :has()
            selector.querySelectorAll('.pastilla-variante').forEach(function (etiqueta) {
                etiqueta.classList.remove('seleccionada');
            });
            radioSeleccionado.closest('.pastilla-variante').classList.add('seleccionada');
        }

        radios.forEach(function (radio) {
            radio.addEventListener('change', function () { actualizar(radio); });
            if (radio.checked) actualizar(radio);
        });
    });
}


/* ==========================================================
   Burbujas laterales de encuestas (Proveedores / Clientes):
   aparecen al cargar la página, y tras un momento se recogen
   dejando solo el ícono (se vuelven a expandir con el mouse encima).
   ========================================================== */

function iniciarBurbujasLaterales() {
    const contenedor = document.getElementById('burbujas-laterales');
    if (!contenedor) return;

    // Pequeña espera para que no aparezcan de golpe junto con el resto de la página
    setTimeout(function () {
        contenedor.classList.add('visible');
    }, 500);

    // Tras un momento visibles, se recogen dejando solo el ícono
    setTimeout(function () {
        contenedor.classList.add('colapsada');
    }, 6000);
}


document.addEventListener('DOMContentLoaded', function () {
    iniciarAnimacionesEntrada();
    iniciarGaleriasProducto();
    iniciarSelectorVariantes();
    iniciarBurbujasLaterales();
});
