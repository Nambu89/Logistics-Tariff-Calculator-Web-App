from flask import Flask, render_template, request
import pandas as pd
import numpy as np

app = Flask(__name__)

# Cargar los archivos Excel
file_path_cbl = 'Tarifas_CBL.xlsx'
file_path_ontime = 'Tarifas_ONTIME.xlsx'
file_path_mrw = 'Tarifas_MRW.xlsx'
file_path_productos = 'Productos.xlsx'

df_cbl = pd.read_excel(file_path_cbl)
df_ontime = pd.read_excel(file_path_ontime)
df_mrw = pd.read_excel(file_path_mrw)
df_productos = pd.read_excel(file_path_productos)

# Asegurarse de que las columnas numéricas son realmente numéricas
df_mrw['KG'] = pd.to_numeric(df_mrw['KG'], errors='coerce')
df_mrw = df_mrw.dropna(subset=['KG'])

df_cbl['KG'] = pd.to_numeric(df_cbl['KG'], errors='coerce')
df_cbl = df_cbl.dropna(subset=['KG'])

# Definir las listas de provincias
provincias_mrw = [
    "VALENCIA", "ALBACETE", "ALICANTE", "CASTELLON", "CUENCA", "BARCELONA", "TARRAGONA", "MADRID", "MURCIA", 
    "ALMERIA", "ZARAGOZA", "GUADALAJARA", "TOLEDO", "GIRONA", "LLEIDA", "CORDOBA", "GRANADA", "SEVILLA", 
    "JAEN", "CIUDAD REAL", "BURGOS", "SEGOVIA", "VALLADOLID", "LA RIOJA", "NAVARRA", "VIZCAYA", "CADIZ", 
    "MALAGA", "HUESCA", "ASTURIAS", "CANTABRIA", "AVILA", "LEON", "BADAJOZ", "CACERES", "VIZCAYA", "GUIPUZKOA", 
    "HUELVA", "TERUEL", "PALENCIA", "SALAMANCA", "SORIA", "ZAMORA", "A CORUÑA", "LUGO", "ORENSE", "PONTEVEDRA", 
    "MALLORCA", "IBIZA", "MENORCA"
]

provincias_cbl = provincias_mrw

provincias_ontime = ["A CORUÑA", "ALAVA", "ALBACETE", "ALICANTE", "ALMERIA", "ASTURIAS", "AVILA", "BADAJOZ", "PALMA DE MALLORCA", 
    "MENORCA", "BARCELONA", "BURGOS", "CACERES", "CADIZ", "CANTABRIA", "CASTELLON", "CIUDAD REAL", "CORDOBA", 
    "CUENCA", "GUIPUZKOA", "GIRONA", "GRANADA", "GRAN CANARIA", "GUADALAJARA", "HUELVA", "HUESCA", "JAEN", 
    "LA RIOJA", "LANZAROTE", "LEON", "LLEIDA", "LUGO", "MADRID", "MALAGA", "MURCIA", "NAVARRA", "ORENSE", 
    "PALENCIA", "PONTEVEDRA", "SALAMANCA", "SEGOVIA", "SEVILLA", "SORIA", "TARRAGONA", "TERUEL", "TOLEDO", 
    "VALENCIA", "VALLADOLID", "VIZCAYA", "ZAMORA", "ZARAGOZA", "PORTUGAL LISBOA", "PORTUGAL OPORTO", 
    "PORTUGAL COIMBRA", "PORTUGAL ZONA2", "GIBRALTAR", "CEUTA", "MELILLA", "ANDORRA"
]

provincias_unificadas = list(set(provincias_mrw + provincias_cbl + provincias_ontime))
provincias_unificadas.sort()  # Ordenar alfabéticamente

# Obtener categorías y SKUs para los desplegables
categorias = df_productos['CATEGORIAS'].unique().tolist()
skus = df_productos['SKU'].unique().tolist()

# Mapeo de provincias a zonas
provincias_zonas = {provincia: provincia for provincia in provincias_unificadas}

def obtener_tarifa_ontime(df, zona, peso):
    tarifas_ontime = [int(col) for col in df.columns if col.isdigit()]
    closest_weight_col = min((x for x in tarifas_ontime if x >= peso), default=None)
    
    if closest_weight_col is not None:
        tarifa_ontime_row = df[df['PROVINCIA DESTINO'] == zona]
        if not tarifa_ontime_row.empty:
            return tarifa_ontime_row.iloc[0][str(closest_weight_col)]
    
    return np.nan

