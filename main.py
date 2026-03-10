import os
import discord
from discord import ui
from discord.ext import commands
from pymongo import MongoClient
from threading import Thread
from flask import Flask

# --- CONFIGURACIÓN ---
CATEGORIAS = {
    "ARMAS": ["Mazo", "Bate de béisbol con pinchos", "Palo de golf", "Navaja automática", "Machete", "Taco de billar", "Cuchillo"],
    "DROGAS": ["Papel de fumar", "Cogollos secos", "Porro", "Bolsa con polvillos", "Semillas genéricas", "Seed Pouch", "Ácido", "Bote de pastillas"],
    "OTROS": ["USB para impresora 3D", "Dispositivo Multifuncion", "Tarjeta SD", "Radio bàsica", "Ganzúa", "Contenedor de gominolas", "Vaso de refresco", "Jeringa", "Teléfono", "Bidón de gasolina", "Bolsa agrícola", "Respirador", "Binoculares"]
}

LUGARES = {
    "SEDE": ["ESTANTERIA 1", "ESTANTERIA 2", "ESTANTERIA 3", "CAJA FUERTE", "CAJA MUNICIONES", "CAJA ARMAS", "CAJA DINERO"],
    "VEHICULOS": ["BURRITO 1", "BURRITO 2"]
}

client = MongoClient(os.getenv("MONGO_URI"))
db = client['InventarioGTA']
items_col = db['items']

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot Online"
def run(): app.run(host='0.0.0.0', port=8080)

# --- LÓGICA DE EMBED ---
def generar_embed_inventario():
    embed = discord.Embed(title="📦 INVENTARIO EN TIEMPO REAL", color=discord.Color.blue())
    items = list(items_col.find())
    if not items:
        embed.description = "El almacén está vacío."
    else:
        for zona, sitios in LUGARES.items():
            texto_zona = ""
            for sitio in sitios:
                objs = [i for i in items if i['lugar'] == sitio]
                if objs:
                    texto_zona += f"**📍 {sitio}:**\n"
                    # Lista hacia abajo
                    for i in objs:
                        texto_zona += f"   • {i['objeto'].title()}: **{i['cantidad']}x**\n"
                    texto_zona += "\n"
            if texto_zona:
                embed.add_field(name=f"--- {zona} ---", value=texto_zona, inline=False)
    return embed

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# --- VISTA DE BOTONES ---
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
        await interaction.response.edit_message(content=f"⚙️ ¿Qué quieres {accion}?", embed=None, view=view)

    def crear_zona_cb(self, zona, accion):
        async def cb(it):
            view = ui.View()
            select = ui.Select(placeholder=f"Elegir sitio en {zona}...", options=[discord.SelectOption(label=s) for s in LUGARES[zona]])
            async def sel_cb(it_sitio):
                await self.mostrar_categorias(it_sitio, select.values[0], accion)
            select.callback = sel_cb
            view.add_item(select)
            await it.response.edit_message(content=f"📍 Has elegido **{zona}**. Selecciona el sitio:", view=view)
        return cb

    async def mostrar_categorias(self, it, lugar, accion):
        view = ui.View()
        for cat in CATEGORIAS:
            btn = ui.Button(label=cat, style=discord.ButtonStyle.secondary)
            btn.callback = lambda it_cat, c=cat: self.mostrar_objetos(it_cat, c, lugar, accion)
            view.add_item(btn)
        await it.response.edit_message(content=f"📍 **{lugar}**. Elige categoría:", view=view)

    async def mostrar_objetos(self, it, cat, lugar, accion):
        view = ui.View()
        select = ui.Select(placeholder="Selecciona objeto...", options=[discord.SelectOption(label=obj) for obj in CATEGORIAS[cat]])
        async def obj_cb(it_obj):
            await it_obj.response.send_modal(CantidadModal(accion, lugar, select.values[0]))
        select.callback = obj_cb
        view.add_item(select)
        await it.response.edit_message(content=f"📍 {lugar} > {cat}. ¿Qué objeto?", view=view)

class CantidadModal(ui.Modal, title="Cantidad"):
    input_cant = ui.TextInput(label="Cantidad", placeholder="Ej: 1")
    def __init__(self, accion, lugar, objeto):
        super().__init__()
        self.accion, self.lugar, self.objeto = accion, lugar, objeto

    async def on_submit(self, interaction):
        cant = int(self.input_cant.value)
        filtro = {"objeto": self.objeto, "lugar": self.lugar}
        if self.accion == "Retirar":
            ex = items_col.find_one(filtro)
            if not ex or ex['cantidad'] < cant: return await interaction.response.send_message("❌ Insuficiente.", ephemeral=True)
            if ex['cantidad'] == cant: items_col.delete_one(filtro)
            else: items_col.update_one(filtro, {"$inc": {"cantidad": -cant}})
        else:
            items_col.update_one(filtro, {"$inc": {"cantidad": cant}}, upsert=True)
        
        # Volvemos al panel principal con el inventario actualizado
        await interaction.response.edit_message(content=None, embed=generar_embed_inventario(), view=PanelControl())

@bot.tree.command(name="panel_inventario")
async def panel_inventario(interaction):
    await interaction.response.send_message(embed=generar_embed_inventario(), view=PanelControl())

Thread(target=run).start()
bot.run(os.getenv("DISCORD_TOKEN"))
