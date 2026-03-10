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
def run_flask(): app.run(host='0.0.0.0', port=8080)

# --- LÓGICA DE EMBED MEJORADA ---
def generar_embed_inventario():
    embed = discord.Embed(title="📦 ALMACÉN DE LA FACCIÓN", color=discord.Color.blue())
    items = list(items_col.find())
    if not items: 
        embed.description = "El almacén está vacío."
    else:
        emojis_zona = {"SEDE": "🏠", "VEHICULOS": "🚗"}
        for zona, sitios in LUGARES.items():
            texto = ""
            for sitio in sitios:
                objs = [i for i in items if i['lugar'] == sitio]
                if objs:
                    texto += f"**📍 {sitio.title()}:**\n" 
                    texto += "\n".join([f"  • {i['objeto'].title()}: **{i['cantidad']}x**" for i in objs]) + "\n\n"
            if texto: 
                embed.add_field(name=f"{emojis_zona.get(zona, '📦')} {zona}", value=texto, inline=False)
                embed.add_field(name="\u200b", value="\u200b", inline=False) 
    return embed

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# --- VISTA CENTRAL ---
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
        await interaction.response.edit_message(content=f"⚙️ ¿Qué zona para {accion}?", embed=generar_embed_inventario(), view=view)

    def crear_zona_cb(self, zona, accion):
        async def cb(it):
            view = ui.View()
            select = ui.Select(placeholder="Elegir sitio...", options=[discord.SelectOption(label=s) for s in LUGARES[zona]])
            async def sel_cb(it_sitio):
                lugar = select.values[0]
                if accion == "Retirar":
                    items_en_lugar = list(items_col.find({"lugar": lugar}))
                    if not items_en_lugar: return await it_sitio.response.edit_message(content="❌ Sitio vacío.", view=PanelControl())
                    view_obj = ui.View()
                    select_obj = ui.Select(placeholder="Selecciona objeto...", options=[discord.SelectOption(label=i['objeto']) for i in items_en_lugar])
                    select_obj.callback = lambda it_o: it_o.response.send_modal(CantidadModal(accion, lugar, select_obj.values[0]))
                    view_obj.add_item(select_obj); view_obj.add_item(self.btn_cancelar())
                    await it_sitio.response.edit_message(content=f"📍 {lugar}. ¿Qué retirar?", view=view_obj)
                else: await self.mostrar_categorias(it_sitio, lugar, accion)
            select.callback = sel_cb
            view.add_item(select); view.add_item(self.btn_cancelar())
            await it.response.edit_message(content=f"📍 Elegiste **{zona}**. Selecciona sitio:", view=view)
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
        btn.callback = lambda it: it.response.edit_message(content="📦 **PANEL PRINCIPAL**", embed=generar_embed_inventario(), view=PanelControl())
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
                if not ex or ex['cantidad'] < cant: return await interaction.response.send_message("❌ Insuficiente.", ephemeral=True)
                if ex['cantidad'] == cant: items_col.delete_one(filtro)
                else: items_col.update_one(filtro, {"$inc": {"cantidad": -cant}})
            else: items_col.update_one(filtro, {"$inc": {"cantidad": cant}}, upsert=True)
            await interaction.response.send_message(f"✅ {self.accion} exitoso.", ephemeral=True, delete_after=2)
            await interaction.message.edit(content="📦 **PANEL PRINCIPAL**", embed=generar_embed_inventario(), view=PanelControl())
        except ValueError:
            await interaction.response.send_message("❌ Introduce un número válido.", ephemeral=True)

@bot.tree.command(name="panel_inventario")
async def panel_inventario(interaction):
    await interaction.response.send_message(embed=generar_embed_inventario(), view=PanelControl())



Thread(target=run_flask).start()
bot.run(os.getenv("DISCORD_TOKEN"))
