import google.generativeai as genai

# 1. Pega aquí tu API key de Gemini
genai.configure(api_key="AIzaSyBTNWR9trEi8NOGeb62NGJrRIob0ZKQs1M")

# 2. Elige el modelo de Gemini (por ejemplo: gemini-1.5-pro-latest)
model = genai.GenerativeModel('gemini-1.5-pro-latest')

# 3. Envía un prompt (igual que con OpenAI)
response = model.generate_content("Resume brevemente esta aventura: un mago y un paladín llegan a un pueblo y descubren una conspiración elfa.")

print("Gemini responde:", response.text)
