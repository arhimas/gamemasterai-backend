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

SAVES_DIR = "saves"

class ChatRequest(BaseModel):
    messages: List[Dict]

if not os.path.exists(SAVES_DIR):
    os.makedirs(SAVES_DIR)

load_dotenv()
USE_LOCAL = os.getenv("USE_LOCAL_LLM", "0") == "1"
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:8000/predict")
openai.api_key = os.getenv("OPENAI_API_KEY")

def llm_chat(messages, max_tokens=100, temperature=0.7):
    """Envía el historial de mensajes al LLM local o remoto y devuelve la respuesta."""
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

def respuesta_concisa_llm(messages, max_tokens=190, temperature=0.7, reintentos=1):
    """
    Llama al LLM y reintenta una vez si la respuesta termina abruptamente.
    """
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

@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    try:
        # Usa la función real del Game Master para responder
        respuesta = respuesta_concisa_llm(request.messages)
        return {"response": respuesta}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def root():
    return {"message": "¡Bienvenido a GameMasterAI Backend! Usa POST /chat para interactuar."}
