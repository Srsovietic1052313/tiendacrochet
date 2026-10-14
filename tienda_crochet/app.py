from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import re
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'clave-secreta-tienda-del-crochet-2026'

# Carpeta donde se guardan las fotos de los productos que sube el admin
CARPETA_IMAGENES = os.path.join('static', 'img', 'productos')
EXTENSIONES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
app.config['CARPETA_IMAGENES'] = CARPETA_IMAGENES
os.makedirs(CARPETA_IMAGENES, exist_ok=True)

# Carpeta donde se guarda el video de presentación (si el admin sube un archivo en vez de un enlace)
CARPETA_VIDEOS = os.path.join('static', 'video')
EXTENSIONES_VIDEO_PERMITIDAS = {'mp4', 'webm', 'mov', 'ogg'}
app.config['CARPETA_VIDEOS'] = CARPETA_VIDEOS
os.makedirs(CARPETA_VIDEOS, exist_ok=True)

# Límite de tamaño de subida (cubre videos + varias fotos en una misma petición)
app.config['MAX_CONTENT_LENGTH'] = 120 * 1024 * 1024  # 120 MB


@app.errorhandler(413)
def archivo_demasiado_grande(error):
    return (
        "El archivo que intentaste subir supera el límite permitido (120 MB). "
        "Para videos pesados, es mejor pegar un enlace de YouTube o Vimeo en vez de subir el archivo. "
        "Usa el botón ← de tu navegador para volver e intentarlo de nuevo.",
        413
    )


def extension_permitida(nombre_archivo):
    return '.' in nombre_archivo and nombre_archivo.rsplit('.', 1)[1].lower() in EXTENSIONES_PERMITIDAS


def extension_video_permitida(nombre_archivo):
    return '.' in nombre_archivo and nombre_archivo.rsplit('.', 1)[1].lower() in EXTENSIONES_VIDEO_PERMITIDAS


def guardar_imagen_producto(archivo):
    """Guarda la imagen subida con un nombre único y devuelve su nombre de archivo, o None si no se subió nada válido."""
    if archivo and archivo.filename != '' and extension_permitida(archivo.filename):
        nombre_seguro = secure_filename(archivo.filename)
        nombre_final = f"{int(datetime.now().timestamp() * 1000)}_{nombre_seguro}"
        archivo.save(os.path.join(app.config['CARPETA_IMAGENES'], nombre_final))
        return nombre_final
    return None


def guardar_video(archivo):
    """Guarda el video subido con un nombre único y devuelve su nombre de archivo, o None si no se subió nada válido."""
    if archivo and archivo.filename != '' and extension_video_permitida(archivo.filename):
        nombre_seguro = secure_filename(archivo.filename)
        nombre_final = f"{int(datetime.now().timestamp() * 1000)}_{nombre_seguro}"
        archivo.save(os.path.join(app.config['CARPETA_VIDEOS'], nombre_final))
        return nombre_final
    return None


def datos_embed_video(url):
    """A partir de un enlace de YouTube o Vimeo, devuelve (plataforma, id_del_video).
    Si no reconoce la plataforma devuelve (None, None) y se usa la URL tal cual en un <video>."""
    if not url:
        return None, None
    url = url.strip()

    patrones_youtube = [
        r'youtu\.be/([A-Za-z0-9_-]{6,})',
        r'youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})',
        r'youtube\.com/embed/([A-Za-z0-9_-]{6,})',
        r'youtube\.com/shorts/([A-Za-z0-9_-]{6,})',
    ]
    for patron in patrones_youtube:
        coincidencia = re.search(patron, url)
        if coincidencia:
            return 'youtube', coincidencia.group(1)

    coincidencia = re.search(r'vimeo\.com/(\d+)', url)
    if coincidencia:
        return 'vimeo', coincidencia.group(1)

    return None, None


def conectar_bd():
    conexion = sqlite3.connect('tienda.db')
    conexion.row_factory = sqlite3.Row  # permite acceder a las columnas por nombre, ej: fila['nombre']
    return conexion


