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


class Producto:
    """
    Representa un producto con sus características físicas y de envío.
    """
    def __init__(self, sku, categorias, alto, ancho, fondo, volumen, peso, cantidad, apilable=True, max_apilado=2):
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

        # Lógica específica para COMBI, LAVADORA, SECADORA y LAVAVAJILLAS
        if any(cat in categorias.upper() for cat in ['COMBI', 'FRIGO', 'REFRIGER']):
            self.apilable = False
            self.max_apilado = 2  # Máximo 2 productos por palet
        elif any(cat in categorias.upper() for cat in ['LAVADORA', 'SECADORA', 'LAVAVAJILLAS']):
            self.apilable = True
            self.max_apilado = 4  # Máximo 4 productos por palet

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

    def puede_agregar(self, producto, cantidad=1):
        peso_total_producto = producto.peso * cantidad
        altura_total_producto = producto.alto * cantidad

        if self.peso_actual + peso_total_producto > self.peso_max:
            return False
        if self.altura_actual + altura_total_producto > self.alto_max:
            return False

        return True

    def agregar_producto(self, producto, cantidad):
        cantidad_maxima = min(
            cantidad,
            (self.peso_max - self.peso_actual) // producto.peso,
            int((self.alto_max - self.altura_actual) / producto.alto)
        )

        if cantidad_maxima <= 0:
            return 0

        self.productos.append({
            'sku': producto.sku,
            'categorias': producto.categorias,
            'cantidad': cantidad_maxima,
            'peso': producto.peso,
            'volumen': producto.volumen,
            'ancho': producto.ancho,
            'fondo': producto.fondo,
            'alto': producto.alto
        })
        
        self.peso_actual += producto.peso * cantidad_maxima
        self.volumen_actual += producto.volumen * cantidad_maxima
        self.altura_actual += producto.alto * cantidad_maxima

        return cantidad_maxima

