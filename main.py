import os
import json
import httpx
import PyPDF2
from dotenv import load_dotenv
import openai
import datetime

SAVES_DIR = "saves"

if not os.path.exists(SAVES_DIR):
    os.makedirs(SAVES_DIR)

load_dotenv()
USE_LOCAL = os.getenv("USE_LOCAL_LLM", "0") == "1"
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:8000/predict")
openai.api_key = os.getenv("OPENAI_API_KEY")

def resumen_ia(messages, n_turnos=6):
    mensajes_a_resumir = [messages[0]] + messages[-n_turnos:]
    prompt = (
        "Eres un Game Master experimentado y conciso. Resume en un solo párrafo, de forma clara y breve, "
        "la situación actual de la aventura para que el jugador recuerde el contexto: "
        "indica dónde están los personajes, qué acaba de ocurrir y cuáles son las opciones o líneas abiertas. "
        "No inventes nada fuera de la historia ya escrita, solo resume lo jugado hasta ahora."
    )
    mensajes_prompt = mensajes_a_resumir + [{"role": "user", "content": prompt}]
    try:
        resumen = llm_chat(mensajes_prompt)
    except Exception as e:
        resumen = f"[No se pudo generar el resumen automático por IA: {e}]"
    return resumen

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

def load_campaign_module(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_campaign_pdf(path):
    reader = PyPDF2.PdfReader(path)
    content = "".join(page.extract_text() for page in reader.pages)
    return {"name": os.path.basename(path), "content": content}

def save_game(state, save_path):
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_game(save_path):
    with open(save_path, "r", encoding="utf-8") as f:
        return json.load(f)

def create_character_interactive(name, role, rules):
    mode = input(f"Asignación para {role} '{name}': automática (a) o manual (m)? ").strip().lower()
    if mode == 'm':
        print(f"Modo manual: introduce los datos de {role} '{name}'")
        klass = input("  Clase: ")
        attrs = {}
        for att in rules.get('attributes', []):
            val = input(f"  {att}: ").strip()
            attrs[att] = int(val) if val.isdigit() else val
        history = input("  Trasfondo breve: ")
        return {"name": name, "role": role, "class": klass, "attributes": attrs, "history": history}
    else:
        prompt = (
            f"Eres un generador de fichas para el sistema {rules['name']}. "
            f"Crea la ficha de {role} '{name}' con atributos, trasfondo y habilidades. Devuélvelo solo en JSON."
        )
        content = llm_chat([{"role": "user", "content": prompt}])
        return json.loads(content)

def trim_history(messages, max_turns=15):
    if len(messages) <= max_turns + 1:
        return messages
    return [messages[0]] + messages[-max_turns:]

def show_welcome():
    print("="*60)
    print("🎲 Bienvenido a GameMaster AI 🎲\n")
    print("Este sistema te permite disfrutar de partidas de rol gestionadas por IA.")
    print("Funciones principales:")
    print("  - Gestiona múltiples aventuras guardadas simultáneamente")
    print("  - Crea campañas propias o usa módulos en PDF/JSON")
    print("  - Genera fichas automáticas o personalizadas de personajes y compañeros")
    print("  - Todo el progreso se guarda y puedes reanudar cualquier aventura")
    print("Sugerencia: ¡Explora, improvisa y juega como quieras!\n")
    print("="*60)

def select_save():
    saves = [f for f in os.listdir(SAVES_DIR) if f.endswith('.json')]
    if not saves:
        print("No hay partidas guardadas. Empezaremos una nueva aventura.")
        return None
    print("\nPartidas disponibles:")
    for idx, fname in enumerate(saves, 1):
        fpath = os.path.join(SAVES_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                nombre = data.get("nombre_aventura") or fname[:-5]
                pj = data.get("player_sheet", {}).get("nombreJugador") or data.get("player_sheet", {}).get("name", "¿?")
        except Exception:
            nombre = fname[:-5]
            pj = "¿?"
        fecha = datetime.datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M')
        print(f"  {idx}) {nombre} (PJ: {pj}, {fecha})")
    print("  N) Empezar nueva aventura")
    sel = input("Selecciona una partida para continuar o pulsa N para nueva: ").strip().lower()
    if sel == "n":
        return None
    try:
        idx = int(sel) - 1
        if idx < 0 or idx >= len(saves):
            raise ValueError
        return os.path.join(SAVES_DIR, saves[idx])
    except Exception:
        print("Selección no válida. Volviendo a menú inicial.")
        return select_save()

def setup_game():
    print("\n=== CREAR NUEVA AVENTURA ===")
    aventura = input("Ponle un nombre a tu aventura (sin espacios ni acentos): ").strip()
    if not aventura:
        print("Debes indicar un nombre.")
        return setup_game()
    aventura_clean = "".join(c for c in aventura if c.isalnum() or c in "_-").lower()
    save_path = os.path.join(SAVES_DIR, f"{aventura_clean}.json")
    if os.path.exists(save_path):
        overwrite = input("Ya existe una aventura con ese nombre. ¿Sobrescribir? (s/n): ").strip().lower()
        if overwrite != "s":
            return setup_game()
    print("Elige sistema de juego:\n 1) D20 clásico\n 2) Otro")
    sys_choice = input("Opción: ").strip()
    if sys_choice == '1':
        rules = {"name": "D20", "attributes": ["FUE","DES","CON","INT","SAB","CAR"]}
    else:
        rules = {}
    if input("¿Quieres subir un módulo de campaña? (s/n): ").strip().lower() == 's':
        mtype = input("Tipo de módulo: 1) JSON  2) PDF: ").strip()
        path = input("Ruta al fichero: ").strip()
        if mtype == '1':
            rules = load_campaign_module(path)
            print(f"Módulo JSON '{rules.get('name','sin nombre')}' cargado.")
        else:
            camp = load_campaign_pdf(path)
            rules.update({"name": camp.get('name'), "campaign_text": camp.get('content')})
            print(f"Campaña PDF '{camp.get('name')}' cargada.")
    player = input("Nombre de tu personaje jugador: ").strip()
    player_sheet = create_character_interactive(player, "Jugador", rules)
    print(f"\nFicha creada: {json.dumps(player_sheet, indent=2, ensure_ascii=False)}")
    npcs = []
    ncomp = input("Número de compañeros IA (0 para ninguno): ").strip() or '0'
    for i in range(int(ncomp)):
        name = input(f"Nombre NPC {i+1}: ").strip()
        sheet = create_character_interactive(name, "Compañero", rules)
        npcs.append(sheet)
    header = (
        "Eres el GM usando sistema {rules.get('name')}. "
        "Gestiona la partida creando escenas, NPCs, monstruos y mapas según las acciones del jugador. "
        "Nunca avances la historia ni tomes decisiones por los jugadores. Después de responder, "
        "espera la próxima acción del jugador, a menos que te indiquen explícitamente lo contrario."
    )
    messages = [{"role": "system", "content": header}]
    messages.append({"role": "user", "content": json.dumps({"player": player_sheet, "npcs": npcs}, ensure_ascii=False)})
    state = {
        "nombre_aventura": aventura,
        "rules": rules,
        "player_sheet": player_sheet,
        "npcs": npcs,
        "messages": messages
    }
    save_game(state, save_path)
    print(f"¡Aventura '{aventura}' creada y guardada!")
    return save_path

def respuesta_concisa_llm(messages, max_tokens=190, temperature=0.7, reintentos=1):
    """
    Llama al LLM y reintenta una vez si la respuesta termina abruptamente.
    """
    # Modifica el último mensaje de usuario para pedir respuesta cerrada y breve.
    ult = messages[-1]
    if ult["role"] == "user":
        ult_content = (
            "Eres un Game Master experimentado. No repitas la pregunta del usuario, ni las frases que él diga. "
            "Eres un Game Master experimentado y haces que los jugadores se impliquen en la historia. "
            "Responde a la pregunta ajustándote a la situación actual de la aventura y termina tu intervención con una frase completa, "
            "pero nunca avances la historia ni tomes decisiones por los personajes jugadores. "
            "No narres las acciones siguientes salvo que el jugador lo solicite expresamente. "
            "Espera siempre la próxima decisión del jugador. "
            + ult["content"]
        )
        messages = messages[:-1] + [{"role": "user", "content": ult_content}]
    respuesta = llm_chat(messages, max_tokens=max_tokens, temperature=temperature)
    # Si acaba abruptamente, reintenta una vez pidiendo cerrar la respuesta
    if not respuesta.strip().endswith(('.', '!', '?')) and reintentos > 0:
        messages.append({"role": "user", "content": "Termina tu respuesta anterior de forma clara y breve."})
        cierre = llm_chat(messages, max_tokens=60, temperature=temperature)
        respuesta = respuesta.strip() + " " + cierre.strip()
    return respuesta

def main():
    show_welcome()
    print("\n¿Qué quieres hacer?\n  1) Cargar una aventura guardada\n  2) Empezar nueva aventura\n")
    opcion = input("Elige opción: ").strip()
    if opcion == "1":
        save_path = select_save()
        if save_path is None:
            save_path = setup_game()
    else:
        save_path = setup_game()
    state = load_game(save_path)

    # --- BLOQUE CORRECTOR DEL NOMBRE DE AVENTURA ---
    if not state.get("nombre_aventura"):
        nombre_derive = os.path.splitext(os.path.basename(save_path))[0]
        state["nombre_aventura"] = nombre_derive
        save_game(state, save_path)  # Opcional pero recomendado

    rules = state["rules"]
    player_sheet = state["player_sheet"]
    npcs = state["npcs"]
    messages = state["messages"]
    print("\n─── Resumen de la aventura ─────────")
    resumen = resumen_ia(messages)
    print(resumen)
    print("────────────────────────────────────\n")
    nombre_aventura = state.get("nombre_aventura") or "-"
    print(f"\n¡Partida configurada! (Aventura: {nombre_aventura})")
    print("Escribe tus acciones para comenzar (o 'salir' para terminar):")
    while True:
        action = input("Tú: ").strip()
        if action.lower() == 'salir':
            state = {
                "nombre_aventura": state.get("nombre_aventura"),
                "rules": rules,
                "player_sheet": player_sheet,
                "npcs": npcs,
                "messages": messages
            }
            save_game(state, save_path)
            print("Partida guardada. ¡Hasta la próxima!")
            break
        messages.append({"role": "user", "content": action})
        trimmed = trim_history(messages, max_turns=18)
        reply = respuesta_concisa_llm(trimmed)
        print(f"\nGM: {reply}\n")
        messages.append({"role": "assistant", "content": reply})

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nPartida interrumpida por el usuario (Ctrl+C). ¡Hasta la próxima!")

