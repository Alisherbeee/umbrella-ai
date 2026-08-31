import os
import asyncio
import aiohttp
import urllib.parse
import edge_tts
from aiohttp import web
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
    clean_text = text.replace("*", "").replace("`", "").replace("_", "")[:1000]
    communicate = edge_tts.Communicate(clean_text, voice="uz-UZ-MadinaNeural")
    await communicate.save(output_path)

import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatAction
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery
import pypdf
from io import BytesIO

from config import BOT_TOKEN, ADMIN_ID
from database import init_db, get_user, set_user_tier, get_all_users, increment_daily_usage

logging.basicConfig(level=logging.INFO)
init_db()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TIER_LIMITS = {
    "free": 10,
    "pro": 100,
    "ultra": 9999
}

IMAGE_KEYWORDS = [
    "rasm chiz", "rasm yarat", "rasm chiqar", "rasmini chiz", "rasmini yarat",
    "draw", "generate image", "create image", "picture of", "image of",
    "нарисуй", "создай картинку", "изображение", "картинка"
]

def is_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID

async def check_user_limit(message: types.Message) -> bool:
    user_id = message.from_user.id
    if is_admin(user_id):
        return True

    user_info = get_user(user_id, message.from_user.username or "")
    user_tier = user_info["tier"]
    used = user_info["daily_usage"]
    max_limit = TIER_LIMITS.get(user_tier, 10)

    if used >= max_limit:
        builder = InlineKeyboardBuilder()
        builder.button(text="⭐ Obunani Yangilash (Cheksiz kirish)", callback_data="show_plans")
        limit_msg = (
            f"⛔ **Kunlik bepul limitingiz tugadi!**\n\n"
            f"📊 Siz bugun **{used}/{max_limit}** ta so'rov ishlatdingiz.\n"
            f"Kunlik limit har kuni soat 00:00 da yangilanadi.\n\n"
            f"🚀 Cheksiz foydalanish va kuchliroq AI uchun obuna bo'ling:"
        )
        await message.answer(limit_msg, reply_markup=builder.as_markup(), parse_mode="Markdown")
        return False
    
    increment_daily_usage(user_id)
    return True

