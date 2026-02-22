from flask import Flask, request, jsonify
from flask_cors import CORS
import whisper
import re
import json
from datetime import datetime
import tempfile
import os
from collections import Counter

app = Flask(__name__)
CORS(app)

# Cargar modelo Whisper (opcional, para audio)
print("🎤 Cargando modelo Whisper...")
try:
    whisper_model = whisper.load_model("small", device="cpu", download_root="./whisper_models")
except:
    print("⚠️ Whisper no disponible, solo modo texto")
    whisper_model = None

# Cargar el menú de El Gustito
def cargar_menu_el_gustito():
    try:
        with open('menu_el_gustito.txt', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        menu = """TAQUERÍA EL GUSTITO - PÁNUCO, VER.

TACOS:
- Taco al Pastor: Carne al pastor, piña, cebolla, cilantro - $25
- Taco de Suadero: Suadero, cebolla, cilantro, salsa verde - $28
- Taco de Tripa: Tripa crujiente, cebolla, cilantro, salsa roja - $30
- Taco de Longaniza: Longaniza, cebolla, cilantro, salsa - $25
- Taco Campechano: Pastor + Suadero, cebolla, cilantro - $30

ESPECIALIDADES:
- Gringa de Pastor: Harina, pastor, queso Oaxaca, piña - $45
- Gringa de Suadero: Harina, suadero, queso Oaxaca - $45
- Quesadilla: Queso Oaxaca, tortilla de harina - $35
- Volcán: Tostada con queso fundido y pastor - $35

BEBIDAS:
- Refresco: Coca-Cola, Sprite, Fanta, Sidral - $25
- Agua natural/jamaica/horchata - $20
- Cerveza: Indio, XX, Corona, Modelo - $45
- Michelada preparada - $65

POSTRES:
- Plátano frito con crema - $40
- Fresas con crema - $45
- Arroz con leche - $30

INFORMACIÓN:
- Horario: Lunes a Domingo de 6:00 PM a 2:00 AM
- Domicilio: $50 envío (gratis > $300)
- Teléfono: +52 833 289 2730
- Dirección: Benito Juárez #123, Pánuco Centro"""
        
        with open('menu_el_gustito.txt', 'w', encoding='utf-8') as f:
            f.write(menu)
        return menu

menu = cargar_menu_el_gustito()
print("📋 Menú de El Gustito cargado correctamente")

class MeseroElGustito:
    def __init__(self):
        self.orden_actual = []
        self.total = 0
        self.items_unicos_actuales = []
        self.ultima_pregunta = ""  # Para contexto
        print("🤵 Mesero de El Gustito listo para atender")
    
    def _normalizar_texto(self, texto):
        """Normaliza el texto del usuario: minúsculas, sin acentos, sin signos"""
        texto = texto.lower().strip()
        # Reemplazar acentos comunes
        reemplazos = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
            'ü': 'u', 'ñ': 'n', '¿': '', '¡': '', '?': '', '!': ''
        }
        for acento, sin_acento in reemplazos.items():
            texto = texto.replace(acento, sin_acento)
        return texto
    
    def _detectar_intencion(self, texto):
        """Detecta la intención del usuario basado en palabras clave"""
        texto_norm = self._normalizar_texto(texto)
        
        # 1. SALUDOS
        if any(p in texto_norm for p in ['hola', 'buenas', 'que tal', 'q tal', 'buen dia', 'buenas tardes', 'buenas noches', 'como estas', 'ke tal']):
            return 'saludo'
        
        # 2. HORARIO
        if any(p in texto_norm for p in ['horario', 'abren', 'cierran', 'hora cierran', 'a q hora', 'abierto', 'cerrado', 'atienden']):
            return 'horario'
        
        # 3. DOMICILIO / ENVÍO
        if any(p in texto_norm for p in ['domicilio', 'envio', 'delivery', 'mandan', 'llevan', 'a domicilio', 'reparten', 'llevar']):
            return 'domicilio'
        
        # 4. TELÉFONO / CONTACTO
        if any(p in texto_norm for p in ['telefono', 'whatsapp', 'contacto', 'numero', 'whats', 'cel', 'celular']):
            return 'telefono'
        
        # 5. DIRECCIÓN / UBICACIÓN
        if any(p in texto_norm for p in ['direccion', 'donde', 'ubicacion', 'como llegar', 'mapa', 'estan en']):
            return 'direccion'
        
        # 6. SALSAS
        if any(p in texto_norm for p in ['salsa', 'salsas', 'pica', 'picante', 'verde', 'roja', 'habanero']):
            return 'salsas'
        
        # 7. PRECIOS / CUÁNTO CUESTA
        if any(p in texto_norm for p in ['precio', 'cuanto cuesta', 'cuanto vale', 'cuesta', 'costo', 'precios', 'q precio', 'a como']):
            return 'precios'
        
        # 8. MENÚ / QUÉ HAY
        if any(p in texto_norm for p in ['menu', 'carta', 'que hay', 'que tienen', 'que venden', 'productos', 'comida']):
            return 'menu'
        
        # 9. RECOMENDACIONES
        if any(p in texto_norm for p in ['recomienda', 'recomiendas', 'que pides', 'que es lo mejor', 'mas rico', 'especialidad', 'sugieres']):
            return 'recomendacion'
        
        # 10. PROMOCIONES / OFERTAS
        if any(p in texto_norm for p in ['promo', 'oferta', 'descuento', 'combo', 'especial', 'barato']):
            return 'promocion'
        
        # 11. GRACIAS
        if any(p in texto_norm for p in ['gracias', 'thanks', 'grax', 'grac']):
            return 'gracias'
        
        # 12. DESPEDIDA
        if any(p in texto_norm for p in ['adios', 'bye', 'nos vemos', 'luego', 'despues', 'hasta luego']):
            return 'despedida'
        
        # 13. VER ORDEN
        if any(p in texto_norm for p in ['ver orden', 'mi orden', 'que llevo', 'como voy', 'total', 'cuanto llevo']):
            return 'ver_orden'
        
        # 14. LIMPIAR ORDEN
        if any(p in texto_norm for p in ['limpiar', 'borrar todo', 'cancelar orden', 'empezar de nuevo']):
            return 'limpiar'
        
        # 15. PAGAR
        if any(p in texto_norm for p in ['pagar', 'cuenta', 'la cuenta', 'pago']):
            return 'pagar'
        
        # 16. BUSCAR PRODUCTO ESPECÍFICO
        productos = ['pastor', 'suadero', 'tripa', 'longaniza', 'campechano', 'gringa', 'quesadilla', 
                     'volcan', 'refresco', 'cerveza', 'michelada', 'platano', 'fresas', 'arroz']
        for prod in productos:
            if prod in texto_norm:
                return f'producto_{prod}'
        
        return 'no_entiendo'
    
    def procesar_pregunta(self, texto):
        """Procesa la pregunta del usuario y devuelve respuesta natural"""
        
        intencion = self._detectar_intencion(texto)
        
        # ===== RESPUESTAS NATURALES =====
        
        if intencion == 'saludo':
            return "¡Hola! Qué gusto verte. Soy Toño, tu mesero de El Gustito. ¿Qué se te antoja? Unos tacos, una gringa, lo que gustes."
        
        elif intencion == 'horario':
            return "Abrimos de lunes a domingo de 6 de la tarde a 2 de la mañana. O sea, llegas tarde noche y todavía alcanzas unos tacos bien preparados. ¿A qué hora piensas venir?"
        
        elif intencion == 'domicilio':
            return "Claro que sí, mandamos a domicilio. El envío cuesta 50 pesitos, pero si pides más de 300 pesos, te lo llevamos gratis. Nuestros repartidores son bien rápidos. ¿Qué te gustaría pedir?"
        
        elif intencion == 'telefono':
            return "Puedes marcarnos al 833 289 2730. También tenemos WhatsApp, así que si quieres mandar mensaje, con confianza. ¿Necesitas algo en especial?"
        
        elif intencion == 'direccion':
            return "Estamos en la calle Benito Juárez #123, en el centro de Pánuco, a una cuadrita del parque. Llegas y nos ves, no tiene pierde. ¿Vienes para acá o prefieres domicilio?"
        
        elif intencion == 'salsas':
            return "Mira, tenemos tres salsas: la verde está suavecita (para los que no les gusta tanto el picante), la roja sí pica pero rico, y la de habanero es pa' los valientes. Todas las preparamos diario. ¿Cuál pruebas?"
        
        elif intencion == 'precios':
            return self._responder_precios(texto)
        
        elif intencion == 'menu':
            return self.mostrar_menu_completo()
        
        elif intencion == 'recomendacion':
            return "Mira, lo que más pide la raza son los tacos al pastor y de suadero, bien jugositos con su piñita. También las gringas de pastor con queso derretido, ufff, están de otro nivel. Si vienes con hambre, el Combo Taco Loco (3 tacos + refresco) está en 90 pesos. ¿Te animas?"
        
        elif intencion == 'promocion':
            return "Hoy tenemos el Combo Taco Loco: 3 tacos de los que quieras más un refresco en 90 pesos. Sale más barato que pedir por separado. También el Combo Familiar: 10 tacos + 4 refrescos en 250 pesos. ¿Cuál te provoca?"
        
        elif intencion == 'gracias':
            return "¡A ti por confiar en El Gustito! Aquí andamos para servirte. Vuelve cuando quieras, las puertas están abiertas."
        
        elif intencion == 'despedida':
            return "¡Ahí nos vemos! Que te vaya bien, y no olvides que aquí tienes tu taquería de confianza en Pánuco. ¡Hasta luego!"
        
        elif intencion == 'ver_orden':
            return self.mostrar_orden_detallada()
        
        elif intencion == 'limpiar':
            self.orden_actual = []
            self.total = 0
            return "🧹 Listo, limpiamos tu orden. ¿Qué se te antoja ahora?"
        
        elif intencion == 'pagar':
            if self.total == 0:
                return "No tienes nada que pagar aún. ¿Qué te gustaría probar?"
            return f"Tu total es ${self.total}. Cuando quieras pagar, haz clic en el botón 'Pagar' de la pantalla y elige transferencia o efectivo. Si eliges transferencia, te mandamos los datos por WhatsApp."
        
        elif intencion.startswith('producto_'):
            producto = intencion.replace('producto_', '')
            return self._responder_producto(producto, texto)
        
        else:
            # Si no entiende, pero detecta palabras de comida, intenta tomar orden
            if self._detectar_posible_orden(texto):
                return self.tomar_orden(texto)
            
            return self._respuesta_no_entiende()
    
    def _responder_precios(self, texto):
        """Responde sobre precios de manera específica según lo que pregunten"""
        texto_norm = self._normalizar_texto(texto)
        
        if 'taco' in texto_norm or 'pastor' in texto_norm or 'suadero' in texto_norm:
            return "Los tacos van de 25 a 30 pesos: Pastor $25, Suadero $28, Tripa $30, Longaniza $25, Campechano $30. Todos bien servidos."
        
        elif 'gringa' in texto_norm:
            return "Las gringas están en $45. Las tenemos de pastor o de suadero, con harto queso derretido."
        
        elif 'bebida' in texto_norm or 'refresco' in texto_norm or 'cerveza' in texto_norm:
            return "Las bebidas: Refresco $25, Agua $20, Cerveza $45, Michelada $65."
        
        elif 'postre' in texto_norm or 'platano' in texto_norm or 'fresas' in texto_norm:
            return "Los postres: Plátano frito $40, Fresas con crema $45, Arroz con leche $30."
        
        elif 'combo' in texto_norm:
            return "Los combos: Taco Loco (3 tacos + refri) $90, Gringa Express (gringa + refri) $65, Familiar (10 tacos + 4 refris) $250."
        
        else:
            return "Nuestros precios: Tacos $25-30, Gringas $45, Refrescos $25, Cerveza $45, Combos desde $65. ¿Qué te gustaría saber en específico?"
    
    def _responder_producto(self, producto, texto_original):
        """Responde sobre un producto específico"""
        if producto == 'pastor':
            return "El taco al pastor es de los más pedidos. Lleva carne de pastor con su piñita, cebolla y cilantro. Está en $25. ¿Te apunto uno? O unos cuantos."
        elif producto == 'suadero':
            return "El suadero es bien suavecito, se deshace en la boca. Con cebolla y cilantro, está en $28. ¿Cuántos te provan?"
        elif producto == 'tripa':
            return "La tripa la preparamos bien crujiente, como debe ser. Con su salsita roja, está en $30. ¿Te gusta la tripa?"
        elif producto == 'gringa':
            return "La gringa es tortilla de harina con pastor o suadero, queso Oaxaca derretido y piña. Está en $45 y es bien completa. ¿La pruebas?"
        elif producto == 'refresco':
            return "Tenemos refresco de $25: Coca-Cola, Sprite, Fanta, Sidral. ¿Cuál quieres?"
        elif producto == 'cerveza':
            return "Cerveza $45: Indio, XX, Corona, Modelo. ¿Cuál te gusta?"
        else:
            return f"Sí tenemos {producto}. ¿Quieres que te lo apunte?"
    
    def _detectar_posible_orden(self, texto):
        """Detecta si el usuario está tratando de ordenar algo"""
        texto_norm = self._normalizar_texto(texto)
        palabras_orden = ['quiero', 'dame', 'me das', 'una', 'un', 'unas', 'unos', 'orden', 'pedir', 'llevar', 'de']
        return any(p in texto_norm for p in palabras_orden)
    
    def _respuesta_no_entiende(self):
        """Respuesta amable cuando no entiende"""
        return "Oye, no te entendí bien. ¿Me puedes decir otra vez? Puedes preguntarme por:\n• Horario (¿a qué hora abren?)\n• Domicilio (¿mandan a domicilio?)\n• Menú (¿qué tienen?)\n• Precios (¿cuánto cuesta?)\n• O decirme qué tacos quieres (pastor, suadero, tripa...)"
    
    def tomar_orden(self, texto):
        """Toma la orden del usuario"""
        texto_norm = self._normalizar_texto(texto)
        
        # Mapeo de palabras a items del menú
        items_menu = {
            'pastor': ('Taco al Pastor', 25),
            'suadero': ('Taco de Suadero', 28),
            'tripa': ('Taco de Tripa', 30),
            'longaniza': ('Taco de Longaniza', 25),
            'campechano': ('Taco Campechano', 30),
            'gringa': ('Gringa', 45),
            'quesadilla': ('Quesadilla', 35),
            'volcan': ('Volcán', 35),
            'refresco': ('Refresco', 25),
            'coca': ('Refresco', 25),
            'sprite': ('Refresco', 25),
            'fanta': ('Refresco', 25),
            'cerveza': ('Cerveza', 45),
            'indio': ('Cerveza', 45),
            'xx': ('Cerveza', 45),
            'corona': ('Cerveza', 45),
            'modelo': ('Cerveza', 45),
            'michelada': ('Michelada', 65),
            'platano': ('Plátano frito', 40),
            'fresas': ('Fresas con crema', 45),
            'arroz': ('Arroz con leche', 30)
        }
        
        items_encontrados = []
        
        # Buscar cantidades (ej: "3 pastor")
        match = re.search(r'(\d+)\s*(pastor|suadero|tripa|gringa|taco|tacos)', texto_norm)
        cantidad_global = int(match.group(1)) if match else 1
        
        for palabra, (nombre, precio) in items_menu.items():
            if palabra in texto_norm:
                items_encontrados.append((nombre, precio))
        
        if items_encontrados:
            for nombre, precio in items_encontrados:
                for i in range(cantidad_global):
                    self.orden_actual.append(nombre)
                    self.total += precio
            
            if len(items_encontrados) == 1:
                if cantidad_global > 1:
                    return f"Listo, te apunto {cantidad_global} {nombre}. Llevas ${self.total}. ¿Algo más?"
                else:
                    return f"¡Perfecto! Agregué {nombre} a tu orden. Llevas ${self.total}. ¿Qué más te provoca?"
            else:
                return f"✅ Agregué {len(items_encontrados)} items a tu orden. Llevas ${self.total}"
        
        return None
    
    def mostrar_menu_completo(self):
        return """📋 **MENÚ DE EL GUSTITO**

🌮 **TACOS** (por pieza):
• Pastor: $25 (con piñita)
• Suadero: $28 (bien suavecito)
• Tripa: $30 (crujiente)
• Longaniza: $25
• Campechano: $30 (pastor + suadero)

🫔 **ESPECIALIDADES**:
• Gringa (pastor/suadero): $45 (con queso derretido)
• Quesadilla: $35
• Volcán: $35

🥤 **BEBIDAS**:
• Refresco: $25
• Agua: $20 (jamaica, horchata)
• Cerveza: $45
• Michelada: $65

🍨 **POSTRES**:
• Plátano frito: $40
• Fresas con crema: $45

🍱 **COMBOS**:
• Taco Loco (3 tacos + refri): $90
• Familiar (10 tacos + 4 refris): $250

¿Qué se te antoja? 😋"""
    
    def mostrar_orden_detallada(self):
        if not self.orden_actual:
            return "Tu orden está vacía. ¿Qué te gustaría probar?"
        
        contador = Counter(self.orden_actual)
        orden_detalle = []
        index = 1
        items_unicos = []
        
        for item, cantidad in contador.items():
            # Buscar precio
            precio = 0
            if 'Pastor' in item: precio = 25
            elif 'Suadero' in item: precio = 28
            elif 'Tripa' in item: precio = 30
            elif 'Longaniza' in item: precio = 25
            elif 'Campechano' in item: precio = 30
            elif 'Gringa' in item: precio = 45
            elif 'Quesadilla' in item: precio = 35
            elif 'Volcán' in item: precio = 35
            elif 'Refresco' in item: precio = 25
            elif 'Cerveza' in item: precio = 45
            elif 'Michelada' in item: precio = 65
            elif 'Plátano' in item: precio = 40
            elif 'Fresas' in item: precio = 45
            
            orden_detalle.append(f"{index}. {cantidad} {item}{'s' if cantidad > 1 else ''} - ${precio * cantidad}")
            items_unicos.append((item, cantidad))
            index += 1
        
        self.items_unicos_actuales = items_unicos
        orden_detalle.append(f"\n💰 Total: ${self.total}")
        return "\n".join(orden_detalle)

