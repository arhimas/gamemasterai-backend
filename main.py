import os
import json
import httpx
import PyPDF2
from dotenv import load_dotenv
import openai
import datetime
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict

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

class ChatRequest(BaseModel):
    messages: List[Dict]  # [{from, text, type}]

if not os.path.exists(SAVES_DIR):
    os.makedirs(SAVES_DIR)

load_dotenv()
USE_LOCAL = os.getenv("USE_LOCAL_LLM", "0") == "1"
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:8000/predict")
openai.api_key = os.getenv("OPENAI_API_KEY")

def llm_chat(messages, max_tokens=100, temperature=0.7):
    if USE_LOCAL:
        resp = httpx.post(
            LOCAL_LLM_URL,
            json={"messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            timeout=90
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    else:
        resp = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return resp.choices[0].message.content

def trim_history(messages, max_turns=15):
    if len(messages) <= max_turns + 1:
        return messages
    return [messages[0]] + messages[-max_turns:]

@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    try:
        # Lógica: recibe el historial completo (chat), añade la respuesta del GM, y devuelve el nuevo historial
        history = request.messages or []
        # El último mensaje del usuario:
        last_user = history[-1]["text"] if history and history[-1]["from"] == "user" else ""
        # --- Generar respuesta del GM (IA) ---
        llm_input = []
        for m in history:
            # Pasa el historial en formato que OpenAI espera (role/content)
            role = "user" if m["from"] == "user" else "assistant"
            llm_input.append({"role": role, "content": m["text"]})
        # Prompt especial: nunca avances historia, responde solo a lo que pregunta el jugador, etc.
        respuesta = respuesta_concisa_llm(llm_input)
        # Añade el mensaje del GM al historial
        new_messages = history + [
            {"from": "ai", "text": respuesta, "type": "normal"}
        ]
        # Ejemplo: puedes detectar comandos especiales y devolver instrucciones
        # Aquí podrías analizar si el usuario ha puesto "/start" y responder con instrucciones

        prompt = "Introduce tu próxima acción como jugador. Si necesitas ayuda escribe /ayuda."
        return {"messages": new_messages, "prompt": prompt}
    except Exception as e:
        return {"error": str(e)}

def respuesta_concisa_llm(messages, max_tokens=190, temperature=0.7, reintentos=1):
    ult = messages[-1]
    if ult["role"] == "user":
        ult_content = (
            "Eres un Game Master experimentado. No repitas la pregunta del usuario, ni las frases que él diga. "
            "Haz que los jugadores se impliquen en la historia. "
            "Responde a la pregunta ajustándote a la situación actual de la aventura y termina tu intervención con una frase completa, "
            "pero nunca avances la historia ni tomes decisiones por los personajes jugadores. "
            "No narres las acciones siguientes salvo que el jugador lo solicite expresamente. "
            "Espera siempre la próxima decisión del jugador. "
            + ult["content"]
        )
        messages = messages[:-1] + [{"role": "user", "content": ult_content}]
    respuesta = llm_chat(messages, max_tokens=max_tokens, temperature=temperature)
    if not respuesta.strip().endswith(('.', '!', '?')) and reintentos > 0:
        messages.append({"role": "user", "content": "Termina tu respuesta anterior de forma clara y breve."})
        cierre = llm_chat(messages, max_tokens=60, temperature=temperature)
        respuesta = respuesta.strip() + " " + cierre.strip()
    return respuesta

@app.get("/")
def root():
    return {"message": "¡Bienvenido a GameMasterAI Backend! Usa POST /chat para interactuar."}