@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    user_info = get_user(message.from_user.id, message.from_user.username or "")
    user_tier = user_info["tier"]
    core_name = TIER_MODELS[user_tier]["name"]
    used = user_info["daily_usage"]
    max_limit = TIER_LIMITS.get(user_tier, 10)
    limit_str = "Cheksiz" if max_limit > 1000 else f"{used}/{max_limit}"

    welcome_text = (
        "👋 **Salom! Men Umbrella AI'man.**\n\n"
        "Men **Umbrella Corporation** tomonidan yaratilgan eng ilg'or sun'iy intellekt assistentiman.\n\n"
        f"⚡ **Sizning joriy modelingiz:** `{core_name}`\n"
        f"📊 **Bugungi Limit:** `{limit_str}` ta so'rov\n\n"
        "✨ **Imkoniyatlar:**\n"
        "• 💬 Savol-javob va matnli muloqot\n"
        "• 🎙 **Ovozli xabarlar**\n"
        "• 🖼 **Rasm, Kod va PDF tahlili**\n"
        "• 🎨 **Rasm generatsiyasi**\n"
        "• 🔄 `/reset` - Suhbatni tozalash\n"
        "• 💳 `/plans` - Obunalar\n"
        "• 👤 `/profile` - Profil"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message(Command("reset"))
async def handle_reset(message: types.Message):
    reset_user_chat(message.from_user.id)
    await message.answer("🔄 **Suhbat tarixi muvaffaqiyatli tozalandi!**", parse_mode="Markdown")

@dp.message(Command("profile"))
async def send_profile(message: types.Message):
    user_info = get_user(message.from_user.id)
    user_tier = user_info["tier"]
    used = user_info["daily_usage"]
    max_limit = TIER_LIMITS.get(user_tier, 10)
    limit_str = "Cheksiz" if max_limit > 1000 else f"{used}/{max_limit} ta so'rov"
    expire_date = user_info["expire_date"] or "Muddatsiz (Tekin)"
    core_name = TIER_MODELS[user_tier]["name"]
    desc = TIER_MODELS[user_tier]["desc"]

    profile_text = (
        "👤 **Foydalanuvchi Profili**\n\n"
        f"🆔 ID: `{message.from_user.id}`\n"
        f"📊 Obuna Darajasi: **{user_tier.upper()}**\n"
        f"🤖 Model: **{core_name}**\n"
        f"ℹ️ Tarif: _{desc}_\n"
        f"📈 Bugungi Limit: `{limit_str}`\n"
        f"📅 Tugash Muddati: `{expire_date}`\n"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Obunani Yangilash", callback_data="show_plans")
    await message.answer(profile_text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.message(Command("plans"))
async def send_plans(message: types.Message):
    plans_text = (
        "☂️ **Umbrella AI — Obuna Tariflari**\n\n"
        "🟢 **Core V1 (Tekin)** — 10 ta so'rov/kun\n"
        "🔵 **Core V2 (Pro) — 15,000 UZS / 100 Stars** — 100 ta so'rov/kun\n"
        "🟣 **Core V3 (Ultra) — 35,000 UZS / 250 Stars** — Cheksiz so'rovlar"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Core V2 (Pro)", callback_data="buy_pro")
    builder.button(text="👑 Core V3 (Ultra)", callback_data="buy_ultra")
    builder.adjust(1)
    await message.answer(plans_text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "show_plans")
async def process_show_plans(callback: types.CallbackQuery):
    await send_plans(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "buy_pro")
async def process_buy_pro(callback: types.CallbackQuery):
    prices = [LabeledPrice(label="Core V2 (Pro Obuna)", amount=100)]
    await bot.send_invoice(
        chat_id=callback.from_user.id, title="Core V2 (Pro)", description="1 oylik Pro obuna",
        payload="buy_pro_payload", provider_token="", currency="XTR", prices=prices
    )
    await callback.answer()

@dp.callback_query(F.data == "buy_ultra")
async def process_buy_ultra(callback: types.CallbackQuery):
    prices = [LabeledPrice(label="Core V3 (Ultra Obuna)", amount=250)]
    await bot.send_invoice(
        chat_id=callback.from_user.id, title="Core V3 (Ultra)", description="1 oylik Ultra obuna",
        payload="buy_ultra_payload", provider_token="", currency="XTR", prices=prices
    )
    await callback.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    user_id = message.from_user.id
    if payload == "buy_pro_payload":
        set_user_tier(user_id, "pro", days=30)
        await message.answer("🎉 **Core V2 (Pro) obuna faollashtirildi!**", parse_mode="Markdown")
    elif payload == "buy_ultra_payload":
        set_user_tier(user_id, "ultra", days=30)
        await message.answer("👑 **Core V3 (Ultra) obuna faollashtirildi!**", parse_mode="Markdown")

@dp.message(Command("stats"))
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id): return
    users = get_all_users()
    total = len(users)
    free_c = sum(1 for u in users if u[1] == 'free')
    pro_c = sum(1 for u in users if u[1] == 'pro')
    ultra_c = sum(1 for u in users if u[1] == 'ultra')
    await message.answer(f"📊 Jami: {total}\nFree: {free_c}\nPro: {pro_c}\nUltra: {ultra_c}", parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def admin_broadcast(message: types.Message):
    if not is_admin(message.from_user.id): return
    text = message.text.replace("/broadcast", "").strip()
    if not text: return
    for u in get_all_users():
        try: await bot.send_message(u[0], f"📢 {text}"); await asyncio.sleep(0.05)
        except: pass
    await message.answer("✅ Xabar yuborildi!")

@dp.message(Command("setup"))
async def admin_set_user(message: types.Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()
        set_user_tier(int(args[1]), args[2].lower(), 30)
        await message.answer("✅ Yangilandi!")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    if not await check_user_limit(message): return
    await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
    file_info = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    response, core_name = await get_umbrella_response(message.from_user.id, "Ovozli xabarga javob ber.", file_bytes.read(), "audio/ogg")
    audio_path = f"voice_{message.from_user.id}.mp3"
    try:
        await text_to_speech(response, audio_path)
        await message.answer_voice(FSInputFile(audio_path), caption=f"⚡ {core_name}")
        if os.path.exists(audio_path): os.remove(audio_path)
    except:
        await message.answer(f"{response}\n\n⚡ {core_name}", parse_mode="Markdown")

@dp.message(F.photo | F.document)
async def handle_files(message: types.Message):
    if not await check_user_limit(message): return
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    caption = message.caption or "Tahlil qil."
    if message.photo:
        file_bytes = await bot.download_file((await bot.get_file(message.photo[-1].file_id)).file_path)
        res, core = await get_umbrella_response(message.from_user.id, caption, file_bytes.read(), "image/jpeg")
        await message.answer(f"{res}\n\n⚡ {core}", parse_mode="Markdown")
    elif message.document:
        raw = await bot.download_file((await bot.get_file(message.document.file_id)).file_path)
        res, core = await get_umbrella_response(message.from_user.id, f"Fayl matni:\n{raw.read().decode('utf-8', errors='ignore')[:6000]}\n\nBuyruq: {caption}")
        await message.answer(f"{res}\n\n⚡ {core}", parse_mode="Markdown")

@dp.message(F.text)
async def handle_message(message: types.Message):
    if not await check_user_limit(message): return
    text = message.text.strip()
    text_lower = text.lower()
    user_id = message.from_user.id
    user_tier = get_user(user_id)["tier"]

    if any(kw in text_lower for kw in IMAGE_KEYWORDS) and "rasmli" not in text_lower:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        try:
            prompt = text
            for kw in IMAGE_KEYWORDS: prompt = prompt.lower().replace(kw, "").strip()
            url = await generate_umbrella_image(prompt or text, user_tier)
            await message.answer_photo(photo=url, caption=f"🖼 Rasm yaratildi!", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}")
    else:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        res, core = await get_umbrella_response(user_id, text)
        await message.answer(f"{res}\n\n⚡ _Model: {core}_", parse_mode="Markdown")

# Render port talabini qondirish uchun veb-server
async def handle_web(request):
    return web.Response(text="Umbrella AI Bot is running!")

async def web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle_web)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    print("Umbrella AI Bot ishga tushmoqda...")
    await asyncio.gather(
        web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())