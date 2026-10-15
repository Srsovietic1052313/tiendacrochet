function validarContacto() {
    const nombre = document.getElementById('nombre').value.trim();
    const email = document.getElementById('email').value.trim();
    const mensaje = document.getElementById('mensaje').value.trim();

    if (nombre === "" || email === "" || mensaje === "") {
        alert("Por favor completa todos los campos.");
        return false;
    }
    return true;
}

function validarLogin() {
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    if (email === "" || password === "") {
        alert("Por favor completa todos los campos.");
        return false;
    }
    return true;
}

function validarRegistro() {
    const nombre = document.getElementById('nombre').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    if (nombre === "" || email === "" || password === "") {
        alert("Por favor completa todos los campos.");
        return false;
    }
    if (password.length < 6) {
        alert("La contraseña debe tener al menos 6 caracteres.");
        return false;
    }
    return true;
}

function validarProducto() {
    const nombre = document.getElementById('nombre').value.trim();
    const descripcion = document.getElementById('descripcion').value.trim();
    const precio = document.getElementById('precio').value;
    const stock = document.getElementById('stock').value;
    const categoria = document.getElementById('categoria_id').value;

    if (nombre === "" || descripcion === "" || precio === "" || stock === "" || categoria === "") {
        alert("Por favor completa todos los campos.");
        return false;
    }
    if (parseFloat(precio) < 0 || parseInt(stock) < 0) {
        alert("El precio y el stock no pueden ser negativos.");
        return false;
    }
    return true;
}

function validarBlog() {
    const titulo = document.getElementById('titulo').value.trim();
    const resumen = document.getElementById('resumen').value.trim();
    const contenido = document.getElementById('contenido').value.trim();

    if (titulo === "" || resumen === "" || contenido === "") {
        alert("Por favor completa todos los campos.");
        return false;
    }
    return true;
}
