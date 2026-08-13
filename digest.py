import os, requests
from bs4 import BeautifulSoup
from datetime import datetime

# ================= НАСТРОЙКИ =================
CHANNELS = [
    "land_jurist",
    "zemlya_tvoi_kapital",
    "OzhevaProZem",
    "kameneva_law"
]

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID   = os.getenv("CHAT_ID", "").strip()
HF_KEY    = os.getenv("HF_KEY", "").strip()

AI_URL_HF = "https://router.huggingface.co/v1/chat/completions"
HF_MODELS = [
    "mistralai/Mistral-7B-Instruct-v0.3",
    "microsoft/Phi-3.5-mini-instruct",
]

SEEN_FILE = "seen.txt"
POSTS_PER_CHANNEL = 5
# =============================================

PROMPT = """Ты — помощник земельного специалиста. Из постов ниже сделай краткий
дайджест на русском: 5–8 пунктов по сути, отдельно выдели всё, что касается
ВРИ, категорий, зон, торгов, судов и рисков. Живой стиль, без воды.

ПОСТЫ:
"""

def get_posts(channel):
    r = requests.get(f"https://t.me/s/{channel}", headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")
    posts = []
    for block in soup.select("div.tgme_widget_message_bubble"):
        text_div = block.select_one("div.tgme_widget_message_text")
        time_a   = block.select_one("time")
        if text_div and time_a:
            posts.append((time_a.get("datetime"), text_div.get_text(" ", strip=True)[:600]))
    return posts[-POSTS_PER_CHANNEL:]

def ask_hf(text):
    if not HF_KEY:
        print("⚠️ HF_KEY пустой — пропускаю Hugging Face")
        return None
    for model in HF_MODELS:
        r = requests.post(
            AI_URL_HF,
            headers={"Authorization": f"Bearer {HF_KEY}"},
            json={"model": model, "temperature": 0.4,
                  "messages": [{"role": "user", "content": text}]})
        if r.status_code == 200:
            print(f"✅ Сработала модель HF: {model}")
            return r.json()["choices"][0]["message"]["content"]
        print(f"⚠️ {model} → {r.status_code}: {r.text[:200]}")
    return None

def ask_pollinations(text):
    """Запасная нейросеть БЕЗ ключа."""
    print("🔄 Пробую Pollinations (без ключа)...")
    try:
        r = requests.post(
            "https://text.pollinations.ai/openai",
            json={"model": "openai", "temperature": 0.4,
                  "messages": [{"role": "user", "content": text}]},
            timeout=180)
        if r.status_code == 200:
            try:
                return r.json()["choices"][0]["message"]["content"]
            except Exception:
                if len(r.text) > 100:
                    return r.text
    except Exception as e:
        print("⚠️ Pollinations /openai error:", e)
    try:
        r = requests.post(
            "https://text.pollinations.ai/",
            json={"messages": [{"role": "user", "content": text}], "model": "openai"},
            timeout=180)
        if r.status_code == 200 and len(r.text) > 100:
            print("✅ Сработал Pollinations")
            return r.text
        print(f"⚠️ Pollinations → {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print("⚠️ Pollinations error:", e)
    return None

def main():
    print(f"🔑 Длины ключей: BOT_TOKEN={len(BOT_TOKEN)}, CHAT_ID={len(CHAT_ID)}, HF_KEY={len(HF_KEY)}")

    seen = set(open(SEEN_FILE).read().splitlines()) if os.path.exists(SEEN_FILE) else set()
    new_posts, new_ids = [], []

    for ch in CHANNELS:
        for dt, text in get_posts(ch):
            if dt not in seen and text:
                new_posts.append(f"[{ch}] {text}")
                new_ids.append(dt)

    if not new_posts:
        print("Новых постов нет — дайджест не отправлен.")
        return

    full_text = PROMPT + "\n---\n".join(new_posts)

    digest = ask_hf(full_text)
    if digest is None:
        digest = ask_pollinations(full_text)
    if digest is None:
        print("❌ Ни одна нейросеть не сработала. Пришли мне лог выше.")
        return

    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  json={"chat_id": CHAT_ID,
                        "text": f"🗞️ Земельный дайджест · {datetime.now():%d.%m}\n\n{digest}"})

    open(SEEN_FILE, "a").write("\n".join(new_ids) + "\n")
    print("Дайджест отправлен ✅")

if __name__ == "__main__":
    main()