def obtener_tarifa_ontime_xs(df, zona, peso, modalidad):
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
        print(f'Error en obtener_tarifa_ontime_xs: {e}')
        return np.nan

def obtener_tarifa_mrw(df, zona, peso_total, num_bultos):
    filtered_df = df[df['KG'] >= peso_total]
    if filtered_df.empty:
        return np.nan, np.nan, np.nan
    closest_weight_row = filtered_df.iloc[0]
    tarifa_base = closest_weight_row[zona] if zona in df.columns else np.nan
    recargo_bultos = max(0, num_bultos - 2) * 2
    tarifa_total = tarifa_base + recargo_bultos
    return tarifa_base, recargo_bultos, tarifa_total

def obtener_tarifa_cbl(df, zona, peso):
    try:
        filtered_df = df[df['KG'] >= peso]
        if filtered_df.empty:
            return np.nan
        
        closest_weight_row = filtered_df.iloc[0]
        return closest_weight_row[zona]
    except Exception as e:
        print(f"Error inesperado al obtener tarifa CBL: {str(e)}")
        return np.nan

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    if request.method == 'POST':
        if 'calcular' in request.form:
            # Lógica de cálculo regular
            tipo_producto = request.form.get('tipo_producto')
            province = request.form.get('province')
            num_bultos = int(request.form.get('num_bultos', 0))
            modalidad = request.form.get('modalidad', None)

            # Solo obtener category y sku si tipo_producto es "XS"
            category = request.form.get('category', None) if tipo_producto == 'XS' else None
            sku = request.form.get('sku', None) if tipo_producto == 'XS' else None

            if tipo_producto == 'XS' and category and sku:
                peso_producto = df_productos[(df_productos['CATEGORIAS'] == category) & (df_productos['SKU'] == sku)]['PESO BRUTO (kg)'].values
                if len(peso_producto) == 0:
                    result = 'No se encontró el producto con la categoría y SKU especificados.'
                else:
                    peso_total = peso_producto[0] * num_bultos

                    tarifa_base_mrw, recargo_bultos_mrw, tarifa_total_mrw = obtener_tarifa_mrw(df_mrw, province, peso_total, num_bultos)
                    tarifa_ontime_xs = obtener_tarifa_ontime_xs(df_ontime, province, peso_total, modalidad)

                    result = f'Para {num_bultos} bultos con SKU {sku} con peso total de {peso_total}kg y destino {province}:\n'
                    
                    if not np.isnan(tarifa_total_mrw):
                        result += (f'Tarifa base MRW: {tarifa_base_mrw:.2f}€\n'
                                f'Recargo por bultos extra MRW: {recargo_bultos_mrw:.2f}€\n'
                                f'Total tarifa MRW con recargos: {tarifa_total_mrw:.2f}€\n')
                    else:
                        result += "Tarifa MRW: No disponible\n"

                    tarifa_cbl_total = np.nan
                    if peso_total >= 10:
                        tarifa_cbl = obtener_tarifa_cbl(df_cbl, province, peso_total)
                        if not np.isnan(tarifa_cbl):
                            recargo_combustible_cbl = tarifa_cbl * 0.035
                            tarifa_cbl_total = tarifa_cbl + recargo_combustible_cbl
                            result += (f'Tarifa base CBL: {tarifa_cbl:.2f}€\n'
                                    f'Recargo por combustible CBL (3.5%): {recargo_combustible_cbl:.2f}€\n'
                                    f'Total tarifa CBL con recargo: {tarifa_cbl_total:.2f}€\n')
                        else:
                            result += "Tarifa CBL: No disponible\n"

                    if not np.isnan(tarifa_ontime_xs):
                        recargo_combustible_ontime = tarifa_ontime_xs * 0.04
                        recargo_seguro_ontime = tarifa_ontime_xs * 0.04
                        tarifa_ontime_xs_total = tarifa_ontime_xs + recargo_combustible_ontime + recargo_seguro_ontime
                        result += (f'Tarifa ONTIME XS ({modalidad} horas): {tarifa_ontime_xs:.2f}€\n'
                                f'Recargo por combustible ONTIME XS (4%): {recargo_combustible_ontime:.2f}€\n'
                                f'Recargo por seguro ONTIME XS (4%): {recargo_seguro_ontime:.2f}€\n'
                                f'Total tarifa ONTIME XS con recargos: {tarifa_ontime_xs_total:.2f}€\n')
                    else:
                        result += "Tarifa ONTIME XS: No disponible\n"

                    tarifas = {
                        "MRW": tarifa_total_mrw,
                        "CBL": tarifa_cbl_total,
                        "ONTIME XS": tarifa_ontime_xs_total
                    }

                    tarifas_validas = {k: v for k, v in tarifas.items() if not np.isnan(v)}
                    if tarifas_validas:
                        mejor_transportista = min(tarifas_validas, key=tarifas_validas.get)
                        result += f'\nMejor transportista: {mejor_transportista} con tarifa {tarifas_validas[mejor_transportista]:.2f}€\n'
                    else:
                        result += "\nNo se encontró un transportista válido.\n"

            elif tipo_producto == 'Normal':
                palet_type = request.form.get('palet_type')
                product_height = float(request.form.get('height', 0))

                base_area = 0.6 * 0.8 if palet_type == 'Medio Palet' else 1.2 * 0.8
                volume = base_area * (product_height + 0.15)
                kgs_cbl = volume * 200
                kgs_ontime = volume * 225

                result = (f"Para {palet_type} con altura {product_height}m y destino {province}:\n"
                        f"Volumen: {volume:.2f} m³\n"
                        f"KGS (CBL): {kgs_cbl:.2f} kg\n"
                        f"KGS (ONTIME): {kgs_ontime:.2f} kg\n\n")

                tarifa_cbl = obtener_tarifa_cbl(df_cbl, province, kgs_cbl)
                tarifa_ontime = obtener_tarifa_ontime(df_ontime, province, kgs_ontime)

                if not np.isnan(tarifa_cbl):
                    recargo_combustible_cbl = tarifa_cbl * 0.035
                    tarifa_cbl_total = tarifa_cbl + recargo_combustible_cbl
                    result += (f"Tarifa base CBL para {province}: {tarifa_cbl:.2f}€\n"
                               f"Recargo por combustible CBL (3.5%): {recargo_combustible_cbl:.2f}€\n"
                               f"Total tarifa CBL con recargo: {tarifa_cbl_total:.2f}€\n")
                else:
                    tarifa_cbl_total = np.nan
                    result += "Tarifa CBL: No disponible\n"

                if not np.isnan(tarifa_ontime):
                    recargo_combustible_ontime = tarifa_ontime * 0.04
                    recargo_seguro_ontime = tarifa_ontime * 0.04
                    tarifa_ontime_total = tarifa_ontime + recargo_combustible_ontime + recargo_seguro_ontime
                    result += (f"Tarifa base ONTIME para {province}: {tarifa_ontime:.2f}€\n"
                               f"Recargo por combustible ONTIME (4%): {recargo_combustible_ontime:.2f}€\n"
                               f"Recargo por seguro ONTIME (4%): {recargo_seguro_ontime:.2f}€\n"
                               f"Total tarifa ONTIME con recargos: {tarifa_ontime_total:.2f}€\n")
                else:
                    tarifa_ontime_total = np.nan
                    result += "Tarifa ONTIME: No disponible\n"

                tarifas = {"CBL": tarifa_cbl_total, "ONTIME": tarifa_ontime_total}
                tarifas_validas = {k: v for k, v in tarifas.items() if not np.isnan(v)}
                if tarifas_validas:
                    mejor_transportista = min(tarifas_validas, key=tarifas_validas.get)
                    result += f'\nMejor transportista: {mejor_transportista} con tarifa {tarifas_validas[mejor_transportista]:.2f}€\n'
                else:
                    result += "\nNo se encontró un transportista válido.\n"

            if 'devolucion' in request.form:
            # Lógica para calcular devolución
                province = request.form.get('province')
                tipo_producto = request.form.get('tipo_producto')
                category = request.form.get('category', None)
                sku = request.form.get('sku', None)
                num_bultos = int(request.form.get('num_bultos', 0))
                height = request.form.get('height')  # Obtener la altura seleccionada

                # Pasar la altura a la función calculate_return_tariff
                result = calculate_return_tariff(province, tipo_producto, category, sku, num_bultos, height)

    # Retornar render_template
    return render_template('index.html', result = result, provincias_unificadas = provincias_unificadas, categorias = categorias, skus = skus)

