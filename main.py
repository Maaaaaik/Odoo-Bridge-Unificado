from flask import Flask, request, jsonify
import xmlrpc.client
from datetime import datetime, date
import calendar
import os
import re

app = Flask(__name__)

# --- Función auxiliar para la conexión a Odoo ---
def connect_to_odoo():
    """
    Establece conexión y autenticación con Odoo.
    Retorna (common, models, uid, password, db) o (None, mensaje_error, codigo_http).
    """
    url = os.environ.get("ODOO_URL")
    db = os.environ.get("ODOO_DB") # Esta variable se lee correctamente aquí
    username = os.environ.get("ODOO_USERNAME")
    password = os.environ.get("ODOO_PASSWORD")

    if not all([url, db, username, password]):
        return None, "Faltan las credenciales de Odoo en las variables de entorno", 500

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return None, "No se pudo autenticar con Odoo", 403
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        return common, models, uid, password, db
    except Exception as e:
        return None, f"Error al conectar con Odoo: {e}", 500

# --- Endpoint para Totales CSV ---
@app.route("/api/totales/csv", methods=["GET"])
def obtener_totales_csv():
    fecha_str = request.args.get("fecha")
    if not fecha_str:
        return "Falta la fecha", 400

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return "Formato de fecha incorrecto (YYYY-MM-DD)", 400

    common, models, uid, password, db = connect_to_odoo()
    if common is None:
        return models, uid

    try:
        orders = models.execute_kw(
            db, uid, password, 'pos.order', 'search_read',
            [['date_order', '>=', f"{fecha} 00:00:00"],
             ['date_order', '<=', f"{fecha} 23:59:59"],
             ['state', 'in', ['done', 'registered', 'paid', 'invoiced']]],
            {'fields': ['amount_total', 'config_id']}
        )

        totales_por_sucursal = {}
        for order in orders:
            nombre = order['config_id'][1]
            total = order['amount_total']
            totales_por_sucursal[nombre] = totales_por_sucursal.get(nombre, 0) + total

        resultado = [{'fecha': fecha_str, 'sucursal': nombre, 'total': total} for nombre, total in totales_por_sucursal.items()]
        return jsonify(resultado)
    except Exception as e:
        return f"Error al procesar la solicitud de totales: {e}", 500

# --- Endpoint para Kilos por Orden CSV ---
@app.route("/api/kilos_por_orden/csv", methods=["GET"])
def obtener_kilos_por_orden_csv():
    fecha_str = request.args.get("fecha")
    if not fecha_str:
        return "Falta la fecha", 400

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return "Formato de fecha incorrecto (YYYY-MM-DD)", 400

    common, models, uid, password, db = connect_to_odoo()
    if common is None:
        return models, uid

    try:
        orders = models.execute_kw(
            db, uid, password, 'pos.order', 'search_read',
            [['date_order', '>=', f"{fecha} 00:00:00"],
             ['date_order', '<=', f"{fecha} 23:59:59"],
             ['state', 'in', ['done', 'registered', 'paid', 'invoiced']]],
            {'fields': ['config_id', 'x_studio_float_field_1u1_1irfgb3un']}
        )

        resultado = []
        for order in orders:
            nombre_sucursal = order['config_id'][1]
            total_kilos = order.get('x_studio_float_field_1u1_1irfgb3un', 0.0)

            if total_kilos > 0:
                resultado.append({
                    'fecha': fecha_str,
                    'sucursal': nombre_sucursal,
                    'kilos_total_orden': total_kilos
                })
        return jsonify(resultado)
    except xmlrpc.client.Fault as e:
        # Aquí capturamos la traza de Odoo para obtener el error completo
        return f"Error al procesar la solicitud: {e.args}", 500
    except Exception as e:
        return f"Error al procesar la solicitud: {e}", 500

# --- Endpoint para Kilos por Mes CSV ---
@app.route("/api/kilos_por_mes/csv", methods=["GET"])
def obtener_kilos_por_mes_csv():
    mes_str = request.args.get("mes")
    anio_str = request.args.get("anio")

    if not mes_str or not anio_str:
        return "Faltan los parámetros 'mes' y/o 'anio'", 400

    try:
        mes = int(mes_str)
        anio = int(anio_str)
        if not (1 <= mes <= 12) or not (1900 <= anio <= 2100):
            raise ValueError("Mes o año fuera de rango válido.")
    except ValueError as e:
        return f"Formato de mes o año incorrecto. Error: {e}", 400

    primer_dia_mes = date(anio, mes, 1)
    ultimo_dia_mes = date(anio, mes, calendar.monthrange(anio, mes)[1])

    common, models, uid, password, db = connect_to_odoo()
    if common is None:
        return models, uid

    try:
        orders = models.execute_kw(
            db, uid, password, 'pos.order', 'search_read',
            [['date_order', '>=', f"{primer_dia_mes} 00:00:00"],
             ['date_order', '<=', f"{ultimo_dia_mes} 23:59:59"],
             ['state', 'in', ['done', 'registered', 'paid', 'invoiced']]],
            {'fields': ['config_id', 'x_studio_float_field_1u1_1irfgb3un']}
        )

        kilos_por_sucursal_mensual = {}
        for order in orders:
            nombre_sucursal = re.sub(r'\s*\(.*\)', '', order['config_id'][1]).strip()
            total_kilos = order.get('x_studio_float_field_1u1_1irfgb3un', 0.0)

            if total_kilos > 0:
                kilos_por_sucursal_mensual[nombre_sucursal] = kilos_por_sucursal_mensual.get(nombre_sucursal, 0.0) + total_kilos
        
        resultado_mensual = [{'mes': mes, 'anio': anio, 'sucursal': sucursal, 'kilos_total_mes': kilos} for sucursal, kilos in kilos_por_sucursal_mensual.items()]
        return jsonify(resultado_mensual)
    except xmlrpc.client.Fault as e:
        # Aquí capturamos la traza de Odoo para obtener el error completo
        return f"Error al procesar la solicitud mensual desde Odoo: {e.args}", 500
    except Exception as e:
        return f"Error al procesar la solicitud mensual desde Odoo: {e}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

