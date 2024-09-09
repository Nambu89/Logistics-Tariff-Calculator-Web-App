from flask import Flask, jsonify, render_template, request, session
import pandas as pd
import numpy as np
import os
from werkzeug.utils import secure_filename
import logging
import json
import unittest
from collections import defaultdict
import csv
from datetime import datetime

# Configuración básica del logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# TODO: Cambiar esto por una clave secreta generada de forma segura en producción
app.secret_key = 'supersecretkey'  # Necesario para manejar la sesión de usuario

# Cargar los archivos Excel
file_path_cbl = 'Tarifas_CBL.xlsx'
file_path_ontime = 'Tarifas_ONTIME.xlsx'
file_path_mrw = 'Tarifas_MRW.xlsx'
file_path_productos = 'Productos.xlsx'

# Carga de datos
df_cbl = pd.read_excel(file_path_cbl)
df_ontime = pd.read_excel(file_path_ontime)
df_mrw = pd.read_excel(file_path_mrw)
df_productos = pd.read_excel(file_path_productos)

# Convertir las comas en puntos para manejar correctamente los decimales en las columnas numéricas
df_productos['PESO BRUTO (kg)'] = df_productos['PESO BRUTO (kg)'].astype(str).str.replace(',', '.').astype(float)
df_productos['VOLUMEN (m3)'] = df_productos['VOLUMEN (m3)'].astype(str).str.replace(',', '.').astype(float)

# Normalizar los nombres de las columnas para evitar problemas de formato
df_cbl.columns = df_cbl.columns.str.strip().str.upper()
df_mrw.columns = df_mrw.columns.str.strip().str.upper()
df_ontime.columns = df_ontime.columns.str.strip().str.upper()

# Asegurarse de que las columnas numéricas son realmente numéricas
df_mrw['KG'] = pd.to_numeric(df_mrw['KG'], errors='coerce')
df_mrw = df_mrw.dropna(subset=['KG'])

df_cbl['KG'] = pd.to_numeric(df_cbl['KG'], errors='coerce')
df_cbl = df_cbl.dropna(subset=['KG'])

# Configuración para la carga de archivos
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Constantes
PALET_ANCHO = 0.8  # metros
PALET_FONDO = 1.2  # metros
PALET_ALTO_BASE = 0.15  # metros
MAX_ALTO_PALET = 2.16  # metros
MAX_PESO_XS = 40  # kg
MAX_PESO_PALET = 400  # kg

# Recargos
RECARGO_COMBUSTIBLE_CBL = 0.035
RECARGO_DEVOLUCION_CBL = 0.20
RECARGO_COMBUSTIBLE_ONTIME = 0.04
RECARGO_SEGURO_ONTIME = 0.04

# Definir el mapeo de columnas
column_mapping = {
    'ALTO EMBALAJE (MM)': ['ALTO EMBALAJE (MM)', 'ALTO EMBALAJE(MM)', 'ALTO'],
    'ANCHO EMBALAJE (MM)': ['ANCHO EMBALAJE (MM)', 'ANCHO EMBALAJE (MM)', 'ANCHO'],
    'FONDO EMBALAJE (MM)': ['FONDO EMBALAJE (MM)', 'FONDO EMBALAJE(MM)', 'FONDO']
}

class Producto:
    """
    Representa un producto con sus características físicas y de envío.
    
    """
    def __init__(self, sku, categorias, alto, ancho, fondo, volumen, peso, cantidad, apilable = True, max_apilado = 2):
        self.sku = sku
        self.categorias = categorias
        self.alto = alto / 1000  # Convertir de mm a m
        self.ancho = ancho / 1000
        self.fondo = fondo / 1000
        self.volumen = volumen
        self.peso = peso
        self.cantidad = cantidad
        self.peso_total = peso * cantidad
        self.volumen_total = volumen * cantidad
        self.apilable = apilable
        self.max_apilado = max_apilado

