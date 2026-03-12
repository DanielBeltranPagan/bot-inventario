import os
import discord
from discord import ui
from discord.ext import commands
from pymongo import MongoClient
from threading import Thread
from flask import Flask
from datetime import datetime

# --- CONFIGURACIÓN (SIN DINERO) ---
CATEGORIAS = {
    "ARMAS": ["Mazo", "Bate De Béisbol Con Pinchos", "Palo De Golf", "Navaja Automática", "Machete", "Cuchillo", "Bate De Béisbol", "Palanca", "Martillo", "Hacha", "Pistola B92", "Pistola P2K", "Munición Pistola P2K", "Munición Pistola B92", "R700", "Munición R700"],
    "DROGAS": ["Cogollos Secos", "Porro", "Bolsa Con Polvitos", "Semilla Genérica", "Seed Pouch", "Bolsa Agrícola", "Semillas De Lima", "Semilla De Coca", "Marihuana Empaquetada"],
    "EQUIPAMIENTO": ["Respirador", "Binoculares", "Ganzúa", "Tablet", "Jeringa", "Dispositivo Multifuncion", "Pala De Jardín", "Chaleco Táctico", "Placas", "Bridas"],
    "OTROS": ["Cartera", "Llavero", "Billetera Luc", "Taco De Billar", "Vaso De Refresco", "Radio Básica", "Teléfono", "Contenedor De Gominolas", "Bote De Pastillas", "Pendrive Usb", "Pendrive Rojo", "Pendrive Carreras", "Pendrive Pistas", "Papel Absorbente", "Aceite De Coco", "Paquete De Puros", "Bolsa Negra", "Botiquín De Primeros Auxilios", "Lima", "Film De Cocina", "Papel De Fumar", "Paquete De Cigarrillos", "Bloc De Notas", "Cartera De Tarjetas", "Cartera De Documentos", "Caja De Cerveza", "Bidón De Gasolina", "Tarjeta Sd"]
}

LUGARES = {
    "SEDE": ["ESTANTERIA 1", "ESTANTERIA 2", "ESTANTERIA 3"],
    "VEHICULOS": ["BURRITO 1", "BURRITO 2"]
}

client = MongoClient(os.getenv("MONGO_URI"))
db = client['InventarioGTA']
items_col = db['items']
logs_col = db['logs']

app = Flask('')
@app.route('/')
def home(): return "Bot Online"
def run_flask(): app.run(host='0.0.0.0', port=8080)

def generar_embed_inventario():
    embed = discord.Embed(title="📦 ALMACÉN DE LA FACCIÓN", color=discord.Color.blue())
    items = list(items_col.find())
    if not items: 
        embed.description = "El almacén está vacío."
    else:
        emojis_zona = {"SEDE": "🏠", "VEHICULOS": "🚗"}
        for zona, sitios in LUGARES.items():
            texto_zona = "\n" 
            zona_tiene_objetos = False
            for sitio in sitios:
                objs = [i for i in items if i['lugar'] == sitio]
                if objs:
                    zona_tiene_objetos = True
                    texto_zona += f"**{sitio.title()}**\n"
                    for i in objs:
                        texto_zona += f"• {i['objeto'].title()}: **{i['cantidad']}x**\n"
                    texto_zona += "\n" 
            if zona_tiene_objetos:
                embed.add_field(name=f"{emojis_zona.get(zona, '📦')} {zona}", value=texto_zona.strip() + "\n\u200b", inline=False)
    return embed

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

