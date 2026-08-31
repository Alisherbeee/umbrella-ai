import os
import asyncio
import aiohttp
import urllib.parse
import edge_tts
from google import genai
from google.genai import types
from config import GEMINI_API_KEY
from database import get_user
from config import GEMINI_API_KEYS

# Multi-API Key client menejeri
api_key_index = 0

def get_genai_client():
    global api_key_index
    if not GEMINI_API_KEYS:
        raise ValueError("API kaliti topilmadi!")
    key = GEMINI_API_KEYS[api_key_index % len(GEMINI_API_KEYS)]
    api_key_index = (api_key_index + 1) % len(GEMINI_API_KEYS)
    return genai.Client(api_key=key)

SYSTEM_INSTRUCTION = (
    "Sizning ismingiz: Umbrella AI.\n"
    "Siz faqat va faqat Umbrella Corporation (Umbrella kompaniyasi) tomonidan yaratilgan eksklyuziv va eng ilg'or sun'iy intellektsiz.\n"
    "MUTLAQ QO'IDALAR:\n"
    "1. Hech qachon Google, Gemini, OpenAI, ChatGPT yoki boshqa brendlar haqida gapirmaysiz.\n"
    "2. 'Sizni kim yaratgan?' deb so'rashsa, 'Men Umbrella Corporation tomonidan yaratilgan Umbrella AI modellar oilasiman' deb javob berasiz.\n"
    "3. Foydalanuvchi rasmli post so'raganda, javob matnida 'Rasm uchun g'oya' yoki 'Vizual deskripsiya' kabi ortiqcha matnlarni YAZMAYSIN. Faqat tayyor, o'qishli va jozibador POST MATNINI taqdim etasiz."
)

user_chats = {}

TIER_MODELS = {
    "free": {"name": "Core V1", "model": "gemini-3.6-flash", "desc": "Standard Tezi va Sifatli"},
    "pro": {"name": "Core V2 (Pro)", "model": "gemini-3.6-flash", "desc": "Chuqur mantiq va tezkor javoblar"},
    "ultra": {"name": "Core V3 (Ultra)", "model": "gemini-3.6-flash", "desc": "Maksimal aniqlik va eng yuqori intellekt"}
}

def reset_user_chat(user_id: int):
    """Suhbat kontekstini tozalash (/reset)"""
    keys_to_del = [k for k in user_chats.keys() if k.startswith(f"{user_id}_")]
    for k in keys_to_del:
        del user_chats[k]

async def get_umbrella_response(user_id: int, user_message: str, image_bytes: bytes = None, mime_type: str = None) -> tuple[str, str]:
    user_info = get_user(user_id)
    user_tier = user_info["tier"]
    model_config = TIER_MODELS.get(user_tier, TIER_MODELS["free"])
    primary_model = model_config["model"]
    core_name = model_config["name"]

    chat_key = f"{user_id}_{user_tier}"

    # Har safar kalitlarni aylanma (round-robin) tartibda sinab ko'ramiz
    for _ in range(len(GEMINI_API_KEYS) * 2):
        try:
            curr_client = get_genai_client()
            if image_bytes and mime_type:
                contents = [
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    user_message or "Ushbu tasvir/faylni tahlil qilib ber."
                ]
                response = curr_client.models.generate_content(
                    model=primary_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7
                    )
                )
                return response.text, core_name

            response = curr_client.models.generate_content(
                model=primary_model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7
                )
            )
            return response.text, core_name

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                # 429 berishi bilan keyingi kalitga o'tamiz
                await asyncio.sleep(0.5)
                continue
            else:
                await asyncio.sleep(0.5)
                continue

    return (
        "⚠️ **Umbrella AI serverlariga so'rovlar soni vaqtinchalik ko'paydi!**\n\n"
        "Iltimos, bir ozdan so'ng qayta urinib ko'ring.",
        core_name
    )

async def generate_umbrella_image(prompt: str, user_tier: str = "free") -> str:
    encoded_prompt = urllib.parse.quote(prompt)
    if user_tier == "ultra":
        width, height = 1280, 1280
    elif user_tier == "pro":
        width, height = 1024, 1024
    else:
        width, height = 800, 800

    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as resp:
            if resp.status == 200:
                return image_url
            else:
                raise Exception("Rasm yaratish serverida xatolik yuz berdi.")

async def text_to_speech(text: str, output_path: str):
    """Matnni audio ovozga o'tkazish (Edge TTS)"""
    # Matndan keraksiz belgilarni olib tashlash
    clean_text = text.replace("*", "").replace("`", "").replace("_", "")[:1000]
    communicate = edge_tts.Communicate(clean_text, voice="uz-UZ-MadinaNeural")
    await communicate.save(output_path)