class MedioPalet(Palet):
    def __init__(self):
        super().__init__(ancho=0.8, fondo=0.6, alto_max=MAX_ALTO_PALET, peso_max=MAX_PESO_PALET)

    def agregar_producto(self, producto, cantidad=1):
        if not self.puede_agregar(producto, cantidad):
            return False

        peso_total_producto = producto.peso * cantidad
        altura_por_nivel = producto.alto
        niveles_nuevos = ( (cantidad - 1) // 2 + 1 )  # Calcula cuántos niveles nuevos se necesitan

        # Actualizar o agregar el producto en la lista de productos
        existing_product = next((p for p in self.productos if p['sku'] == producto.sku), None)
        if existing_product:
            existing_product['cantidad'] += cantidad
        else:
            self.productos.append({
                'sku': producto.sku,
                'categorias': producto.categorias,
                'cantidad': cantidad,
                'peso': producto.peso,
                'volumen': producto.volumen,
                'ancho': producto.ancho,
                'fondo': producto.fondo,
                'alto': producto.alto
            })
        # Actualizar peso y altura del palet
        self.peso_actual += peso_total_producto
        self.volumen_actual += producto.volumen * cantidad
        self.altura_actual += altura_por_nivel * niveles_nuevos

        return True

def empaquetar_productos(productos):
    productos_ordenados = sorted(productos, key=lambda p: p.volumen_total, reverse=True)
    palets_completos = []
    medios_palets = []
    productos_xs = []
    productos_especiales = []

    def crear_nuevo_palet(es_medio=False):
        return MedioPalet() if es_medio else Palet()

    def intentar_agregar_a_palet(producto, cantidad, palet):
        es_nevera = any(cat in producto.categorias.upper() for cat in ['COMBI', 'FRIGO', 'REFRIGER', 'CONGELAD'])
        es_lavadora = any(cat in producto.categorias.upper() for cat in ['LAVADORA', 'SECADORA', 'LAVAVAJILLAS'])

        if es_nevera:
            if isinstance(palet, Palet) and sum(1 for p in palet.productos if any(cat in p['categorias'].upper() for cat in ['COMBI', 'FRIGO', 'REFRIGER', 'CONGELAD'])) < 2:
                return palet.agregar_producto(producto, 1)
            return 0
        elif es_lavadora:
            if isinstance(palet, Palet):
                if len(palet.productos) == 1 and any(cat in palet.productos[0]['categorias'].upper() for cat in ['COMBI', 'FRIGO', 'REFRIGER', 'CONGELAD']):
                    return palet.agregar_producto(producto, min(cantidad, 2))
                elif sum(p['cantidad'] for p in palet.productos if any(cat in p['categorias'].upper() for cat in ['LAVADORA', 'SECADORA', 'LAVAVAJILLAS'])) + cantidad <= 4:
                    return palet.agregar_producto(producto, min(cantidad, 4 - sum(p['cantidad'] for p in palet.productos if any(cat in p['categorias'].upper() for cat in ['LAVADORA', 'SECADORA', 'LAVAVAJILLAS']))))
            return 0
        else:
            return palet.agregar_producto(producto, cantidad)

    neveras = [p for p in productos_ordenados if any(cat in p.categorias.upper() for cat in ['COMBI', 'FRIGO', 'REFRIGER', 'CONGELAD'])]
    otros_productos = [p for p in productos_ordenados if p not in neveras]

    # Agrupar neveras en palets completos
    for i in range(0, len(neveras), 2):
        if i + 1 < len(neveras):
            nuevo_palet = crear_nuevo_palet()
            nuevo_palet.agregar_producto(neveras[i], 1)
            nuevo_palet.agregar_producto(neveras[i+1], 1)
            palets_completos.append(nuevo_palet)
        else:
            medio_palet = crear_nuevo_palet(es_medio=True)
            medio_palet.agregar_producto(neveras[i], 1)
            medios_palets.append(medio_palet)

    # Procesar otros productos
    for producto in otros_productos:
        unidades_restantes = producto.cantidad
        while unidades_restantes > 0:
            palet_encontrado = False
            for palet in palets_completos + medios_palets:
                cantidad_agregada = intentar_agregar_a_palet(producto, unidades_restantes, palet)
                if cantidad_agregada > 0:
                    unidades_restantes -= cantidad_agregada
                    palet_encontrado = True
                    break
            
            if not palet_encontrado:
                nuevo_palet = crear_nuevo_palet()
                cantidad_agregada = intentar_agregar_a_palet(producto, unidades_restantes, nuevo_palet)
                if cantidad_agregada > 0:
                    palets_completos.append(nuevo_palet)
                    unidades_restantes -= cantidad_agregada
                else:
                    productos_especiales.append(producto)
                    break

    # Logging
    logger.debug(f"Palets completos creados: {len(palets_completos)}, Medios palets creados: {len(medios_palets)}, Productos XS: {len(productos_xs)}, Productos especiales: {len(productos_especiales)}")
    
    for i, palet in enumerate(palets_completos):
        logger.debug(f"Contenido del palet completo {i+1}:")
        for producto in palet.productos:
            logger.debug(f"  - SKU: {producto['sku']}, Cantidad: {producto['cantidad']}, Categoría: {producto['categorias']}")
    
    for i, palet in enumerate(medios_palets):
        logger.debug(f"Contenido del medio palet {i+1}:")
        for producto in palet.productos:
            logger.debug(f"  - SKU: {producto['sku']}, Cantidad: {producto['cantidad']}, Categoría: {producto['categorias']}")
    
    return palets_completos, medios_palets, productos_xs, productos_especiales

# Obtener provincias
provincias_cbl = set(df_cbl.columns[2:])
provincias_ontime = set(df_ontime['PROVINCIA DESTINO'].unique())
provincias_mrw = set(df_mrw.columns[1:])

provincias_comunes = list(provincias_cbl.intersection(provincias_ontime, provincias_mrw))
provincias_comunes.extend(["IBIZA", "MALLORCA"])  # Añadir destinos especiales
provincias_comunes = list(set(provincias_comunes))  # Eliminar duplicados si los hubiera
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

        if zona in ["IBIZA", "MALLORCA"] and zona not in df['PROVINCIA DESTINO'].values:
            return "El transportista no envía a este destino"

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
    Si el destino no está contemplado, devuelve un mensaje de no disponibilidad.
    """
    zona = zona.upper()  # Aseguramos que el destino esté en mayúsculas
    if zona not in df['PROVINCIA DESTINO'].unique():
        return "El transportista no envía a este destino."  # Si no encuentra el destino, devuelve el mensaje

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
        
        if zona not in df.columns:
            if zona in ["IBIZA", "MALLORCA"]:
                return "El transportista no envía a este destino"
            return np.nan
        
        tarifa_base = closest_weight_row[zona]
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
            if zona in ["IBIZA", "MALLORCA"]:
                return "El transportista no envía a este destino"
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
    elif isinstance(obj, (list, tuple)):  # Para listas y tuplas
        return [serialize_numpy(item) for item in obj]
    elif isinstance(obj, dict):  # Para diccionarios
        return {key: serialize_numpy(value) for key, value in obj.items()}
    elif isinstance(obj, (int, float, str)):  # Tipos simples permitidos en JSON
        return obj
    else:
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

            logger.debug("Iniciando procesamiento del pedido")
            resultados = procesar_pedido(df_pedido, provincia)
            logger.debug(f"Resultados procesados: {json.dumps(resultados, default=serialize_numpy)}")

            if not resultados:
                logger.warning("No se generaron resultados después del procesamiento")
                return jsonify({'error': 'No se encontraron productos que se pudieran procesar'}), 400
            
            # Guardar los resultados en el CSV
            guardar_registro_envio(resultados, provincia)
            
            # Analizar y resumir los resultados
            resumen, mensaje_usuario = analizar_y_resumir_pedido(resultados)

            # Convertir resultados a un formato serializable
            serializable_resultados = json.loads(json.dumps(resultados, default=serialize_numpy))
            
            return jsonify({'resultados': serializable_resultados, 'resumen': resumen, 'mensaje': mensaje_usuario})
        
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
    """
    Procesa el pedido cargado y lo organiza en palets.
    
    Args:
        df_pedido (DataFrame): Los datos del pedido con productos.
        provincia (str): La provincia de destino para calcular las tarifas.
    
    Returns:
        list: Una lista de diccionarios con detalles sobre palets, productos XS, y productos especiales.
    """

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
            categorias = 'DESCONOCIDO'
        else:
            producto_info = producto_info.iloc[0]
            peso = float(producto_info['PESO BRUTO (kg)'])
            volumen = float(producto_info['VOLUMEN (m3)'])
            alto = float(producto_info['ALTO EMBALAJE (MM)'])
            ancho = float(producto_info['ANCHO EMBALAJE (MM)'])
            fondo = float(producto_info['FONDO EMBALAJE (MM)'])
            apilable = producto_info.get('APILABLE', True)
            max_apilado = int(producto_info.get('MAX_APILADO', 2))
            categorias = producto_info['CATEGORIAS']

        productos.append(Producto(sku, categorias, alto, ancho, fondo, volumen, peso, cantidad, apilable, max_apilado))

        palets_completos, medios_palets, productos_xs, productos_especiales = empaquetar_productos(productos)

    resultados = []

    # Procesar palets completos
    for i, palet in enumerate(palets_completos):
        tarifas = calcular_tarifas_palet({'peso': palet.peso_actual, 'volumen': palet.volumen_actual}, provincia)
        transportista_optimo, tarifa_optima = min(
            tarifas.items(), key=lambda x: x[1] if not pd.isna(x[1]) else float('inf')
        )
        resultados.append({
            'tipo': 'Palet Completo',
            'numero': i + 1,
            'productos': [{'SKU': p['sku'], 'CANTIDAD': p['cantidad']} for p in palet.productos],
            'peso': palet.peso_actual,
            'volumen': palet.volumen_actual,
            'transportista_optimo': transportista_optimo,
            'tarifa_optima': tarifa_optima,
            'tarifas': tarifas
        })

        # Procesar medios palets
    for i, palet in enumerate(medios_palets):
        tarifas = calcular_tarifas_palet({'peso': palet.peso_actual, 'volumen': palet.volumen_actual}, provincia)
        transportista_optimo, tarifa_optima = min(
            tarifas.items(), key=lambda x: x[1] if not pd.isna(x[1]) else float('inf')
        )
        resultados.append({
            'tipo': 'Medio Palet',
            'numero': i + 1,
            'productos': [{'SKU': p['sku'], 'CANTIDAD': p['cantidad']} for p in palet.productos],
            'peso': palet.peso_actual,
            'volumen': palet.volumen_actual,
            'transportista_optimo': transportista_optimo,
            'tarifa_optima': tarifa_optima,
            'tarifas': tarifas
        })

    # Procesar productos XS
    if productos_xs:
        total_peso_xs = sum(p.peso_total for p in productos_xs)
        total_volumen_xs = sum(p.volumen_total for p in productos_xs)
        tarifas = calcular_tarifas_xs({'peso': total_peso_xs, 'volumen': total_volumen_xs}, provincia)
        transportista_optimo, tarifa_optima = min(
            tarifas.items(), key=lambda x: x[1] if not pd.isna(x[1]) else float('inf')
        )
        resultados.append({
            'tipo': 'XS',
            'productos': [{'SKU': p.sku, 'CANTIDAD': p.cantidad} for p in productos_xs],
            'peso': total_peso_xs,
            'volumen': total_volumen_xs,
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
# Función para analizar y resumir el pedido

def analizar_y_resumir_pedido(resultados):
    logger.debug(f"Iniciando análisis y resumen de {len(resultados)} resultados")
    total_palets = 0
    total_medios_palets = 0
    total_xs = 0
    total_especiales = 0
    total_precio_cbl = 0
    total_precio_ontime = 0
    total_precio_mrw = 0
    conteo_transportistas = {"CBL": 0, "ONTIME": 0, "MRW": 0}
    resumen_por_envio = []

    for resultado in resultados:
        if resultado['tipo'] == 'Palet':
            total_palets += 1
        elif resultado['tipo'] == 'Medio Palet':
            total_medios_palets += 1
        elif resultado['tipo'] == 'XS':
            total_xs += 1
        elif resultado['tipo'] == 'Especial':
            total_especiales += 1

        if 'tarifas' in resultado:
            total_precio_cbl += resultado['tarifas'].get('CBL', 0)
            total_precio_ontime += resultado['tarifas'].get('ONTIME', 0)
            total_precio_mrw += resultado['tarifas'].get('MRW', 0)

        if 'transportista_optimo' in resultado:
            conteo_transportistas[resultado['transportista_optimo']] += 1

        productos_str = ", ".join([f"{p['CANTIDAD']} x {p['SKU']}" for p in resultado.get('productos', [])])
        
        resumen_por_envio.append({
            'tipo': resultado['tipo'],
            'numero': resultado.get('numero', ''),
            'productos': productos_str,
            'precio_CBL': resultado.get('tarifas', {}).get('CBL', 'N/A'),
            'precio_ONTIME': resultado.get('tarifas', {}).get('ONTIME', 'N/A'),
            'precio_MRW': resultado.get('tarifas', {}).get('MRW', 'N/A'),
            'transportista_optimo': resultado.get('transportista_optimo', 'N/A')
        })

    transportista_mayoritario = max(conteo_transportistas, key=conteo_transportistas.get) if conteo_transportistas else 'No disponible'
    total_precio_por_transportista = {
        'CBL': total_precio_cbl,
        'ONTIME': total_precio_ontime,
        'MRW': total_precio_mrw
    }
    transportista_optimo_total = min(
        (k for k, v in total_precio_por_transportista.items() if v > 0), 
        key=lambda k: total_precio_por_transportista[k],
        default='No disponible'
    )

    resumen = {
        'total_palets': total_palets,
        'total_medios_palets': total_medios_palets,
        'total_xs': total_xs,
        'total_especiales': total_especiales,
        'precio_total_CBL': total_precio_cbl,
        'precio_total_ONTIME': total_precio_ontime,
        'precio_total_MRW': total_precio_mrw,
        'transportista_mayoritario': transportista_mayoritario,
        'transportista_optimo_total': transportista_optimo_total,
        'resumen_por_envio': resumen_por_envio,
        'conteo_transportistas': conteo_transportistas
    }

    mensaje_usuario = f"""
    Resumen del pedido:
    - Total de palets completos: {total_palets}
    - Total de medios palets: {total_medios_palets}
    - Total de envíos XS: {total_xs}
    - Total de envíos especiales: {total_especiales}
    - Precio total con CBL: {total_precio_cbl:.2f}€
    - Precio total con ONTIME: {total_precio_ontime:.2f}€
    - Precio total con MRW: {total_precio_mrw:.2f}€

    El transportista mayoritario en los envíos individuales es {transportista_mayoritario}.
    El transportista más económico para todo el pedido es {transportista_optimo_total}.

    Recomendación: Utilizar {transportista_optimo_total} para todo el pedido.

    Detalle por envío:
    """
    for envio in resumen_por_envio:
        productos_str = envio['productos']
        precio_cbl = f"{envio['precio_CBL']:.2f}€" if envio['precio_CBL'] != 'N/A' else 'N/A'
        precio_ontime = f"{envio['precio_ONTIME']:.2f}€" if envio['precio_ONTIME'] != 'N/A' else 'N/A'
        precio_mrw = f"{envio['precio_MRW']:.2f}€" if envio['precio_MRW'] != 'N/A' else 'N/A'
        mensaje_usuario += f"{envio['tipo']} {envio['numero']} ({productos_str}): CBL ({precio_cbl}), ONTIME ({precio_ontime}), MRW ({precio_mrw}) "
        mensaje_usuario += f"-> Más económico: {envio['transportista_optimo']}\n"

    logger.debug(f"Resumen completado: {total_palets} palets completos, {total_medios_palets} medios palets, {total_xs} XS, {total_especiales} especiales, {len(resumen_por_envio)} envíos en total")
    return resumen, mensaje_usuario

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
    peso_volumetrico_cbl = envio['volumen'] * 200
    peso_volumetrico_ontime = envio['volumen'] * 225

    tarifa_cbl = obtener_tarifa_cbl(df_cbl, provincia, peso_volumetrico_cbl)
    tarifa_ontime = obtener_tarifa_ontime(df_ontime, provincia, peso_volumetrico_ontime)

    # Solo recargo de combustible y seguro, sin recargo por devolución
    return {
        'CBL': (tarifa_cbl * (1 + RECARGO_COMBUSTIBLE_CBL)) if not pd.isna(tarifa_cbl) else None,
        'ONTIME': (tarifa_ontime * (1 + RECARGO_COMBUSTIBLE_ONTIME + RECARGO_SEGURO_ONTIME)) if not pd.isna(tarifa_ontime) else None
    }


@app.route('/calcular_devolucion', methods=['POST'])
def calcular_devolucion():
    provincia = request.form['provincia']
    
    tarifas_devolucion = {}

    if 'file-devolucion' in request.files and request.files['file-devolucion'].filename != '':
        file = request.files['file-devolucion']
        
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                df_devolucion = pd.read_excel(filepath, engine='openpyxl')

                if df_devolucion.shape[1] < 2:
                    return jsonify({'error': 'El archivo debe tener al menos 2 columnas'}), 400

                df_devolucion.columns = df_devolucion.columns.str.strip().str.lower()
                df_devolucion['cantidad'] = df_devolucion['cantidad'].astype(str).str.replace(',', '').astype(int)

                if 'sku' not in df_devolucion.columns or 'cantidad' not in df_devolucion.columns:
                    return jsonify({'error': 'El archivo debe contener columnas "sku" y "cantidad"'}), 400

                for _, row in df_devolucion.iterrows():
                    sku = str(row['sku']).upper()
                    cantidad = int(row['cantidad'])

                    if sku not in df_productos['SKU'].values:
                        return jsonify({'error': f'SKU {sku} no encontrado en los productos'}), 400
 
                    producto = df_productos[df_productos['SKU'] == sku].iloc[0]
                    peso_total = producto['PESO BRUTO (kg)'] * cantidad
                    volumen = producto['ALTO EMBALAJE (MM)'] / 1000 * producto['ANCHO EMBALAJE (MM)'] / 1000 * producto['FONDO EMBALAJE (MM)'] / 1000 * cantidad

                    tarifas = calcular_tarifas_palet({'peso': peso_total, 'volumen': volumen}, provincia)

                    # Inicializar variables para el transportista más barato
                    transportista_optimo = None
                    tarifa_optima = float('inf')

                    tarifas_sku = {}
                    for transportista, tarifa in tarifas.items():
                        if not pd.isna(tarifa):
                            if transportista == 'CBL':
                                tarifas_sku[transportista] = tarifa * (1 + RECARGO_DEVOLUCION_CBL + RECARGO_COMBUSTIBLE_CBL)
                            else:
                                tarifas_sku[transportista] = tarifa

                            # Comparamos la tarifa actual con la tarifa óptima
                            if tarifa < tarifa_optima:
                                tarifa_optima = tarifa
                                transportista_optimo = transportista

                    tarifas_devolucion[sku] = {
                        'tarifas': tarifas_sku,
                        'transportista_optimo': transportista_optimo,
                        'tarifa_optima': tarifa_optima
                    }

                return render_template('index.html', resultado_devolucion=tarifas_devolucion, provincias=provincias_comunes)

            except Exception as e:
                import traceback
                logger.error(f"Error en calcular_devolucion: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return jsonify({'error': f'Error procesando el archivo de devolución: {str(e)}'}), 500

            finally:
                os.remove(filepath)
    else:
        # Si no se ha cargado un archivo, usar SKU y cantidad del formulario
        sku = request.form['sku']
        cantidad = int(request.form['cantidad'])

        if sku not in df_productos['SKU'].values:
            return jsonify({'error': f'SKU {sku} no encontrado en los productos'}), 400

        producto = df_productos[df_productos['SKU'] == sku].iloc[0]
        peso_total = producto['PESO BRUTO (kg)'] * cantidad
        volumen = producto['ALTO EMBALAJE (MM)'] / 1000 * producto['ANCHO EMBALAJE (MM)'] / 1000 * producto['FONDO EMBALAJE (MM)'] / 1000 * cantidad

        # Ajuste: Eliminamos la clave 'productos' ya que no es necesaria aquí
        tarifas = calcular_tarifas_palet({'peso': peso_total, 'volumen': volumen}, provincia)

        tarifas_sku = {}
        transportista_optimo = None
        tarifa_optima = float('inf')

        for transportista, tarifa in tarifas.items():
            if not pd.isna(tarifa):
                if transportista == 'CBL':
                    tarifas_sku[transportista] = tarifa * (1 + RECARGO_DEVOLUCION_CBL + RECARGO_COMBUSTIBLE_CBL)
                else:
                    tarifas_sku[transportista] = tarifa

                # Comparamos la tarifa actual con la tarifa óptima
                if tarifa < tarifa_optima:
                    tarifa_optima = tarifa
                    transportista_optimo = transportista

        tarifas_devolucion[sku] = {
            'tarifas': tarifas_sku,
            'transportista_optimo': transportista_optimo,
            'tarifa_optima': tarifa_optima
        }

        return render_template('index.html', resultado_devolucion=tarifas_devolucion, provincias=provincias_comunes)
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)