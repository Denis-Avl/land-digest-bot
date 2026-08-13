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

AI_URL = "https://router.huggingface.co/v1/chat/completions"
AI_MODELS = [
    "mistralai/Mistral-7B-Instruct-v0.3",
    "microsoft/Phi-3.5-mini-instruct",
    "Qwen/Qwen2.5-72B-Instruct",
]

SEEN_FILE = "seen.txt"
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
            posts.append((time_a.get("datetime"), text_div.get_text(" ", strip=True)))
    return posts

def ask_ai(text):
    for model in AI_MODELS:
        r = requests.post(
            AI_URL,
            headers={"Authorization": f"Bearer {HF_KEY}"},
            json={"model": model, "temperature": 0.4,
                  "messages": [{"role": "user", "content": text}]})
        if r.status_code == 200:
            print(f"✅ Сработала модель: {model}")
            return r.json()["choices"][0]["message"]["content"]
        print(f"⚠️ {model} → {r.status_code}: {r.text[:200]}")
    return None

def main():
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

    digest = ask_ai(PROMPT + "\n---\n".join(new_posts))
    if digest is None:
        print("❌ Ни одна модель не сработала. Скопируй лог выше и пришли мне.")
        return

    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  json={"chat_id": CHAT_ID,
                        "text": f"🗞️ Земельный дайджест · {datetime.now():%d.%m}\n\n{digest}"})

    open(SEEN_FILE, "a").write("\n".join(new_ids) + "\n")
    print("Дайджест отправлен ✅")

if __name__ == "__main__":
    main()