def calculate_return_tariff(province, tipo_producto, categoria, sku, num_bultos, height=None):
    province_normalized = province  # No se realiza normalización
    tarifa_cbl_total = np.nan
    tarifa_ontime_total = np.nan
    tarifa_ontime_xs = np.nan  # Asignar un valor por defecto

    if tipo_producto == 'Normal':
        if not height:  # Verificar si la altura fue proporcionada
            return "Debe seleccionar una altura para el producto."

        try:
            altura_producto = float(height)  # Convertir la altura seleccionada a un valor float
        except ValueError:
            return "La altura seleccionada no es válida."

        base_area = 1.2 * 0.8  # Asumiendo que siempre se usa un Palet Completo para devoluciones normales
        volume = base_area * (altura_producto + 0.15)
        peso_total_cbl = volume * 200
        peso_total_ontime = volume * 225

        # Calcular tarifa CBL con recargos
        tarifa_cbl = obtener_tarifa_cbl(df_cbl, province_normalized, peso_total_cbl)
        if not np.isnan(tarifa_cbl):
            recargo_combustible_cbl = tarifa_cbl * 0.035
            recargo_devolucion = tarifa_cbl * 0.2
            tarifa_cbl_total = tarifa_cbl + recargo_combustible_cbl + recargo_devolucion

        # Calcular tarifa ONTIME con recargos
        tarifa_ontime = obtener_tarifa_ontime(df_ontime, province_normalized, peso_total_ontime)
        if not np.isnan(tarifa_ontime):
            recargo_combustible_ontime = tarifa_ontime * 0.04
            recargo_seguro_ontime = tarifa_ontime * 0.04
            tarifa_ontime_total = tarifa_ontime + recargo_combustible_ontime + recargo_seguro_ontime

    elif tipo_producto == 'XS':
        # Calcular peso del producto XS
        peso_producto = df_productos[
            (df_productos['CATEGORIAS'] == categoria) &
            (df_productos['SKU'] == sku)
        ]['PESO BRUTO (kg)'].values

        if len(peso_producto) == 0:
            return "Producto no encontrado."

        peso_total = peso_producto[0] * int(num_bultos)

        # Calcular tarifa CBL con recargos
        tarifa_cbl = obtener_tarifa_cbl(df_cbl, province_normalized, peso_total)
        if not np.isnan(tarifa_cbl):
            recargo_combustible_cbl = tarifa_cbl * 0.035
            recargo_devolucion = tarifa_cbl * 0.2
            tarifa_cbl_total = tarifa_cbl + recargo_combustible_cbl + recargo_devolucion

        # Calcular tarifa ONTIME XS con recargos
        tarifa_ontime_xs = obtener_tarifa_ontime_xs(df_ontime, province_normalized, peso_total, '24')
        if not np.isnan(tarifa_ontime_xs):
            recargo_combustible_ontime = tarifa_ontime_xs * 0.04
            recargo_seguro_ontime = tarifa_ontime_xs * 0.04
            tarifa_ontime_total = tarifa_ontime_xs + recargo_combustible_ontime + recargo_seguro_ontime

    # Comparar tarifas y mostrar el mejor resultado
    tarifas = {'CBL': tarifa_cbl_total, 'ONTIME': tarifa_ontime_total}
    tarifas_validas = {k: v for k, v in tarifas.items() if not np.isnan(v)}

    if not tarifas_validas:
        return 'No se encontraron tarifas válidas para la devolución.'

    mejor_transportista = min(tarifas_validas, key=tarifas_validas.get)

    # Mostrar el resultado
    result = (f'Para devolución desde {province} a Valencia con producto tipo {tipo_producto}:\n'
            f'Tarifa CBL: {tarifa_cbl_total:.2f}€\n'
            f'Recargo de CBL por combustible (3.5%): {recargo_combustible_cbl:.2f}€\n'
            f'Recargo de CBL por devolución (20%): {recargo_devolucion:.2f}€\n'
            f'Tarifa total CBL: {tarifa_cbl_total:.2f}€\n'
            f'Tarifa ONTIME: {tarifa_ontime_total:.2f}€\n'
            f'Recargo de ONTIME por combustible (4%): {recargo_combustible_ontime:.2f}€\n'
            f'Recargo de ONTIME por seguro (4%): {recargo_seguro_ontime:.2f}€\n'
            f'Tarifa total ONTIME: {tarifa_ontime_total:.2f}€\n')

    return result


if __name__ == '__main__':
    app.run(debug=True)
