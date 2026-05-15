import sys
import types
sys.modules["av"] = types.ModuleType("av")

import threading
import sounddevice as sd
import numpy as np
import subprocess
import psutil
import asyncio
import edge_tts
import tempfile
import os
import json
import difflib
import re
from faster_whisper import WhisperModel
from pydub import AudioSegment
from pydub.playback import play

# ================== CONFIG ==================
model = WhisperModel("small", device="cuda", compute_type="float16")

ARQUIVO_MEMORIA = "memoria_apps.json"
programas = {}
memoria = {}
ultimo_app = None

# ================== MEMÓRIA ==================
def carregar_memoria():
    global memoria
    if os.path.exists(ARQUIVO_MEMORIA):
        with open(ARQUIVO_MEMORIA, "r", encoding="utf-8") as f:
            memoria = json.load(f)

def salvar_memoria():
    with open(ARQUIVO_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(memoria, f, indent=4)

carregar_memoria()

# ================== LIMPEZA ==================
def limpar_texto(texto):
    if not texto:
        return ""

    texto = texto.lower().strip()

    # remove só símbolos MUITO quebrados
    texto = re.sub(r'[^\w\sáéíóúãõâêîôûç.,!?]', '', texto)

    # corrige espaços colados (principal problema seu)
    texto = re.sub(r'([a-zá-ú])([A-Z])', r'\1 \2', texto)
    texto = re.sub(r'([a-z])([0-9])', r'\1 \2', texto)
    texto = re.sub(r'([0-9])([a-z])', r'\1 \2', texto)

    # normaliza espaços
    texto = re.sub(r'\s+', ' ', texto)

    return texto.strip()

# ================== VOZ ==================
def falar(texto):
    print("Alfa:", texto)

    if not texto:
        return

    async def gerar():
        communicate = edge_tts.Communicate(
            text=texto,
            voice="pt-BR-FranciscaNeural"
        )

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        await communicate.save(tmp.name)
        return tmp.name

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    arquivo = loop.run_until_complete(gerar())
    loop.close()

    audio = AudioSegment.from_mp3(arquivo)
    play(audio)

    os.remove(arquivo)

# ================== INPUT ==================
def ouvir():
    print("Aguardando você falar...")

    fs = 16000
    audio = sd.rec(int(5 * fs), samplerate=fs, channels=1, blocking=True)
    sd.wait()

    audio = np.squeeze(audio)
    segments, info = model.transcribe(audio)

    texto = "".join(seg.text for seg in segments)

    texto = limpar_texto(texto)

    texto = re.sub(r'\s+', '', texto).strip()

    # FILTRO DE RUÍDO
    if len(texto) < 2:
        return ""

    print("Você:", texto)
    return texto

# ================== PROGRAMAS ==================
def indexar_programas():
    global programas

    caminhos = [
        "C:\\Program Files",
        "C:\\Program Files (x86)",
        os.path.expanduser("~\\Desktop"),
        os.path.expanduser("~\\AppData\\Local")
    ]

    for caminho in caminhos:
        for root, dirs, files in os.walk(caminho):
            for file in files:
                if file.endswith(".exe"):
                    nome = file.lower().replace(".exe", "")
                    programas[nome] = os.path.join(root, file)

    print(f"{len(programas)} programas indexados!")

def encontrar_programa(nome):
    nome = nome.lower().strip()

    if nome in memoria:
        return memoria[nome]

    if nome in programas:
        return programas[nome]

    lista = list(programas.keys())
    match = difflib.get_close_matches(nome, lista, n=1, cutoff=0.5)

    if match:
        return programas[match[0]]

    return None

# ================== AÇÕES ==================
def abrir_app(texto):
    global ultimo_app

    if "abre" not in texto and "abrir" not in texto:
        return False

    nome = texto.replace("abre", "").replace("abrir", "").strip()

    if not nome:
        falar("Qual aplicativo você quer abrir?")
        return True

    caminho = encontrar_programa(nome)

    if caminho:
        os.startfile(caminho)
        ultimo_app = caminho
        falar(f"Abrindo {nome}")
        return True

    falar(f"Não encontrei {nome}. Me mostre onde está.")
    caminho_manual = input("Arraste o .exe aqui: ").strip().replace('"', '')

    if caminho_manual and os.path.exists(caminho_manual):
        memoria[nome] = caminho_manual
        salvar_memoria()

        os.startfile(caminho_manual)
        falar("Aprendi esse aplicativo.")
        return True

    falar("Não consegui aprender.")
    return True

def fechar_app(texto):
    if "fecha" not in texto:
        return False

    nome = texto.replace("fecha", "").strip().lower()

    for proc in psutil.process_iter(['name']):
        try:
            if nome in proc.info['name'].lower():
                proc.kill()
                falar(f"Fechando {nome}")
                return True
        except:
            pass

    return False

# ================== IA ==================
def perguntar_ia(pergunta):
    prompt = f"""
Responda em português do Brasil.
Responda curto (máximo 2 frases).

Pergunta: {pergunta}
"""

    resposta = subprocess.run(
        ["ollama", "run", "llama3", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    return resposta.stdout.strip()

# ================== CÉREBRO ==================
def decidir(texto):

    if abrir_app(texto):
        return

    if fechar_app(texto):
        return

    if "idade" in texto:
        falar("Não tenho idade, sou uma IA.")
        return

    if "quem é você" in texto:
        falar("Sou uma inteligência artificial assistente.")
        return

    resposta = perguntar_ia(texto)

    if not resposta:
        falar("Não entendi direito.")
        return

    falar(resposta)

# ================== START ==================
print("Alfa iniciada! 👀")
indexar_programas()

while True:
    texto = ouvir()

    if not texto:
        continue

    decidir(texto)