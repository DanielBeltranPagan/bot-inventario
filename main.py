import os
import discord
from discord import ui
from discord.ext import commands
from pymongo import MongoClient
from datetime import datetime
from flask import Flask
from threading import Thread

# --- CONFIGURACIÓN ---
CATEGORIAS = {
    "Armas": ["Mazo", "Bate de béisbol con pinchos", "Palo de golf", "Navaja automática", "Machete", "Taco de billar", "Cuchillo"],
    "Drogas": ["Papel de fumar", "Cogollos secos", "Porro", "Bolsa con polvillos", "Semillas genéricas", "Seed Pouch", "Ácido", "Bote de pastillas"],
    "Otros": ["USB para impresora 3D", "Dispositivo Multifuncion", "Tarjeta SD", "Radio bàsica", "Ganzúa", "Contenedor de gominolas", "Vaso de refresco", "Jeringa", "Teléfono", "Bidón de gasolina", "Bolsa agrícola", "Respirador", "Binoculares"]
}

LUGARES = {
    "SEDE": ["estanteria1", "estanteria2", "estanteria3", "caja_fuerte", "caja_municiones", "caja_armas", "caja_dinero"],
    "VEHICULOS": ["burrito1", "burrito2"]
}

# --- CONEXIÓN ---
client = MongoClient(os.getenv("MONGO_URI"))
db = client['InventarioGTA']
items_col = db['items']
logs_col = db['logs']

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot Online"
def run(): app.run(host='0.0.0.0', port=8080)

# --- LÓGICA DE ACTUALIZACIÓN ---
def generar_embed_inventario():
    embed = discord.Embed(title="📦 ALMACÉN DE FACCION", color=discord.Color.blue())
    items = list(items_col.find())
    if not items:
        embed.description = "El almacén está vacío."
    else:
        for zona, sitios in LUGARES.items():
            contenido = ""
            for sitio in sitios:
                objs = [i for i in items if i['lugar'] == sitio]
                if objs:
                    contenido += f"**{sitio}:**\n" + "\n".join([f"- {i['objeto']}: {i['cantidad']}" for i in objs]) + "\n"
            if contenido:
                embed.add_field(name=f"--- {zona} ---", value=contenido, inline=False)
    return embed

# --- BOT ---
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        self.add_view(PanelControl(self))
        await self.tree.sync()

bot = MyBot()

# --- INTERFAZ ---
class CantidadModal(ui.Modal, title="Indica la Cantidad"):
    input_cant = ui.TextInput(label="Cantidad", placeholder="Ej: 5", min_length=1, max_length=5)
    def __init__(self, accion, lugar, objeto, view_padre):
        super().__init__()
        self.accion, self.lugar, self.objeto, self.view_padre = accion, lugar, objeto, view_padre

    async def on_submit(self, interaction: discord.Interaction):
        cant = int(self.input_cant.value)
        filtro = {"objeto": self.objeto, "lugar": self.lugar}
        if self.accion == "Retirar":
            existente = items_col.find_one(filtro)
            if not existente or existente['cantidad'] < cant:
                return await interaction.response.send_message("❌ No hay suficiente.", ephemeral=True)
            if existente['cantidad'] == cant: items_col.delete_one(filtro)
            else: items_col.update_one(filtro, {"$inc": {"cantidad": -cant}})
        else:
            items_col.update_one(filtro, {"$inc": {"cantidad": cant}}, upsert=True)
        
        await interaction.response.edit_message(content="✅ Operación realizada.", view=None)
        # ACTUALIZAR EL PANEL PRINCIPAL
        await interaction.message.channel.edit(embed=generar_embed_inventario())

class PanelControl(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
    
    @ui.button(label="📥 DEPOSITAR", style=discord.ButtonStyle.success, custom_id="btn_dep")
    async def depositar(self, interaction, button): await self.mostrar_lugares(interaction, "Depositar")
    
    @ui.button(label="📤 RETIRAR", style=discord.ButtonStyle.danger, custom_id="btn_ret")
    async def retirar(self, interaction, button): await self.mostrar_lugares(interaction, "Retirar")

    async def mostrar_lugares(self, interaction, accion):
        view = ui.View()
        for zona, sitios in LUGARES.items():
            select = ui.Select(placeholder=f"Sitio en {zona}...", options=[discord.SelectOption(label=s) for s in sitios])
            async def lugar_cb(it, sel=select):
                view_cat = ui.View()
                for cat in CATEGORIAS:
                    btn = ui.Button(label=cat, style=discord.ButtonStyle.secondary)
                    btn.callback = self.crear_cat_cb(cat, sel.values[0], accion)
                    view_cat.add_item(btn)
                await it.response.edit_message(content=f"📍 {sel.values[0]} | Elige categoría:", view=view_cat)
            select.callback = lugar_cb
            view.add_item(select)
        await interaction.response.send_message("¿Dónde?:", view=view, ephemeral=True)

    def crear_cat_cb(self, cat, lugar, accion):
        async def cb(it):
            v = ui.View()
            v.add_item(SelectorObjeto(cat, lugar, accion))
            await it.response.edit_message(content=f"📍 {lugar} > {cat}. ¿Objeto?:", view=v)
        return cb

class SelectorObjeto(ui.Select):
    def __init__(self, categoria, lugar, accion):
        super().__init__(placeholder="Selecciona...", options=[discord.SelectOption(label=obj) for obj in CATEGORIAS[categoria]])
        self.lugar, self.accion = lugar, accion
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CantidadModal(self.accion, self.lugar, self.values[0], self))

@bot.tree.command(name="panel_inventario", description="Genera el panel")
async def panel_inventario(interaction):
    await interaction.response.send_message(embed=generar_embed_inventario(), view=PanelControl(bot))

Thread(target=run).start()
bot.run(os.getenv("DISCORD_TOKEN"))