class Palet:
    def __init__(self, ancho=PALET_ANCHO, fondo=PALET_FONDO, alto_max=MAX_ALTO_PALET, peso_max=MAX_PESO_PALET):
        self.ancho = ancho
        self.fondo = fondo
        self.alto_max = alto_max
        self.peso_max = peso_max
        self.productos = []
        self.peso_actual = 0
        self.volumen_actual = 0
        self.altura_actual = PALET_ALTO_BASE
        self.espacio_disponible = [[0, 0, ancho, fondo]]  # [x, y, ancho, fondo]

    def puede_agregar(self, producto):
        if self.peso_actual + producto.peso > self.peso_max:
            return False
        
        altura_necesaria = producto.alto
        if any(p.sku == producto.sku for p in self.productos):
            altura_necesaria /= producto.max_apilado
        
        if self.altura_actual + altura_necesaria > self.alto_max:
            return False
        
        for espacio in self.espacio_disponible:
            if producto.ancho <= espacio[2] and producto.fondo <= espacio[3]:
                return True
        return False

    def agregar_producto(self, producto):
        if not self.puede_agregar(producto):
            return False

        for i, espacio in enumerate(self.espacio_disponible):
            if producto.ancho <= espacio[2] and producto.fondo <= espacio[3]:
                x, y = espacio[0], espacio[1]
                self.productos.append(producto)
                self.peso_actual += producto.peso
                self.volumen_actual += producto.volumen
                self.altura_actual = max(self.altura_actual, self.altura_actual + producto.alto)

                # Actualizar espacios disponibles
                nuevo_espacio_derecha = [x + producto.ancho, y, espacio[2] - producto.ancho, espacio[3]]
                nuevo_espacio_arriba = [x, y + producto.fondo, producto.ancho, espacio[3] - producto.fondo]
                
                self.espacio_disponible[i] = [x, y, producto.ancho, producto.fondo]
                if nuevo_espacio_derecha[2] > 0:
                    self.espacio_disponible.append(nuevo_espacio_derecha)
                if nuevo_espacio_arriba[3] > 0:
                    self.espacio_disponible.append(nuevo_espacio_arriba)
                
                self.espacio_disponible.sort(key=lambda e: e[0] * e[1])
                return True
        return False
    
# Este método empaqueta los productos en palets según las restricciones de peso, volumen y apilamiento.