# Inicializar mesero
mesero = MeseroElGustito()

# ============================================
# API ENDPOINTS
# ============================================

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "restaurante": "Taquería El Gustito - Pánuco, Ver.",
        "estado": "🟢 Atendiendo",
        "mesero": "Toño está listo para atenderte"
    })

@app.route('/hablar', methods=['POST'])
def hablar():
    if request.is_json:
        data = request.json
        mensaje = data.get('mensaje', '')
        print(f"📝 Cliente: {mensaje}")
        
        # Primero intentar tomar orden
        respuesta_orden = mesero.tomar_orden(mensaje)
        if respuesta_orden:
            respuesta = respuesta_orden
        else:
            respuesta = mesero.procesar_pregunta(mensaje)
        
        return jsonify({
            "cliente": mensaje,
            "mesero": respuesta,
            "orden_actual": mesero.orden_actual,
            "total": mesero.total
        })
    return jsonify({"error": "Formato no válido"}), 400

@app.route('/orden', methods=['GET'])
def ver_orden():
    return jsonify({
        "orden": mesero.orden_actual,
        "total": mesero.total,
        "mensaje": mesero.mostrar_orden_detallada()
    })

@app.route('/reset', methods=['POST'])
def reset_orden():
    mesero.orden_actual = []
    mesero.total = 0
    return jsonify({"mensaje": "🧹 Orden limpiada"})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🌮 TAQUERÍA EL GUSTITO - MESERO IA")
    print("="*60)
    print("📍 API: http://localhost:5000")
    print("🤵 Toño está listo para atender")
    print("💬 Prueba: 'hola', 'horario', 'domicilio', 'precios', 'quiero 3 pastor'")
    print("="*60)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)