def inicializar_bd():
    conexion = conectar_bd()

    # Usuarios: pueden ser 'admin' o 'cliente'
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'cliente',
            telefono TEXT,
            direccion TEXT,
            fecha_registro TEXT NOT NULL
        )
    ''')

    # Categorías de productos
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL
        )
    ''')

    # Productos: cada uno pertenece a UNA categoría.
    # "precio" y "stock" funcionan como valores BASE: se usan tal cual si el
    # producto no tiene variantes, y quedan de respaldo si las tiene.
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            precio REAL NOT NULL,
            stock INTEGER NOT NULL,
            categoria_id INTEGER NOT NULL,
            destacado INTEGER NOT NULL DEFAULT 0,
            fecha_registro TEXT NOT NULL,
            imagen TEXT,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id)
        )
    ''')

    # Migración: si la tabla productos ya existía sin la columna "imagen", la agregamos
    columnas_productos = [c['name'] for c in conexion.execute("PRAGMA table_info(productos)").fetchall()]
    if 'imagen' not in columnas_productos:
        conexion.execute("ALTER TABLE productos ADD COLUMN imagen TEXT")

    # Galería de imágenes por producto (multi-imagen, con orden para el carrusel)
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS producto_imagenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            imagen TEXT NOT NULL,
            orden INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    ''')

    # Variantes de un producto: distintas medidas/tallas, cada una con su propio precio y stock.
    # Ej: un amigurumi en tamaño Pequeño / Mediano / Grande, cada uno a un precio distinto.
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS producto_variantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            medida TEXT NOT NULL,
            precio REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    ''')

    # Pedidos: cada uno pertenece a UN usuario
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            total REAL NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    ''')

    # Detalle de cada pedido (los productos que contiene)
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS pedido_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            producto_id INTEGER,
            nombre_producto TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            precio_unitario REAL NOT NULL,
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        )
    ''')

    # Publicaciones del blog (ya no se administra desde el panel, se conserva la tabla por compatibilidad)
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            resumen TEXT NOT NULL,
            contenido TEXT NOT NULL,
            autor TEXT NOT NULL,
            fecha TEXT NOT NULL
        )
    ''')

    # Migración: portada y video (archivo o enlace) por publicación del blog
    columnas_blog = [c['name'] for c in conexion.execute("PRAGMA table_info(blog_posts)").fetchall()]
    if 'imagen' not in columnas_blog:
        conexion.execute("ALTER TABLE blog_posts ADD COLUMN imagen TEXT")
    if 'video_archivo' not in columnas_blog:
        conexion.execute("ALTER TABLE blog_posts ADD COLUMN video_archivo TEXT")
    if 'video_url' not in columnas_blog:
        conexion.execute("ALTER TABLE blog_posts ADD COLUMN video_url TEXT")

    # Opiniones/comentarios que deja el admin o cualquier visitante en una publicación del blog
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS blog_comentarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            comentario TEXT NOT NULL,
            es_admin INTEGER NOT NULL DEFAULT 0,
            fecha TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES blog_posts(id)
        )
    ''')

    # Contenido editable de la página "Sobre nosotros" (un único registro, id = 1)
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS sobre_nosotros (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            historia TEXT NOT NULL,
            mision TEXT NOT NULL,
            vision TEXT NOT NULL
        )
    ''')

    # Video de presentación de la página principal (un único registro, id = 1)
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS video_presentacion (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            titulo TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            video_archivo TEXT,
            video_url TEXT
        )
    ''')

    # Migración: título e imagen editables para la sección de historia
    columnas_sobre_nosotros = [c['name'] for c in conexion.execute("PRAGMA table_info(sobre_nosotros)").fetchall()]
    if 'historia_titulo' not in columnas_sobre_nosotros:
        conexion.execute("ALTER TABLE sobre_nosotros ADD COLUMN historia_titulo TEXT")
    if 'historia_imagen' not in columnas_sobre_nosotros:
        conexion.execute("ALTER TABLE sobre_nosotros ADD COLUMN historia_imagen TEXT")

    # Mensajes del formulario de contacto
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            fecha TEXT NOT NULL,
            leido INTEGER NOT NULL DEFAULT 0
        )
    ''')

    # Respuestas de la encuesta de clientes (visible desde la interfaz principal)
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS encuestas_respuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            email TEXT,
            calificacion INTEGER NOT NULL,
            comentario TEXT,
            fecha TEXT NOT NULL
        )
    ''')

    # Registro de proveedores interesados en ser aliados comerciales
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa TEXT NOT NULL,
            contacto_nombre TEXT NOT NULL,
            telefono TEXT NOT NULL,
            email TEXT NOT NULL,
            productos_servicios TEXT NOT NULL,
            fecha TEXT NOT NULL
        )
    ''')

    # Configuración general del sitio: contacto y ubicación del mapa (un único registro, id = 1)
    conexion.execute('''
        CREATE TABLE IF NOT EXISTS configuracion (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            telefono TEXT NOT NULL,
            whatsapp TEXT NOT NULL,
            email TEXT NOT NULL,
            direccion TEXT NOT NULL,
            mapa_lat REAL NOT NULL,
            mapa_lng REAL NOT NULL,
            mapa_zoom INTEGER NOT NULL DEFAULT 16
        )
    ''')

    conexion.commit()

    # ---- Datos de ejemplo (solo la primera vez que se crea la base) ----
    hay_categorias = conexion.execute("SELECT COUNT(*) AS total FROM categorias").fetchone()['total']

    if hay_categorias == 0:
        hoy = datetime.now().isoformat()

        # Usuario administrador por defecto
        conexion.execute(
            "INSERT INTO usuarios (nombre, email, password_hash, rol, fecha_registro) VALUES (?, ?, ?, ?, ?)",
            ('Administradora', 'admin@crochet.com', generate_password_hash('admin123'), 'admin', hoy)
        )

        categorias = [
            'Prendas Femeninas', 'Prendas Masculinas', 'Artículos de Hogar',
            'Calzado', 'Sección de Bebés', 'Artículos de Almacenamiento',
            'Accesorios', 'Amigurumis', 'Bolsos', 'Ropa y mantas'
        ]
        for nombre_categoria in categorias:
            conexion.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre_categoria,))

        productos_ejemplo = [
            ('Osito Amigurumi', 'Tierno osito tejido a mano en algodón suave, ideal para regalar.', 70000, 12, 1, 1),
            ('Bolso Flores', 'Bolso tejido estilo granny square con flores de colores.', 120000, 8, 2, 1),
            ('Manta para bebé', 'Manta suave y delicada tejida en punto abanico, perfecta para el bebé.', 150000, 5, 3, 1),
            ('Llavero Corazón', 'Llavero en forma de corazón tejido en punto amigurumi.', 20000, 25, 4, 1),
            ('Conejito Amigurumi', 'Conejito tejido con orejas largas, disponible en varios colores.', 65000, 10, 1, 0),
            ('Bolso Tote Natural', 'Bolso grande tejido en hilo de algodón crudo, resistente y elegante.', 135000, 6, 2, 0),
            ('Gorro Invierno', 'Gorro tejido en punto trenzado, abrigado y suave.', 45000, 15, 3, 0),
            ('Pulsera Corazones', 'Pulsera artesanal con pequeños corazones tejidos.', 15000, 30, 4, 0),
        ]
        ids_productos = []
        for nombre, descripcion, precio, stock, categoria_id, destacado in productos_ejemplo:
            cursor = conexion.execute(
                "INSERT INTO productos (nombre, descripcion, precio, stock, categoria_id, destacado, fecha_registro) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nombre, descripcion, precio, stock, categoria_id, destacado, hoy)
            )
            ids_productos.append(cursor.lastrowid)

        # Ejemplo de variantes de medida/precio en el primer producto (Osito Amigurumi),
        # para mostrar cómo el cliente puede elegir tamaño y precio desde la ficha del producto.
        id_osito = ids_productos[0]
        variantes_ejemplo = [
            (id_osito, 'Pequeño (10 cm)', 55000, 10),
            (id_osito, 'Mediano (18 cm)', 70000, 8),
            (id_osito, 'Grande (28 cm)', 95000, 4),
        ]
        for producto_id, medida, precio_v, stock_v in variantes_ejemplo:
            conexion.execute(
                "INSERT INTO producto_variantes (producto_id, medida, precio, stock) VALUES (?, ?, ?, ?)",
                (producto_id, medida, precio_v, stock_v)
            )

        posts_ejemplo = [
            ('5 puntos básicos de crochet que debes conocer',
             'Te contamos cuáles son los puntos esenciales para empezar a tejer.',
             'Si estás empezando en el mundo del crochet, dominar unos pocos puntos básicos '
             'te abrirá las puertas a mil proyectos distintos: cadeneta, punto bajo, punto alto, '
             'medio punto alto y punto deslizado. Con estos cinco puedes tejer desde amigurumis '
             'hasta mantas completas. La práctica constante es la clave para tejer con tensión pareja.',
             'La Tienda del Crochet', hoy),
            ('Cómo cuidar tus piezas tejidas a mano',
             'Consejos para que tus prendas y accesorios de crochet duren muchos años.',
             'Las piezas tejidas a mano merecen un cuidado especial. Te recomendamos lavarlas a mano '
             'con agua fría y jabón neutro, evitar torcerlas al secar y dejarlas secar en posición '
             'horizontal sobre una toalla. Así conservarás la forma y el color de tus tejidos por más tiempo.',
             'La Tienda del Crochet', hoy),
        ]
        for titulo, resumen, contenido, autor, fecha in posts_ejemplo:
            conexion.execute(
                "INSERT INTO blog_posts (titulo, resumen, contenido, autor, fecha) VALUES (?, ?, ?, ?, ?)",
                (titulo, resumen, contenido, autor, fecha)
            )

        conexion.commit()

    # Contenido por defecto de "Sobre nosotros" (independiente, para que se cree
    # tanto en bases de datos nuevas como en bases de datos ya existentes)
    hay_sobre_nosotros = conexion.execute(
        "SELECT COUNT(*) AS total FROM sobre_nosotros"
    ).fetchone()['total']

    if hay_sobre_nosotros == 0:
        conexion.execute(
            "INSERT INTO sobre_nosotros (id, historia_titulo, historia, mision, vision, historia_imagen) "
            "VALUES (1, ?, ?, ?, ?, NULL)",
            (
                '¿Quiénes somos?',
                'En La Tienda del Crochet, cada puntada lleva amor, dedicación y el deseo de hacer tu vida '
                'más bonita. Nacimos de la pasión por el tejido artesanal y hoy trabajamos para llevar a tus '
                'manos piezas únicas, hechas con materiales de la mejor calidad y mucho cariño.',
                'Crear piezas de crochet únicas, hechas a mano con materiales de calidad, que acompañen '
                'momentos especiales y lleven amor y dedicación a cada hogar colombiano.',
                'Ser reconocidas como la tienda de crochet artesanal preferida en Colombia, destacando por '
                'la calidad, la creatividad y el cuidado en cada una de nuestras piezas tejidas a mano.',
            )
        )
        conexion.commit()

    # Configuración por defecto (contacto y mapa) — independiente, igual que sobre_nosotros
    hay_configuracion = conexion.execute(
        "SELECT COUNT(*) AS total FROM configuracion"
    ).fetchone()['total']

    if hay_configuracion == 0:
        conexion.execute(
            "INSERT INTO configuracion (id, telefono, whatsapp, email, direccion, mapa_lat, mapa_lng, mapa_zoom) "
            "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
            (
                '+57 313 6912090',
                '573136912090',
                'Latiendadelcrochet.isa@gmail.com',
                'Villavicencio, Meta - Colombia',
                4.142000, -73.626000, 16
            )
        )
        conexion.commit()

    # Video de presentación por defecto — independiente, igual que sobre_nosotros
    hay_video = conexion.execute(
        "SELECT COUNT(*) AS total FROM video_presentacion"
    ).fetchone()['total']

    if hay_video == 0:
        conexion.execute(
            "INSERT INTO video_presentacion (id, titulo, descripcion, video_archivo, video_url) VALUES (1, ?, ?, NULL, NULL)",
            (
                'Conoce nuestro taller',
                'Un vistazo detrás de cámaras de cómo nace cada pieza tejida a mano, hilo por hilo y con mucho cariño.'
            )
        )
        conexion.commit()

    conexion.close()