class PanelControl(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📥 DEPOSITAR", style=discord.ButtonStyle.success)
    async def depositar(self, interaction, button): await self.elegir_zona(interaction, "Depositar")
    
    @ui.button(label="📤 RETIRAR", style=discord.ButtonStyle.danger)
    async def retirar(self, interaction, button): await self.elegir_zona(interaction, "Retirar")

    async def elegir_zona(self, interaction, accion):
        view = ui.View()
        for zona in LUGARES.keys():
            btn = ui.Button(label=zona, style=discord.ButtonStyle.primary)
            btn.callback = self.crear_zona_cb(zona, accion)
            view.add_item(btn)
        view.add_item(self.btn_cancelar())
        await interaction.response.edit_message(content=None, embed=generar_embed_inventario(), view=view)

    def crear_zona_cb(self, zona, accion):
        async def cb(it):
            view = ui.View()
            select = ui.Select(placeholder="Elegir sitio...", options=[discord.SelectOption(label=s) for s in LUGARES[zona]])
            async def sel_cb(it_sitio):
                lugar = select.values[0]
                if accion == "Retirar":
                    items_en_lugar = list(items_col.find({"lugar": lugar}))
                    if not items_en_lugar: return await it_sitio.response.send_message("❌ Sitio vacío.", ephemeral=True, delete_after=3)
                    view_obj = ui.View()
                    select_obj = ui.Select(placeholder="¿Qué retirar?", options=[discord.SelectOption(label=i['objeto']) for i in items_en_lugar])
                    select_obj.callback = lambda it_o: it_o.response.send_modal(CantidadModal(accion, lugar, select_obj.values[0]))
                    view_obj.add_item(select_obj); view_obj.add_item(self.btn_cancelar())
                    await it_sitio.response.edit_message(content=f"📍 {lugar}. Selecciona objeto:", view=view_obj)
                else: await self.mostrar_categorias(it_sitio, lugar, accion)
            select.callback = sel_cb
            view.add_item(select); view.add_item(self.btn_cancelar())
            await it.response.edit_message(content=f"📍 Has elegido **{zona}**. Selecciona sitio:", view=view)
        return cb

    async def mostrar_categorias(self, it, lugar, accion):
        view = ui.View()
        for cat in CATEGORIAS:
            btn = ui.Button(label=cat, style=discord.ButtonStyle.secondary)
            btn.callback = lambda it_cat, c=cat: self.mostrar_objetos(it_cat, c, lugar, accion)
            view.add_item(btn)
        view.add_item(self.btn_cancelar())
        await it.response.edit_message(content=f"📍 {lugar}. Elige categoría:", view=view)

    async def mostrar_objetos(self, it, cat, lugar, accion):
        view = ui.View()
        select = ui.Select(placeholder="Selecciona objeto...", options=[discord.SelectOption(label=obj) for obj in CATEGORIAS[cat]])
        select.callback = lambda it_obj: it_obj.response.send_modal(CantidadModal(accion, lugar, select.values[0]))
        view.add_item(select); view.add_item(self.btn_cancelar())
        await it.response.edit_message(content=f"📍 {lugar} > {cat}. ¿Qué objeto?", view=view)

    def btn_cancelar(self):
        btn = ui.Button(label="❌ VOLVER", style=discord.ButtonStyle.secondary)
        btn.callback = lambda it: it.response.edit_message(content=None, embed=generar_embed_inventario(), view=PanelControl())
        return btn

class CantidadModal(ui.Modal, title="Cantidad"):
    input_cant = ui.TextInput(label="Cantidad", placeholder="Ej: 1")
    def __init__(self, accion, lugar, objeto):
        super().__init__()
        self.accion, self.lugar, self.objeto = accion, lugar, objeto

    async def on_submit(self, interaction):
        try:
            cant = int(self.input_cant.value)
            filtro = {"objeto": self.objeto, "lugar": self.lugar}
            if self.accion == "Retirar":
                ex = items_col.find_one(filtro)
                if not ex or ex['cantidad'] < cant: return await interaction.response.send_message("❌ Insuficiente.", ephemeral=True, delete_after=3)
                if ex['cantidad'] == cant: items_col.delete_one(filtro)
                else: items_col.update_one(filtro, {"$inc": {"cantidad": -cant}})
            else: items_col.update_one(filtro, {"$inc": {"cantidad": cant}}, upsert=True)
            
            logs_col.insert_one({
                "usuario": str(interaction.user), "accion": self.accion.upper(), "objeto": self.objeto,
                "cantidad": cant, "lugar": self.lugar, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            await interaction.response.send_message(f"✅ {self.accion} exitoso.", ephemeral=True, delete_after=2)
            await interaction.message.edit(content=None, embed=generar_embed_inventario(), view=PanelControl())
        except ValueError:
            await interaction.response.send_message("❌ Introduce un número válido.", ephemeral=True, delete_after=3)

@bot.command()
async def inventario(ctx):
    await ctx.message.delete() 
    await ctx.send(embed=generar_embed_inventario(), view=PanelControl())

Thread(target=run_flask).start()
bot.run(os.getenv("DISCORD_TOKEN"))