def empaquetar_productos(productos):
    productos_ordenados = sorted(productos, key=lambda p: p.volumen_total, reverse=True)
    palets = []  # Lista para almacenar los palets creados
    productos_xs = []  # Lista para almacenar productos XS (pequeños)
    productos_especiales = []  # Lista para productos que no caben en un palet estándar

    for producto in productos_ordenados:
        # Registrar información del producto en el log
        logger.debug(f'Evaluando producto: SKU = {producto.sku}, peso total = {producto.peso_total}, volumen total = {producto.volumen_total}')
        logger.debug(f'Dimensiones: Alto = {producto.alto}m, Ancho = {producto.ancho}m, Fondo = {producto.fondo}m')

        # Verificar si el producto excede las dimensiones del palet
        if producto.ancho > PALET_ANCHO or producto.fondo > PALET_FONDO or producto.alto > (MAX_ALTO_PALET - PALET_ALTO_BASE):
            productos_especiales.append(producto)  # Agregar producto a la lista de productos especiales
            logger.debug(f'Producto especial agregado: {producto.sku}')
        
        # Verificar si el producto puede clasificarse como XS (por debajo de ciertos límites de peso y volumen)
        elif producto.peso_total <= MAX_PESO_XS and producto.volumen_total <= 0.25:
            productos_xs.append(producto)  # Agregar a la lista de productos XS
            logger.debug(f'Producto XS agregado: {producto.sku}')
        
        else:
            # Calcular cuántas unidades caben en un palet según el peso, las dimensiones y la altura máxima de apilado
            max_unidades_ancho = int(PALET_ANCHO // producto.ancho)  # Unidades posibles por ancho
            max_unidades_fondo = int(PALET_FONDO // producto.fondo)  # Unidades posibles por fondo
            max_unidades_alto = int((MAX_ALTO_PALET - PALET_ALTO_BASE) // producto.alto)  # Unidades apiladas en altura

            # Restricción de apilamiento (si el producto es apilable)
            if producto.apilable:
                max_unidades_alto = min(max_unidades_alto, producto.max_apilado)

            # Calcular el número máximo de unidades permitidas en el palet basándose en las tres dimensiones
            max_unidades_dimensiones = max_unidades_ancho * max_unidades_fondo * max_unidades_alto

            # Restringir también por el peso máximo del palet
            max_unidades_peso = int(MAX_PESO_PALET // producto.peso)

            # Determinar cuántas unidades del producto pueden caber por palet
            unidades_por_palet = min(producto.cantidad, max_unidades_dimensiones, max_unidades_peso)
            
            # Mientras queden unidades del producto por empaquetar
            while producto.cantidad > 0:
                nuevo_palet = Palet()  # Crear un nuevo palet
                unidades_este_palet = min(unidades_por_palet, producto.cantidad)  # Determinar cuántas unidades irán en este palet

                # Crear un nuevo objeto Producto ajustando el peso y volumen según las unidades en el palet
                nuevo_producto = Producto(
                    producto.sku,
                    producto.categorias,
                    producto.alto * 1000,  # Convertir de metros a milímetros
                    producto.ancho * 1000,
                    producto.fondo * 1000,
                    producto.volumen * unidades_este_palet,  # Volumen ajustado para las unidades en el palet
                    producto.peso * unidades_este_palet,  # Peso ajustado para las unidades en el palet
                    unidades_este_palet,  # Cantidad de unidades en este palet
                    producto.apilable,
                    producto.max_apilado
                )

                # Agregar el producto al palet
                nuevo_palet.agregar_producto(nuevo_producto)
                palets.append(nuevo_palet)  # Agregar el palet a la lista de palets
                producto.cantidad -= unidades_este_palet  # Reducir la cantidad de productos restantes a empaquetar
                logger.debug(f'Nuevo palet creado para {unidades_este_palet} unidades de {producto.sku}')

    # Al final, registrar cuántos palets se crearon y cuántos productos XS y especiales hay
    logger.debug(f"Palets creados: {len(palets)}, Productos XS: {len(productos_xs)}, Productos especiales: {len(productos_especiales)}")
    
    # Devolver la lista de palets creados, productos XS y productos especiales
    return palets, productos_xs, productos_especiales


# Obtener provincias
provincias_cbl = set(df_cbl.columns[2:])
provincias_ontime = set(df_ontime['PROVINCIA DESTINO'].unique())
provincias_mrw = set(df_mrw.columns[1:])

provincias_comunes = list(provincias_cbl.intersection(provincias_ontime, provincias_mrw))
provincias_comunes.sort()

# Obtener categorías y SKUs para los desplegables
categorias = df_productos['CATEGORIAS'].unique().tolist()
skus = df_productos['SKU'].unique().tolist()

def obtener_tarifa_ontime(df, zona, peso):
    """
    Obtiene la tarifa de ONTIME para un peso y zona específicos.
    """
    try:
        tarifas_ontime = [int(col) for col in df.columns if col.isdigit()]
        closest_weight_col = min((x for x in tarifas_ontime if x >= float(peso)), default=None)

        if closest_weight_col is not None:
            tarifa_ontime_row = df[df['PROVINCIA DESTINO'] == zona]
            if not tarifa_ontime_row.empty:
                return tarifa_ontime_row.iloc[0][str(closest_weight_col)]

        return np.nan
    except ValueError as e:
        logger.error(f"Error en obtener_tarifa_ontime: {e}. Peso: {peso}, Zona: {zona}")
        return np.nan
    except Exception as e:
        logger.error(f"Error inesperado en obtener_tarifa_ontime: {e}")
        return np.nan

def obtener_tarifa_ontime_xs(df, zona, peso, modalidad):
    """
    Obtiene la tarifa de ONTIME XS para un peso, zona y modalidad específicos.
    """
    try:
        tarifas_ontime = [col for col in df.columns if modalidad in col]
        closest_weight_col = None

        for col in tarifas_ontime:
            weight_limit = int(col.split()[0])
            if weight_limit >= peso:
                closest_weight_col = col
                break

        if closest_weight_col is not None:
            tarifa_ontime_row = df[df['PROVINCIA DESTINO'] == zona]
            if not tarifa_ontime_row.empty:
                return tarifa_ontime_row.iloc[0][closest_weight_col]

        return np.nan

    except Exception as e:
        logger.error(f"Error en obtener_tarifa_ontime_xs: {e}")
        return np.nan

def obtener_tarifa_mrw(df, zona, peso_total, num_bultos):
    """
    Obtiene la tarifa de MRW para un peso total, zona y número de bultos específicos.
    """
    try:
        peso_total = float(peso_total)
        filtered_df = df[df['KG'] >= peso_total]
        if filtered_df.empty:
            return np.nan
        closest_weight_row = filtered_df.iloc[0]
        tarifa_base = closest_weight_row[zona] if zona in df.columns else np.nan
        recargo_bultos = max(0, num_bultos - 2) * 2
        tarifa_total = tarifa_base + recargo_bultos
        return tarifa_total
    except ValueError as e:
        logger.error(f"Error en obtener_tarifa_mrw: {e}. Peso total: {peso_total}, Zona: {zona}, Num bultos: {num_bultos}")
        return np.nan
    except Exception as e:
        logger.error(f"Error inesperado en obtener_tarifa_mrw: {e}")
        return np.nan

def obtener_tarifa_cbl(df, zona, peso):
    """
    Obtiene la tarifa de CBL para un peso y zona específicos.
    """
    try:
        peso = float(peso)
        filtered_df = df[df['KG'] >= peso]
        if filtered_df.empty:
            return np.nan

        zona = zona.strip().upper()

        if zona not in df.columns:
            logger.error(f"Columna '{zona}' no encontrada en las tarifas CBL.")
            return np.nan

        closest_weight_row = filtered_df.iloc[0]
        return closest_weight_row[zona]
    except ValueError as e:
        logger.error(f"Error en obtener_tarifa_cbl: {e}. Peso: {peso}, Zona: {zona}")
        return np.nan
    except Exception as e:
        logger.error(f"Error inesperado al obtener tarifa CBL: {str(e)}")
        return np.nan

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Maneja la ruta principal de la aplicación.
    """
    if request.method == 'POST':
        if 'file' in request.files:
            return procesar_pedidos_route()
        elif 'calcular_devolucion' in request.form:
            return calcular_devolucion()
    return render_template('index.html', provincias=provincias_comunes)

def allowed_file(filename):
    """
    Verifica si el archivo tiene una extensión permitida.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'xls', 'xlsx'}

def serialize_numpy(obj):
    """
    Serializa objetos numpy y pandas para JSON.
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj) if not np.isnan(obj) else None
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    elif isinstance(obj, pd.Series):
        return obj.to_dict()
    elif pd.isna(obj):
        return None
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')

@app.route('/procesar_pedido', methods=['POST'])
def procesar_pedidos_route():
    """
    Procesa el pedido subido por el usuario.
    """
    if 'file' not in request.files or 'provincia' not in request.form:
        return jsonify({'error': 'No se ha subido un archivo o no se ha seleccionado una provincia'}), 400
    
    file = request.files['file']
    provincia = request.form['provincia']
    
    if file.filename == '' or provincia == '':
        return jsonify({'error': 'No se ha seleccionado un archivo o una provincia'}), 400
    
    if provincia not in provincias_comunes:
        return jsonify({'error': 'La provincia seleccionada no es válida'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            df_pedido = pd.read_excel(filepath, engine='openpyxl')
            
            if df_pedido.shape[1] < 2:
                return jsonify({'error': 'El archivo debe tener al menos 2 columnas'}), 400

            df_pedido.columns = df_pedido.columns.str.strip().str.lower()
            if 'nº' in df_pedido.columns:
                df_pedido.rename(columns={'nº': 'sku'}, inplace=True)
            
            # Verifica la presencia de todas las columnas necesarias
            required_columns = ['sku', 'cantidad', 'peso bruto total', 'volumen']
            missing_columns = [col for col in required_columns if col not in df_pedido.columns]

            if missing_columns:
                return jsonify({'error': f'El archivo no contiene las columnas requeridas: {", ".join(missing_columns)}'}), 400

            # Renombrar columnas si es necesario
            column_mapping_pedido = {
                'cantidad': 'cantidad',
                'peso bruto total': 'peso bruto total',
                'volumen': 'volumen'
            }
            df_pedido.rename(columns=column_mapping_pedido, inplace=True)

            logger.debug("Iniciando procesamiento del pedido")
            resultados = procesar_pedido(df_pedido, provincia)
            logger.debug(f"Resultados procesados: {json.dumps(resultados, default=serialize_numpy)}")

            if not resultados:
                logger.warning("No se generaron resultados después del procesamiento")
                return jsonify({'error': 'No se encontraron productos que se pudieran procesar'}), 400
            
            # Guardar los resultados en el CSV
            guardar_registro_envio(resultados, provincia)
            
            # Convertir resultados a un formato serializable
            serializable_resultados = json.loads(json.dumps(resultados, default=serialize_numpy))
            return jsonify(serializable_resultados)
        
        except Exception as e:
            logger.error(f"Error en procesar_pedidos_route: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({'error': str(e)}), 500
        finally:
            os.remove(filepath)
    else:
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400

def procesar_pedido(df_pedido, provincia):
    productos = []

    for _, row in df_pedido.iterrows():
        sku = str(row['sku']).upper()
        cantidad = int(row['cantidad'])

        producto_info = df_productos[df_productos['SKU'] == sku]
        
        if producto_info.empty:
            logger.warning(f'No se encontró información para el SKU: {sku}. Usando datos del pedido.')
            peso = float(row['peso bruto total'])
            volumen = float(row['volumen'])
            alto = ancho = fondo = (volumen ** (1 / 3)) * 1000
            apilable = False
            max_apilado = 1
        else:
            producto_info = producto_info.iloc[0]
            peso = float(producto_info['PESO BRUTO (kg)'])
            volumen = float(producto_info['VOLUMEN (m3)'])
            alto = float(producto_info['ALTO EMBALAJE (MM)'])
            ancho = float(producto_info['ANCHO EMBALAJE (MM)'])
            fondo = float(producto_info['FONDO EMBALAJE (MM)'])
            apilable = producto_info.get('APILABLE', True)
            max_apilado = int(producto_info.get('MAX_APILADO', 2))

        productos.append(Producto(sku, producto_info['CATEGORIAS'] if not producto_info.empty else 'DESCONOCIDO',
                                  alto, ancho, fondo, volumen, peso, cantidad, apilable, max_apilado))

    palets, productos_xs, productos_especiales = empaquetar_productos(productos)

    resultados = []

    # Procesar palets
    for i, palet in enumerate(palets):
        tarifas = calcular_tarifas_palet({'peso': palet.peso_actual, 'volumen': palet.volumen_actual}, provincia)
        transportista_optimo, tarifa_optima = min(tarifas.items(), key=lambda x: x[1] if not pd.isna(x[1]) else float('inf'))
        resultados.append({
            'tipo': 'Palet',
            'numero': i + 1,
            'productos': [{'SKU': p.sku, 'CANTIDAD': p.cantidad} for p in palet.productos],
            'peso': palet.peso_actual,
            'volumen': palet.volumen_actual,
            'transportista_optimo': transportista_optimo,
            'tarifa_optima': tarifa_optima,
            'tarifas': tarifas
        })
    
    # Procesar productos XS
    if productos_xs:
        tarifas = calcular_tarifas_xs({'peso': sum(p.peso_total for p in productos_xs), 'volumen': sum(p.volumen_total for p in productos_xs)}, provincia)
        transportista_optimo, tarifa_optima = min(tarifas.items(), key=lambda x: x[1] if not pd.isna(x[1]) else float('inf'))
        resultados.append({
            'tipo': 'XS',
            'productos': [{'SKU': p.sku, 'CANTIDAD': p.cantidad} for p in productos_xs],
            'peso': sum(p.peso_total for p in productos_xs),
            'volumen': sum(p.volumen_total for p in productos_xs),
            'transportista_optimo': transportista_optimo,
            'tarifa_optima': tarifa_optima,
            'tarifas': tarifas
        })
    
    # Procesar productos especiales
    if productos_especiales:
        resultados.append({
            'tipo': 'Especial',
            'productos': [{'SKU': p.sku, 'CANTIDAD': p.cantidad} for p in productos_especiales],
            'mensaje': 'Preguntar a Manel'
        })

    return resultados

def guardar_registro_envio(resultados, provincia):
    """"
    Guarda los detalles de cada envío en un archivo CSV.

    :param resultados: Lista de diccionarios con los resultados del envío.
    :param provincia: Provincia de destinod del envío.
    """
    # Definir el archivo CSV
    file_path = 'registros_envio.csv'

    # Verificar si el archivo existe para decidir si escribir el encabezado
    archivo_existe = os.path.isfile(file_path)

    # Obtener fecha y hora actual
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Abrir el archivo en modo agregar ('a')
    with open(file_path, mode = 'a', newline = '', encoding = 'utf-8') as file:
        writer = csv.writer(file)

        # Escribir el encabezado si el archivo es nuevo
        if not archivo_existe:
            writer.writerow([
                'Tipo', 'Numero Palet', 'SKU', 'Cantidad', 'Peso Total', 
                'Volumen Total', 'Transportista Optimo', 'Tarifa Optima', 
                'Provincia', 'Fecha', 'Mensaje'
            ])
        
        # Iterar sobre los resultados procesados de cada envío y guardar los datos
        for resultado in resultados:
            tipo = resultado.get('tipo', 'Desconocido')
            if tipo == 'Palet':
                numero_palet = resultado.get('numero', '')  # Puede estar ausente
                transportista = resultado.get('transportista_optimo', 'Desconocido')
                tarifa = resultado.get('tarifa_optima', 0)
                mensaje = ''  # No se necesita mensaje para palet
                for producto in resultado.get('productos', []):
                    writer.writerow([
                        tipo,
                        numero_palet,
                        producto['SKU'],
                        producto['CANTIDAD'],
                        resultado.get('peso', 0),
                        resultado.get('volumen', 0),
                        transportista,
                        tarifa,
                        provincia,
                        fecha_actual,
                        mensaje
                    ])
            elif tipo == 'Especial':
                numero_palet = ''  # No aplica para productos especiales
                transportista = ''  # No aplica
                tarifa = ''  # No aplica
                mensaje = resultado.get('mensaje', '')
                for producto in resultado.get('productos', []):
                    writer.writerow([
                        tipo,
                        numero_palet,
                        producto['SKU'],
                        producto['CANTIDAD'],
                        resultado.get('peso', 0),
                        resultado.get('volumen', 0),
                        transportista,
                        tarifa,
                        provincia,
                        fecha_actual,
                        mensaje
                    ])

def calcular_tarifas_envios(envios, provincia):
    """
    Calcula las tarifas para una lista de envíos.
    """
    resultados = []
    for envio in envios:
        if 'es_palet' not in envio:
            logger.error(f"Envío sin información de 'es_palet': {envio}")
            resultados.append({'error': 'Falta información de "es_palet" en el envío'})
            continue

        # Verificar si 'productos' existe
        if 'productos' not in envio:
            logger.error(f"Envío sin 'productos': {envio}")
            resultados.append({'error': 'Falta información de productos en el envío'})
            continue
        
        # Calcula las tarifas para cada transportista
        if envio['es_palet']:
            tarifas = calcular_tarifas_palet(envio, provincia)
        else:
            tarifas = calcular_tarifas_xs(envio, provincia)

        # Seleccionar el transportista más barato
        transportista_optimo = None
        tarifa_optima = float('inf')
        for transportista, tarifa in tarifas.items():
            if not np.isnan(tarifa) and tarifa < tarifa_optima:
                transportista_optimo = transportista
                tarifa_optima = tarifa

        resultado = {
            'productos': envio['productos'],
            'peso': envio['peso'],
            'volumen': envio['volumen'],
            'es_palet': envio['es_palet'],
            'transportista_optimo': transportista_optimo,
            'tarifa_optima': tarifa_optima,
            'tarifas': tarifas,
            'notas': envio.get('notas', '')
        }
        resultados.append(resultado)

    if not resultados:
        return [{'error': 'No se pudo calcular ninguna tarifa'}]

    return resultados

def calcular_tarifas_xs(envio, provincia):
    """
    Calcula las tarifas para envíos XS.
    """
    if envio['peso'] < 10:
        tarifa_mrw = obtener_tarifa_mrw(df_mrw, provincia, envio['peso'], 1)  # Asumimos 1 bulto para XS
        tarifa_ontime = obtener_tarifa_ontime_xs(df_ontime, provincia, envio['peso'], '24')
        return {
            'MRW': tarifa_mrw if not pd.isna(tarifa_mrw) else None,
            'ONTIME': (tarifa_ontime * (1 + RECARGO_COMBUSTIBLE_ONTIME + RECARGO_SEGURO_ONTIME)) if not pd.isna(tarifa_ontime) else None
        }
    else:
        tarifa_mrw = obtener_tarifa_mrw(df_mrw, provincia, envio['peso'], 1)  # Asumimos 1 bulto para XS
        tarifa_cbl = obtener_tarifa_cbl(df_cbl, provincia, envio['peso'])
        tarifa_ontime = obtener_tarifa_ontime_xs(df_ontime, provincia, envio['peso'], '24')
        return {
            'MRW': tarifa_mrw if not pd.isna(tarifa_mrw) else None,
            'CBL': (tarifa_cbl * (1 + RECARGO_COMBUSTIBLE_CBL)) if not pd.isna(tarifa_cbl) else None,
            'ONTIME': (tarifa_ontime * (1 + RECARGO_COMBUSTIBLE_ONTIME + RECARGO_SEGURO_ONTIME)) if not pd.isna(tarifa_ontime) else None
        }

def calcular_tarifas_palet(envio, provincia):
    """
    Calcula las tarifas para envíos en palet.
    """
    peso_volumetrico_cbl = envio['volumen'] * 200
    peso_volumetrico_ontime = envio['volumen'] * 225

    tarifa_cbl = obtener_tarifa_cbl(df_cbl, provincia, peso_volumetrico_cbl)
    tarifa_ontime = obtener_tarifa_ontime(df_ontime, provincia, peso_volumetrico_ontime)

    return {
        'CBL': (tarifa_cbl * (1 + RECARGO_COMBUSTIBLE_CBL)) if not pd.isna(tarifa_cbl) else None,
        'ONTIME': (tarifa_ontime * (1 + RECARGO_COMBUSTIBLE_ONTIME + RECARGO_SEGURO_ONTIME)) if not pd.isna(tarifa_ontime) else None
    }


def calcular_devolucion():
    """
    Calcula las tarifas de devolución para un producto específico.
    """
    provincia = request.form['provincia']
    sku = request.form['sku']
    cantidad = int(request.form['cantidad'])

    producto = df_productos[df_productos['SKU'] == sku].iloc[0]
    peso_total = producto['PESO BRUTO (kg)'] * cantidad
    volumen = producto['ALTO EMBALAJE (MM)'] / 1000 * producto['ANCHO EMBALAJE (MM)'] / 1000 * producto['FONDO EMBALAJE (MM)'] / 1000 * cantidad

    if peso_total < MAX_PESO_XS:
        tarifas = calcular_tarifas_xs({'peso': peso_total, 'volumen': volumen, 'productos': [{'SKU': sku, 'CANTIDAD': cantidad}]}, provincia)
    else:
        tarifas = calcular_tarifas_palet({'peso': peso_total, 'volumen': volumen, 'productos': [{'SKU': sku, 'CANTIDAD': cantidad}]}, provincia)

    tarifas_devolucion = {}
    for transportista, tarifa in tarifas.items():
        if not np.isnan(tarifa):
            if transportista == 'CBL':
                tarifas_devolucion[transportista] = tarifa * (1 + RECARGO_DEVOLUCION_CBL)
            else:
                tarifas_devolucion[transportista] = tarifa  # No se aplica recargo adicional para otros transportistas

    return render_template('index.html', resultado_devolucion=tarifas_devolucion, provincias=provincias_comunes)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)