inicializar_bd()


# ==========================================================
# Decoradores de autenticación
# ==========================================================

def login_required(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorada


def admin_required(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if session.get('usuario_rol') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorada


# Hace disponible la cantidad de artículos del carrito y la configuración
# general del sitio (contacto/mapa) en TODAS las plantillas
@app.context_processor
def inyectar_globales():
    carrito_sesion = session.get('carrito', {})
    cantidad_total = sum(carrito_sesion.values())

    conexion = conectar_bd()
    configuracion = conexion.execute("SELECT * FROM configuracion WHERE id = 1").fetchone()
    conexion.close()

    return dict(carrito_cantidad=cantidad_total, configuracion=configuracion)


def resolver_item_carrito(conexion, clave):
    """A partir de una clave del carrito ('id' o 'id-varianteId') devuelve el producto y,
    si aplica, la variante (medida + precio) elegida."""
    if '-' in clave:
        producto_id_str, variante_id_str = clave.split('-', 1)
    else:
        producto_id_str, variante_id_str = clave, None

    producto = conexion.execute("SELECT * FROM productos WHERE id = ?", (producto_id_str,)).fetchone()
    variante = None
    if producto and variante_id_str:
        variante = conexion.execute(
            "SELECT * FROM producto_variantes WHERE id = ? AND producto_id = ?",
            (variante_id_str, producto_id_str)
        ).fetchone()
    return producto, variante


# Columnas auxiliares reutilizadas en las consultas de listado de productos:
# "portada" = primera imagen de la galería, o la imagen clásica si no hay galería.
# "precio_min_variante" / "num_variantes" permiten mostrar "Desde $X" cuando hay variantes.
SQL_COLUMNAS_LISTADO_PRODUCTOS = '''
    COALESCE(
        (SELECT imagen FROM producto_imagenes WHERE producto_id = productos.id ORDER BY orden, id LIMIT 1),
        productos.imagen
    ) AS portada,
    (SELECT MIN(precio) FROM producto_variantes WHERE producto_id = productos.id) AS precio_min_variante,
    (SELECT COUNT(*) FROM producto_variantes WHERE producto_id = productos.id) AS num_variantes
'''


# ==========================================================
# Página de inicio
# ==========================================================

@app.route('/')
def inicio():
    conexion = conectar_bd()
    destacados = conexion.execute(f'''
        SELECT productos.*, {SQL_COLUMNAS_LISTADO_PRODUCTOS}
        FROM productos
        WHERE destacado = 1
        ORDER BY id DESC LIMIT 4
    ''').fetchall()
    video = conexion.execute("SELECT * FROM video_presentacion WHERE id = 1").fetchone()
    conexion.close()

    video_plataforma, video_embed_id = (None, None)
    if video and video['video_url'] and not video['video_archivo']:
        video_plataforma, video_embed_id = datos_embed_video(video['video_url'])

    return render_template(
        'inicio.html', destacados=destacados, video=video,
        video_plataforma=video_plataforma, video_embed_id=video_embed_id
    )


# ==========================================================
# Tienda / productos
# ==========================================================

@app.route('/tienda')
def tienda():
    categoria_id = request.args.get('categoria')
    conexion = conectar_bd()
    categorias = conexion.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()

    if categoria_id:
        productos = conexion.execute(f'''
            SELECT productos.*, {SQL_COLUMNAS_LISTADO_PRODUCTOS}
            FROM productos WHERE categoria_id = ? ORDER BY nombre
        ''', (categoria_id,)).fetchall()
    else:
        productos = conexion.execute(f'''
            SELECT productos.*, {SQL_COLUMNAS_LISTADO_PRODUCTOS}
            FROM productos ORDER BY nombre
        ''').fetchall()

    conexion.close()
    return render_template(
        'tienda.html', productos=productos, categorias=categorias,
        categoria_actual=categoria_id
    )


@app.route('/producto/<int:id>')
def producto_detalle(id):
    conexion = conectar_bd()
    producto = conexion.execute("SELECT * FROM productos WHERE id = ?", (id,)).fetchone()
    if producto is None:
        conexion.close()
        return "Producto no encontrado", 404

    imagenes = conexion.execute(
        "SELECT * FROM producto_imagenes WHERE producto_id = ? ORDER BY orden, id", (id,)
    ).fetchall()
    variantes = conexion.execute(
        "SELECT * FROM producto_variantes WHERE producto_id = ? ORDER BY precio", (id,)
    ).fetchall()
    conexion.close()
    return render_template('producto.html', producto=producto, imagenes=imagenes, variantes=variantes)


# ==========================================================
# Carrito de compras (se guarda en la sesión del navegador)
# ==========================================================

@app.route('/carrito')
def carrito():
    carrito_sesion = session.get('carrito', {})
    conexion = conectar_bd()
    items = []
    total = 0

    for clave, cantidad in carrito_sesion.items():
        producto, variante = resolver_item_carrito(conexion, clave)
        if producto:
            precio_unitario = variante['precio'] if variante else producto['precio']
            subtotal = precio_unitario * cantidad
            total += subtotal
            items.append({
                'clave': clave, 'producto': producto, 'variante': variante,
                'cantidad': cantidad, 'precio_unitario': precio_unitario, 'subtotal': subtotal
            })

    conexion.close()
    return render_template('carrito.html', items=items, total=total)


@app.route('/carrito/agregar/<int:id>', methods=['POST'])
def carrito_agregar(id):
    cantidad = int(request.form.get('cantidad', 1))
    variante_id = (request.form.get('variante_id') or '').strip()

    carrito_sesion = session.get('carrito', {})
    clave = f"{id}-{variante_id}" if variante_id else str(id)
    carrito_sesion[clave] = carrito_sesion.get(clave, 0) + cantidad
    session['carrito'] = carrito_sesion
    return redirect(url_for('carrito'))


@app.route('/carrito/actualizar/<clave>', methods=['POST'])
def carrito_actualizar(clave):
    cantidad = int(request.form.get('cantidad', 1))
    carrito_sesion = session.get('carrito', {})
    if clave in carrito_sesion:
        if cantidad <= 0:
            carrito_sesion.pop(clave)
        else:
            carrito_sesion[clave] = cantidad
    session['carrito'] = carrito_sesion
    return redirect(url_for('carrito'))


@app.route('/carrito/eliminar/<clave>')
def carrito_eliminar(clave):
    carrito_sesion = session.get('carrito', {})
    carrito_sesion.pop(clave, None)
    session['carrito'] = carrito_sesion
    return redirect(url_for('carrito'))


@app.route('/carrito/finalizar', methods=['POST'])
@login_required
def carrito_finalizar():
    carrito_sesion = session.get('carrito', {})
    if not carrito_sesion:
        return redirect(url_for('carrito'))

    conexion = conectar_bd()
    total = 0
    items_info = []

    for clave, cantidad in carrito_sesion.items():
        producto, variante = resolver_item_carrito(conexion, clave)
        if producto:
            precio_unitario = variante['precio'] if variante else producto['precio']
            subtotal = precio_unitario * cantidad
            total += subtotal
            items_info.append((producto, variante, cantidad, precio_unitario))

    hoy = datetime.now().isoformat()
    cursor = conexion.execute(
        "INSERT INTO pedidos (usuario_id, fecha, estado, total) VALUES (?, ?, ?, ?)",
        (session['usuario_id'], hoy, 'Pendiente', total)
    )
    pedido_id = cursor.lastrowid

    for producto, variante, cantidad, precio_unitario in items_info:
        nombre_producto = producto['nombre']
        if variante:
            nombre_producto = f"{nombre_producto} - {variante['medida']}"
        conexion.execute(
            "INSERT INTO pedido_items (pedido_id, producto_id, nombre_producto, cantidad, precio_unitario) "
            "VALUES (?, ?, ?, ?, ?)",
            (pedido_id, producto['id'], nombre_producto, cantidad, precio_unitario)
        )

    conexion.commit()
    conexion.close()

    session['carrito'] = {}
    return redirect(url_for('cliente_pedidos'))


# ==========================================================
# Sobre nosotros
# ==========================================================

@app.route('/sobre-nosotros')
def sobre_nosotros():
    conexion = conectar_bd()
    contenido = conexion.execute("SELECT * FROM sobre_nosotros WHERE id = 1").fetchone()
    conexion.close()
    return render_template('sobre_nosotros.html', contenido=contenido)


# ==========================================================
# Blog: la historia del emprendimiento, el proceso de cada producto
# (con video opcional) y las opiniones de quienes visitan la página
# ==========================================================

@app.route('/blog')
def blog():
    conexion = conectar_bd()
    posts = conexion.execute('''
        SELECT blog_posts.*,
            (SELECT COUNT(*) FROM blog_comentarios WHERE blog_comentarios.post_id = blog_posts.id) AS total_comentarios
        FROM blog_posts ORDER BY fecha DESC
    ''').fetchall()
    conexion.close()
    return render_template('blog.html', posts=posts)


@app.route('/blog/<int:id>', methods=['GET', 'POST'])
def blog_post(id):
    conexion = conectar_bd()

    if request.method == 'POST':
        comentario = (request.form.get('comentario') or '').strip()
        es_admin = session.get('usuario_rol') == 'admin'
        nombre = 'La Tienda del Crochet' if es_admin else (request.form.get('nombre') or '').strip()

        if nombre and comentario:
            hoy = datetime.now().isoformat()
            conexion.execute(
                "INSERT INTO blog_comentarios (post_id, nombre, comentario, es_admin, fecha) VALUES (?, ?, ?, ?, ?)",
                (id, nombre, comentario, 1 if es_admin else 0, hoy)
            )
            conexion.commit()

    post = conexion.execute("SELECT * FROM blog_posts WHERE id = ?", (id,)).fetchone()
    if post is None:
        conexion.close()
        return "Publicación no encontrada", 404

    comentarios = conexion.execute(
        "SELECT * FROM blog_comentarios WHERE post_id = ? ORDER BY fecha DESC", (id,)
    ).fetchall()
    conexion.close()

    video_plataforma, video_embed_id = (None, None)
    if post['video_url'] and not post['video_archivo']:
        video_plataforma, video_embed_id = datos_embed_video(post['video_url'])

    return render_template(
        'blog_post.html', post=post, comentarios=comentarios,
        video_plataforma=video_plataforma, video_embed_id=video_embed_id
    )


# ==========================================================
# Encuesta de clientes
# ==========================================================

@app.route('/encuesta', methods=['GET', 'POST'])
def encuesta():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        email = request.form.get('email', '').strip()
        calificacion = int(request.form['calificacion'])
        comentario = request.form.get('comentario', '').strip()
        hoy = datetime.now().isoformat()

        conexion = conectar_bd()
        conexion.execute(
            "INSERT INTO encuestas_respuestas (nombre, email, calificacion, comentario, fecha) VALUES (?, ?, ?, ?, ?)",
            (nombre, email, calificacion, comentario, hoy)
        )
        conexion.commit()
        conexion.close()
        return render_template('encuesta.html', enviado=True)

    return render_template('encuesta.html', enviado=False)


# ==========================================================
# Registro de proveedores / aliados comerciales
# ==========================================================

@app.route('/proveedores', methods=['GET', 'POST'])
def proveedores():
    if request.method == 'POST':
        empresa = request.form['empresa']
        contacto_nombre = request.form['contacto_nombre']
        telefono = request.form['telefono']
        email = request.form['email']
        productos_servicios = request.form['productos_servicios']
        hoy = datetime.now().isoformat()

        conexion = conectar_bd()
        conexion.execute(
            "INSERT INTO proveedores (empresa, contacto_nombre, telefono, email, productos_servicios, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (empresa, contacto_nombre, telefono, email, productos_servicios, hoy)
        )
        conexion.commit()
        conexion.close()
        return render_template('proveedores.html', enviado=True)

    return render_template('proveedores.html', enviado=False)


# ==========================================================
# Contacto
# ==========================================================

@app.route('/contacto', methods=['GET', 'POST'])
def contacto():
    if request.method == 'POST':
        nombre = request.form['nombre']
        email = request.form['email']
        mensaje = request.form['mensaje']
        hoy = datetime.now().isoformat()

        conexion = conectar_bd()
        conexion.execute(
            "INSERT INTO mensajes (nombre, email, mensaje, fecha) VALUES (?, ?, ?, ?)",
            (nombre, email, mensaje, hoy)
        )
        conexion.commit()
        conexion.close()
        return render_template('contacto.html', enviado=True)

    return render_template('contacto.html', enviado=False)


# ==========================================================
# Autenticación (login / registro / logout)
# ==========================================================

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        email = request.form['email']
        password = request.form['password']

        conexion = conectar_bd()
        existente = conexion.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
        if existente:
            conexion.close()
            return render_template('registro.html', error='Ese correo ya está registrado.')

        password_hash = generate_password_hash(password)
        hoy = datetime.now().isoformat()
        conexion.execute(
            "INSERT INTO usuarios (nombre, email, password_hash, rol, fecha_registro) VALUES (?, ?, ?, 'cliente', ?)",
            (nombre, email, password_hash, hoy)
        )
        conexion.commit()
        conexion.close()
        return redirect(url_for('login'))

    return render_template('registro.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conexion = conectar_bd()
        usuario = conexion.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        conexion.close()

        if usuario and check_password_hash(usuario['password_hash'], password):
            session['usuario_id'] = usuario['id']
            session['usuario_nombre'] = usuario['nombre']
            session['usuario_rol'] = usuario['rol']
            if usuario['rol'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('inicio'))

        return render_template('login.html', error='Correo o contraseña incorrectos.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('inicio'))


# ==========================================================
# Zona de cliente
# ==========================================================

@app.route('/cliente/pedidos')
@login_required
def cliente_pedidos():
    conexion = conectar_bd()
    pedidos = conexion.execute('''
        SELECT pedidos.*,
            (SELECT GROUP_CONCAT(nombre_producto || ' ×' || cantidad, ', ')
             FROM pedido_items WHERE pedido_items.pedido_id = pedidos.id) AS productos_resumen
        FROM pedidos WHERE usuario_id = ? ORDER BY fecha DESC
    ''', (session['usuario_id'],)).fetchall()
    conexion.close()
    return render_template('cliente/pedidos.html', pedidos=pedidos)


@app.route('/cliente/perfil', methods=['GET', 'POST'])
@login_required
def cliente_perfil():
    conexion = conectar_bd()

    if request.method == 'POST':
        nombre = request.form['nombre']
        telefono = request.form['telefono']
        direccion = request.form['direccion']
        conexion.execute(
            "UPDATE usuarios SET nombre=?, telefono=?, direccion=? WHERE id=?",
            (nombre, telefono, direccion, session['usuario_id'])
        )
        conexion.commit()
        session['usuario_nombre'] = nombre

    usuario = conexion.execute("SELECT * FROM usuarios WHERE id = ?", (session['usuario_id'],)).fetchone()
    conexion.close()
    return render_template('cliente/perfil.html', usuario=usuario)


# ==========================================================
# Panel de administrador
# ==========================================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    conexion = conectar_bd()
    total_productos = conexion.execute("SELECT COUNT(*) AS total FROM productos").fetchone()['total']
    total_pedidos = conexion.execute("SELECT COUNT(*) AS total FROM pedidos").fetchone()['total']
    total_clientes = conexion.execute("SELECT COUNT(*) AS total FROM usuarios WHERE rol='cliente'").fetchone()['total']
    mensajes_sin_leer = conexion.execute("SELECT COUNT(*) AS total FROM mensajes WHERE leido = 0").fetchone()['total']
    total_encuestas = conexion.execute("SELECT COUNT(*) AS total FROM encuestas_respuestas").fetchone()['total']
    total_proveedores = conexion.execute("SELECT COUNT(*) AS total FROM proveedores").fetchone()['total']
    conexion.close()
    return render_template(
        'admin/dashboard.html', total_productos=total_productos, total_pedidos=total_pedidos,
        total_clientes=total_clientes, mensajes_sin_leer=mensajes_sin_leer,
        total_encuestas=total_encuestas, total_proveedores=total_proveedores
    )


@app.route('/admin/productos')
@admin_required
def admin_productos():
    conexion = conectar_bd()
    productos = conexion.execute(f'''
        SELECT productos.*, categorias.nombre AS categoria_nombre, {SQL_COLUMNAS_LISTADO_PRODUCTOS}
        FROM productos
        JOIN categorias ON productos.categoria_id = categorias.id
        ORDER BY productos.id DESC
    ''').fetchall()
    conexion.close()
    return render_template('admin/productos.html', productos=productos)


@app.route('/admin/productos/nuevo')
@admin_required
def admin_productos_nuevo():
    conexion = conectar_bd()
    categorias = conexion.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()
    conexion.close()
    return render_template('admin/producto_form.html', categorias=categorias, producto=None, imagenes=[], variantes=[])


@app.route('/admin/productos/editar/<int:id>')
@admin_required
def admin_productos_editar(id):
    conexion = conectar_bd()
    producto = conexion.execute("SELECT * FROM productos WHERE id = ?", (id,)).fetchone()
    categorias = conexion.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()
    imagenes = conexion.execute(
        "SELECT * FROM producto_imagenes WHERE producto_id = ? ORDER BY orden, id", (id,)
    ).fetchall()
    variantes = conexion.execute(
        "SELECT * FROM producto_variantes WHERE producto_id = ? ORDER BY id", (id,)
    ).fetchall()
    conexion.close()
    return render_template(
        'admin/producto_form.html', producto=producto, categorias=categorias,
        imagenes=imagenes, variantes=variantes
    )


@app.route('/admin/productos/guardar', methods=['POST'])
@admin_required
def admin_productos_guardar():
    id = request.form.get('id')
    nombre = request.form['nombre']
    descripcion = request.form['descripcion']
    precio = float(request.form['precio'])
    stock = int(request.form['stock'])
    categoria_id = int(request.form['categoria_id'])
    destacado = 1 if request.form.get('destacado') == 'on' else 0

    conexion = conectar_bd()

    if id:
        producto_id = int(id)
        conexion.execute(
            "UPDATE productos SET nombre=?, descripcion=?, precio=?, stock=?, categoria_id=?, destacado=? WHERE id=?",
            (nombre, descripcion, precio, stock, categoria_id, destacado, producto_id)
        )
    else:
        hoy = datetime.now().isoformat()
        cursor = conexion.execute(
            "INSERT INTO productos (nombre, descripcion, precio, stock, categoria_id, destacado, fecha_registro, imagen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (nombre, descripcion, precio, stock, categoria_id, destacado, hoy)
        )
        producto_id = cursor.lastrowid

    # --- Galería de imágenes: eliminar las marcadas y agregar las nuevas subidas ---
    for imagen_id in request.form.getlist('eliminar_imagen'):
        conexion.execute(
            "DELETE FROM producto_imagenes WHERE id = ? AND producto_id = ?", (int(imagen_id), producto_id)
        )

    fila_orden = conexion.execute(
        "SELECT COALESCE(MAX(orden), -1) AS maximo FROM producto_imagenes WHERE producto_id = ?", (producto_id,)
    ).fetchone()
    siguiente_orden = fila_orden['maximo'] + 1

    for archivo in request.files.getlist('imagenes'):
        nombre_imagen = guardar_imagen_producto(archivo)
        if nombre_imagen:
            conexion.execute(
                "INSERT INTO producto_imagenes (producto_id, imagen, orden) VALUES (?, ?, ?)",
                (producto_id, nombre_imagen, siguiente_orden)
            )
            siguiente_orden += 1
            # Compatibilidad: si el producto todavía no tenía imagen "clásica", usamos la primera subida
            conexion.execute(
                "UPDATE productos SET imagen = COALESCE(imagen, ?) WHERE id = ?", (nombre_imagen, producto_id)
            )

    # --- Variantes de medida/precio: se reemplazan por completo con lo enviado en el formulario ---
    conexion.execute("DELETE FROM producto_variantes WHERE producto_id = ?", (producto_id,))
    medidas = request.form.getlist('variante_medida')
    precios_variante = request.form.getlist('variante_precio')
    stocks_variante = request.form.getlist('variante_stock')

    for medida, precio_v, stock_v in zip(medidas, precios_variante, stocks_variante):
        medida = medida.strip()
        if medida and precio_v.strip():
            conexion.execute(
                "INSERT INTO producto_variantes (producto_id, medida, precio, stock) VALUES (?, ?, ?, ?)",
                (producto_id, medida, float(precio_v), int(stock_v) if stock_v.strip() else 0)
            )

    conexion.commit()
    conexion.close()
    return redirect(url_for('admin_productos'))


@app.route('/admin/productos/eliminar/<int:id>')
@admin_required
def admin_productos_eliminar(id):
    conexion = conectar_bd()
    conexion.execute("DELETE FROM producto_imagenes WHERE producto_id = ?", (id,))
    conexion.execute("DELETE FROM producto_variantes WHERE producto_id = ?", (id,))
    conexion.execute("DELETE FROM productos WHERE id = ?", (id,))
    conexion.commit()
    conexion.close()
    return redirect(url_for('admin_productos'))


@app.route('/admin/pedidos')
@admin_required
def admin_pedidos():
    conexion = conectar_bd()
    pedidos = conexion.execute('''
        SELECT pedidos.*, usuarios.nombre AS cliente_nombre, usuarios.email AS cliente_email,
            (SELECT GROUP_CONCAT(nombre_producto || ' ×' || cantidad, ', ')
             FROM pedido_items WHERE pedido_items.pedido_id = pedidos.id) AS productos_resumen
        FROM pedidos
        JOIN usuarios ON pedidos.usuario_id = usuarios.id
        ORDER BY pedidos.fecha DESC
    ''').fetchall()
    conexion.close()
    return render_template('admin/pedidos.html', pedidos=pedidos)


@app.route('/admin/pedidos/<int:id>/estado', methods=['POST'])
@admin_required
def admin_pedidos_estado(id):
    estado = request.form['estado']
    conexion = conectar_bd()
    conexion.execute("UPDATE pedidos SET estado = ? WHERE id = ?", (estado, id))
    conexion.commit()
    conexion.close()
    return redirect(url_for('admin_pedidos'))


@app.route('/admin/sobre-nosotros', methods=['GET', 'POST'])
@admin_required
def admin_sobre_nosotros():
    conexion = conectar_bd()

    if request.method == 'POST':
        historia_titulo = request.form['historia_titulo']
        historia = request.form['historia']
        mision = request.form['mision']
        vision = request.form['vision']

        archivo_imagen = request.files.get('historia_imagen')
        nombre_imagen = guardar_imagen_producto(archivo_imagen)

        if nombre_imagen:
            conexion.execute(
                "UPDATE sobre_nosotros SET historia_titulo=?, historia=?, mision=?, vision=?, historia_imagen=? WHERE id = 1",
                (historia_titulo, historia, mision, vision, nombre_imagen)
            )
        else:
            conexion.execute(
                "UPDATE sobre_nosotros SET historia_titulo=?, historia=?, mision=?, vision=? WHERE id = 1",
                (historia_titulo, historia, mision, vision)
            )

        if request.form.get('eliminar_imagen') == '1':
            conexion.execute("UPDATE sobre_nosotros SET historia_imagen = NULL WHERE id = 1")

        conexion.commit()

    contenido = conexion.execute("SELECT * FROM sobre_nosotros WHERE id = 1").fetchone()
    conexion.close()
    return render_template('admin/sobre_nosotros.html', contenido=contenido)


@app.route('/admin/video', methods=['GET', 'POST'])
@admin_required
def admin_video():
    conexion = conectar_bd()

    if request.method == 'POST':
        titulo = request.form['titulo']
        descripcion = request.form['descripcion']
        video_url = (request.form.get('video_url') or '').strip()

        nombre_video = guardar_video(request.files.get('video_archivo'))

        if nombre_video:
            conexion.execute(
                "UPDATE video_presentacion SET titulo=?, descripcion=?, video_archivo=?, video_url=? WHERE id = 1",
                (titulo, descripcion, nombre_video, video_url)
            )
        else:
            conexion.execute(
                "UPDATE video_presentacion SET titulo=?, descripcion=?, video_url=? WHERE id = 1",
                (titulo, descripcion, video_url)
            )

        if request.form.get('eliminar_video') == '1':
            conexion.execute("UPDATE video_presentacion SET video_archivo = NULL WHERE id = 1")

        conexion.commit()

    video = conexion.execute("SELECT * FROM video_presentacion WHERE id = 1").fetchone()
    conexion.close()
    return render_template('admin/video.html', video=video)


@app.route('/admin/blog')
@admin_required
def admin_blog():
    conexion = conectar_bd()
    posts = conexion.execute('''
        SELECT blog_posts.*,
            (SELECT COUNT(*) FROM blog_comentarios WHERE blog_comentarios.post_id = blog_posts.id) AS total_comentarios
        FROM blog_posts ORDER BY fecha DESC
    ''').fetchall()
    conexion.close()
    return render_template('admin/blog.html', posts=posts)


@app.route('/admin/blog/nuevo')
@admin_required
def admin_blog_nuevo():
    return render_template('admin/blog_form.html', post=None, comentarios=[])


@app.route('/admin/blog/editar/<int:id>')
@admin_required
def admin_blog_editar(id):
    conexion = conectar_bd()
    post = conexion.execute("SELECT * FROM blog_posts WHERE id = ?", (id,)).fetchone()
    comentarios = conexion.execute(
        "SELECT * FROM blog_comentarios WHERE post_id = ? ORDER BY fecha DESC", (id,)
    ).fetchall()
    conexion.close()
    return render_template('admin/blog_form.html', post=post, comentarios=comentarios)


@app.route('/admin/blog/guardar', methods=['POST'])
@admin_required
def admin_blog_guardar():
    id = request.form.get('id')
    titulo = request.form['titulo']
    resumen = request.form['resumen']
    contenido = request.form['contenido']
    video_url = (request.form.get('video_url') or '').strip()

    nombre_imagen = guardar_imagen_producto(request.files.get('imagen'))
    nombre_video = guardar_video(request.files.get('video_archivo'))

    conexion = conectar_bd()

    if id:
        post_id = int(id)
        conexion.execute(
            "UPDATE blog_posts SET titulo=?, resumen=?, contenido=?, video_url=? WHERE id=?",
            (titulo, resumen, contenido, video_url, post_id)
        )
        if nombre_imagen:
            conexion.execute("UPDATE blog_posts SET imagen=? WHERE id=?", (nombre_imagen, post_id))
        if nombre_video:
            conexion.execute("UPDATE blog_posts SET video_archivo=? WHERE id=?", (nombre_video, post_id))
        if request.form.get('eliminar_imagen') == '1':
            conexion.execute("UPDATE blog_posts SET imagen=NULL WHERE id=?", (post_id,))
        if request.form.get('eliminar_video') == '1':
            conexion.execute("UPDATE blog_posts SET video_archivo=NULL WHERE id=?", (post_id,))
    else:
        hoy = datetime.now().isoformat()
        autor = session.get('usuario_nombre', 'La Tienda del Crochet')
        cursor = conexion.execute(
            "INSERT INTO blog_posts (titulo, resumen, contenido, autor, fecha, video_url, imagen, video_archivo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (titulo, resumen, contenido, autor, hoy, video_url, nombre_imagen, nombre_video)
        )
        post_id = cursor.lastrowid

    conexion.commit()
    conexion.close()
    return redirect(url_for('admin_blog'))


@app.route('/admin/blog/eliminar/<int:id>')
@admin_required
def admin_blog_eliminar(id):
    conexion = conectar_bd()
    conexion.execute("DELETE FROM blog_comentarios WHERE post_id = ?", (id,))
    conexion.execute("DELETE FROM blog_posts WHERE id = ?", (id,))
    conexion.commit()
    conexion.close()
    return redirect(url_for('admin_blog'))


@app.route('/admin/blog/comentario/eliminar/<int:id>')
@admin_required
def admin_blog_comentario_eliminar(id):
    conexion = conectar_bd()
    fila = conexion.execute("SELECT post_id FROM blog_comentarios WHERE id = ?", (id,)).fetchone()
    conexion.execute("DELETE FROM blog_comentarios WHERE id = ?", (id,))
    conexion.commit()
    conexion.close()
    if fila:
        return redirect(url_for('admin_blog_editar', id=fila['post_id']))
    return redirect(url_for('admin_blog'))


@app.route('/admin/encuestas')
@admin_required
def admin_encuestas():
    conexion = conectar_bd()
    respuestas = conexion.execute("SELECT * FROM encuestas_respuestas ORDER BY fecha DESC").fetchall()
    promedio = conexion.execute("SELECT AVG(calificacion) AS promedio FROM encuestas_respuestas").fetchone()['promedio']
    conexion.close()
    return render_template('admin/encuestas.html', respuestas=respuestas, promedio=promedio)


@app.route('/admin/proveedores')
@admin_required
def admin_proveedores():
    conexion = conectar_bd()
    registros = conexion.execute("SELECT * FROM proveedores ORDER BY fecha DESC").fetchall()
    conexion.close()
    return render_template('admin/proveedores.html', registros=registros)


@app.route('/admin/configuracion', methods=['GET', 'POST'])
@admin_required
def admin_configuracion():
    conexion = conectar_bd()

    if request.method == 'POST':
        telefono = request.form['telefono']
        whatsapp = request.form['whatsapp']
        email = request.form['email']
        direccion = request.form['direccion']
        mapa_lat = float(request.form['mapa_lat'])
        mapa_lng = float(request.form['mapa_lng'])
        mapa_zoom = int(request.form['mapa_zoom'])

        conexion.execute(
            "UPDATE configuracion SET telefono=?, whatsapp=?, email=?, direccion=?, mapa_lat=?, mapa_lng=?, mapa_zoom=? WHERE id = 1",
            (telefono, whatsapp, email, direccion, mapa_lat, mapa_lng, mapa_zoom)
        )
        conexion.commit()

    configuracion = conexion.execute("SELECT * FROM configuracion WHERE id = 1").fetchone()
    conexion.close()
    return render_template('admin/configuracion.html', configuracion=configuracion)


@app.route('/admin/mensajes')
@admin_required
def admin_mensajes():
    conexion = conectar_bd()
    mensajes = conexion.execute("SELECT * FROM mensajes ORDER BY fecha DESC").fetchall()
    conexion.execute("UPDATE mensajes SET leido = 1")
    conexion.commit()
    conexion.close()
    return render_template('admin/mensajes.html', mensajes=mensajes)


if __name__ == '__main__':
    app.run(debug=True)
