import os
import json
import httpx
import PyPDF2
from dotenv import load_dotenv
import openai
import datetime
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional




app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://webapp-rol.vercel.app"],  # tu dominio en Vercel, exactamente así, sin barra final
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



SAVES_DIR = "saves"
if not os.path.exists(SAVES_DIR):
    os.makedirs(SAVES_DIR)

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    state: Optional[Dict] = None  # Estado de la conversación para cada usuario

# ---------------------------------
# Utilidades para lógica de aventura
# ---------------------------------

def list_saves():
    return [f[:-5] for f in os.listdir(SAVES_DIR) if f.endswith(".json")]

def save_game(name, state):
    path = os.path.join(SAVES_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_game(name):
    path = os.path.join(SAVES_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def llm_chat(messages, max_tokens=100, temperature=0.7):
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    )
    return resp.choices[0].message.content

# ---------------------------------
# Flujo principal del agente
# ---------------------------------

@app.post("/chat")
def chat(request: ChatRequest):
    user_msgs = request.messages
    estado = request.state or {}  # Diccionario para llevar estado de usuario

    def response(text, prompt="", newstate=None):
        # Devuelve mensaje para el frontend, más estado si es necesario
        r = {"response": text}
        if prompt: r["prompt"] = prompt
        if newstate is not None: r["state"] = newstate
        return r

    # 1. Primer mensaje o /start
    if not user_msgs or user_msgs[-1]["text"].strip().lower() in ["/start", ""]:
        estado = {"step": "inicio"}
        return response(
            "🎲 ¡Bienvenido a GameMasterAI! 🎲\n¿Quieres **cargar** una aventura guardada o empezar una **nueva**?",
            prompt="Responde: cargar o nueva", newstate=estado
        )

    # 2. Pregunta: ¿Cargar o nueva?
    if estado.get("step") == "inicio":
        texto = user_msgs[-1]["text"].strip().lower()
        if texto.startswith("cargar"):
            saves = list_saves()
            if not saves:
                estado = {"step": "sin_saves"}
                return response("No tienes partidas guardadas. ¿Quieres empezar una nueva?", prompt="Escribe: nueva", newstate=estado)
            else:
                estado = {"step": "elige_save", "saves": saves}
                listado = "\n".join([f"{i+1}) {n}" for i, n in enumerate(saves)])
                return response(f"Tus partidas guardadas:\n{listado}\nIndica el número de la partida que deseas cargar.", prompt="Escribe el número de la partida", newstate=estado)
        elif texto.startswith("nueva"):
            estado = {"step": "nombre_aventura"}
            return response("Ponle un nombre a tu aventura (sin espacios ni acentos):", prompt="Introduce el nombre", newstate=estado)
        else:
            return response("No te he entendido. Escribe: **cargar** o **nueva**", prompt="cargar o nueva", newstate=estado)

    # 3. Elegir partida guardada
    if estado.get("step") == "elige_save":
        idx = user_msgs[-1]["text"].strip()
        if idx.isdigit() and 1 <= int(idx) <= len(estado["saves"]):
            nombre = estado["saves"][int(idx)-1]
            partida = load_game(nombre)
            estado = {"step": "jugando", "nombre_aventura": nombre, "partida": partida, "history": partida.get("messages", [])}
            return response(f"¡Aventura '{nombre}' cargada! Puedes escribir tus acciones para comenzar.", prompt="¿Qué quieres hacer?", newstate=estado)
        else:
            return response("Selecciona un número válido de la lista.", prompt="Elige número de partida", newstate=estado)

    # 4. Crear nueva aventura: pide nombre
    if estado.get("step") == "nombre_aventura":
        nombre = user_msgs[-1]["text"].strip()
        if not nombre.replace("_", "").replace("-", "").isalnum():
            return response("El nombre solo puede tener letras, números, guiones y subrayados. Prueba otro.", prompt="Introduce nombre de la aventura", newstate=estado)
        estado = {"step": "elige_sistema", "nombre_aventura": nombre}
        return response(
            "Elige sistema de juego:\n1) D20 clásico\n2) Otro (aún no implementado)",
            prompt="Elige: 1 para D20", newstate=estado
        )

    # 5. Sistema de juego
    if estado.get("step") == "elige_sistema":
        if user_msgs[-1]["text"].strip() == "1":
            rules = {"name": "D20", "attributes": ["FUE","DES","CON","INT","SAB","CAR"]}
            estado = {
                "step": "ficha_jugador",
                "nombre_aventura": estado["nombre_aventura"],
                "rules": rules,
                "npcs": [],
                "player_sheet": {}
            }
            return response("Nombre de tu personaje jugador:", prompt="Introduce el nombre del personaje", newstate=estado)
        else:
            return response("Por ahora solo D20 está disponible. Escribe '1' para elegir D20.", prompt="Escribe 1", newstate=estado)

    # 6. Crear ficha de jugador (simplificado)
    if estado.get("step") == "ficha_jugador":
        nombre_pj = user_msgs[-1]["text"].strip()
        estado["player_sheet"] = {
            "name": nombre_pj,
            "role": "Jugador",
            "class": "",
            "attributes": {},
            "history": ""
        }
        estado["step"] = "clase_jugador"
        return response("Clase del personaje (guerrero, mago, etc):", prompt="Introduce clase", newstate=estado)

    if estado.get("step") == "clase_jugador":
        estado["player_sheet"]["class"] = user_msgs[-1]["text"].strip()
        estado["step"] = "stats_jugador"
        estado["attr_index"] = 0
        return response(f"Valor para {estado['rules']['attributes'][0]}:", prompt="Introduce valor", newstate=estado)

    if estado.get("step") == "stats_jugador":
        idx = estado["attr_index"]
        attr = estado["rules"]["attributes"][idx]
        val = user_msgs[-1]["text"].strip()
        estado["player_sheet"]["attributes"][attr] = val
        if idx+1 < len(estado["rules"]["attributes"]):
            estado["attr_index"] += 1
            next_attr = estado["rules"]["attributes"][estado['attr_index']]
            return response(f"Valor para {next_attr}:", prompt="Introduce valor", newstate=estado)
        else:
            estado["step"] = "historia_jugador"
            return response("Breve trasfondo del personaje:", prompt="Introduce trasfondo", newstate=estado)

    if estado.get("step") == "historia_jugador":
        estado["player_sheet"]["history"] = user_msgs[-1]["text"].strip()
        estado["step"] = "compañeros"
        return response("¿Cuántos compañeros IA tendrá tu grupo? (0 para ninguno)", prompt="Introduce un número", newstate=estado)

    # 7. Compañeros IA (simplificado: solo pide nombre)
    if estado.get("step") == "compañeros":
        try:
            n = int(user_msgs[-1]["text"].strip())
        except:
            return response("Introduce un número válido.", prompt="¿Cuántos compañeros IA?", newstate=estado)
        estado["n_npcs"] = n
        estado["npcs"] = []
        if n > 0:
            estado["step"] = "ficha_npc"
            estado["npc_idx"] = 1
            return response(f"Nombre del compañero IA {1}:", prompt="Introduce nombre NPC", newstate=estado)
        else:
            estado["step"] = "jugar"
            # Guardar la partida
            partida = {
                "nombre_aventura": estado["nombre_aventura"],
                "rules": estado["rules"],
                "player_sheet": estado["player_sheet"],
                "npcs": [],
                "messages": []
            }
            save_game(estado["nombre_aventura"], partida)
            return response("¡Aventura creada y lista! Escribe tus acciones para comenzar la partida.", prompt="¿Qué quieres hacer?", newstate=estado)

    if estado.get("step") == "ficha_npc":
        nombre_npc = user_msgs[-1]["text"].strip()
        npc = {
            "name": nombre_npc,
            "role": "Compañero"
            # Puedes extender a más atributos igual que jugador
        }
        estado["npcs"].append(npc)
        if len(estado["npcs"]) < estado["n_npcs"]:
            estado["npc_idx"] += 1
            return response(f"Nombre del compañero IA {estado['npc_idx']}:", prompt="Introduce nombre NPC", newstate=estado)
        else:
            estado["step"] = "jugar"
            # Guardar la partida
            partida = {
                "nombre_aventura": estado["nombre_aventura"],
                "rules": estado["rules"],
                "player_sheet": estado["player_sheet"],
                "npcs": estado["npcs"],
                "messages": []
            }
            save_game(estado["nombre_aventura"], partida)
            return response("¡Aventura creada y lista! Escribe tus acciones para comenzar la partida.", prompt="¿Qué quieres hacer?", newstate=estado)

    # 8. Paso de juego normal (chat rol LLM)
    if estado.get("step") in ["jugar", "jugando"]:
        # Recuperar la partida para guardar mensajes
        nombre = estado["nombre_aventura"]
        partida = load_game(nombre)
        # Añadir la acción del usuario
        partida["messages"].append({"role": "user", "content": user_msgs[-1]["text"]})
        # Invoca el LLM para obtener respuesta del GM
        respuesta = llm_chat(partida["messages"])
        partida["messages"].append({"role": "assistant", "content": respuesta})
        save_game(nombre, partida)
        estado["step"] = "jugando"
        return response(respuesta, prompt="¿Tu siguiente acción?", newstate=estado)

    # Si no coincide ningún paso, reinicia
    return response("No entiendo en qué punto estás. Escribe /start para comenzar de nuevo.", prompt="Escribe /start", newstate={})

@app.get("/")
def root():
    return {"message": "¡Bienvenido a GameMasterAI Backend! Usa POST /chat para interactuar."}