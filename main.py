# -*- coding: utf-8 -*-
"""
=====================================================================
   بات رسمی روبیکا (Bot Platform - با توکن) — اختصاصی اُ
   فقط با requests مستقیم به API رسمی روبیکا وصل می‌شیم، بدون هیچ
   کتابخانه‌ی واسط.

   نکته‌ی مهم درباره‌ی نقل‌قول/تکی (Mono):
   روبیکا فرمت‌بندی رو از داخل خود متن (مثل ``` یا `` `text` `` یا "> ")
   نمی‌خونه! باید از فیلد جدای "metadata" با آرایه‌ی meta_data_parts
   استفاده کرد که هر بخش، ایندکس شروع و طولش رو بر حسب UTF-16 مشخص
   می‌کنه. تابع make_meta پایین همین کار رو انجام می‌ده.
=====================================================================

اجرا:
    1) pip install requests   (اگه از قبل نصب نیست)
    2) توکن باتت رو جای RUBIKA_TOKEN بذار
    3) python o_bot.py
"""

import time
import json
import os
import requests
from datetime import datetime

# ------------------------- تنظیمات -------------------------
RUBIKA_TOKEN = "CBFJAC0EUURCJJRDYAHDCTVZSSYCZKNDJJKCIKBOQHKDEBPAKSDJTIHPEFLZZOMG"  # توکن باتت رو اینجا بذار
# چت مقصد پیام‌های ناشناس. اگه اشتباه باشه سرور خطای INVALID_ACCESS می‌ده.
# برای گرفتن مقدار درست: از داخل بات روی «👤 اطلاعات من» بزن و «شناسه چت» رو کپی کن.
ANON_TARGET_CHAT_ID = "b0JdCXS0xBX0881f0817af0ae10db2d6"
ANON_COOLDOWN_SECONDS = 30  # ضد هرزنامه: فاصله‌ی مجاز بین دو پیام ناشناس
POLL_INTERVAL = 2  # فاصله‌ی هر بار چک‌کردن پیام‌های جدید (ثانیه)

BASE_URL = f"https://botapi.rubika.ir/v3/{RUBIKA_TOKEN}"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state.json")

waiting_for_anon: set = set()      # sender_id کاربرهایی که منتظر ارسال پیام ناشناس‌ان
user_lang: dict = {}               # sender_id -> "fa" | "en"  (ذخیره و بازیابی می‌شه)
last_anon_time: dict = {}          # sender_id -> timestamp آخرین پیام ناشناس (ذخیره و بازیابی می‌شه)
seen_message_ids: set = set()      # جلوگیری از پردازش تکراری یک پیام


# ---------------------- ذخیره/بازیابی وضعیت (زنده موندن بعد از ریستارت) ----------------------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            user_lang.update(data.get("user_lang", {}))
            last_anon_time.update(data.get("last_anon_time", {}))
            return data.get("offset_id")
        except Exception as e:
            print("⚠️ خطا در خواندن فایل وضعیت (نادیده گرفته شد):", e)
    return None


def save_state(offset_id):
    try:
        data = {
            "user_lang": user_lang,
            "last_anon_time": last_anon_time,
            "offset_id": offset_id,
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print("⚠️ خطا در ذخیره‌ی فایل وضعیت:", e)


# ---------------------- متادیتای فرمت‌بندی (نقل‌قول Quote / تکی Mono) ----------------------
def utf16_len(s) -> int:
    return len(str(s).encode("utf-16-le")) // 2


def make_meta(text: str, mono_parts=None, quote_parts=None):
    """برای هر رشته‌ی داده‌شده، محل دقیقش داخل متن رو پیدا می‌کنه و
    یک meta_data_part متناظر می‌سازه. اگه رشته‌ای پیدا نشه، نادیده گرفته می‌شه."""
    meta_parts = []
    if mono_parts:
        for value in mono_parts:
            value = str(value)
            start = text.find(value)
            if start != -1:
                meta_parts.append({
                    "type": "Mono",
                    "from_index": utf16_len(text[:start]),
                    "length": utf16_len(value),
                })
    if quote_parts:
        for value in quote_parts:
            value = str(value)
            start = text.find(value)
            if start != -1:
                meta_parts.append({
                    "type": "Quote",
                    "from_index": utf16_len(text[:start]),
                    "length": utf16_len(value),
                })
    return {"meta_data_parts": meta_parts} if meta_parts else None


# ---------------------- هسته‌ی ارتباط با API (فقط requests) ----------------------
def api_call(method: str, payload: dict | None = None):
    url = f"{BASE_URL}/{method}"
    resp = requests.post(url, json=payload or {}, timeout=15)
    try:
        body = resp.json()
    except Exception:
        print(f"⚠️ پاسخ غیرمنتظره از {method} (HTTP {resp.status_code}):", resp.text[:500])
        resp.raise_for_status()
        return None

    status = body.get("status") if isinstance(body, dict) else None
    if status and status != "OK":
        target = (payload or {}).get("chat_id", "?")
        print(f"⚠️ سرور روبیکا برای متد {method} (چت مقصد: {target}) خطا داد:", body)

    resp.raise_for_status()
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def get_updates(limit=10, offset_id=None):
    payload = {"limit": limit}
    if offset_id:
        payload["offset_id"] = offset_id
    data = api_call("getUpdates", payload) or {}
    updates = data.get("updates", []) if isinstance(data, dict) else []
    next_offset_id = data.get("next_offset_id") if isinstance(data, dict) else None
    return updates, next_offset_id


def send_message(chat_id, text, chat_keypad=None, chat_keypad_type=None, metadata=None):
    payload = {"chat_id": str(chat_id), "text": text}
    if chat_keypad is not None:
        payload["chat_keypad"] = chat_keypad
        payload["chat_keypad_type"] = chat_keypad_type or "New"
    if metadata:
        payload["metadata"] = metadata
    try:
        return api_call("sendMessage", payload)
    except Exception as e:
        print("⚠️ خطا در ارسال پیام:", e)
        return None


def get_chat(chat_id):
    try:
        data = api_call("getChat", {"chat_id": chat_id}) or {}
        return data.get("chat", data) if isinstance(data, dict) else {}
    except Exception as e:
        print("⚠️ خطا در دریافت اطلاعات چت:", e)
        return {}


def send(chat_id, text, keypad=None, metadata=None):
    send_message(chat_id, text, chat_keypad=keypad, chat_keypad_type="New" if keypad else None, metadata=metadata)


# ------------------------- ساخت کیبورد (دو‌ستونه، سایز استاندارد) -------------------------
def build_keypad(rows_texts):
    """rows_texts مثل [["دکمه۱", "دکمه۲"], ["دکمه۳"]] هر ساب‌لیست یک ردیفه.
    resize_keyboard=True + دو دکمه در هر ردیف => سایز استاندارد و کوچیک‌تر
    (دقیقاً مثل نمونه‌ای که فرستادی)، نه تمام‌عرض صفحه."""
    rows = []
    for i, row in enumerate(rows_texts):
        buttons = [
            {"id": f"btn_{i}_{j}", "type": "Simple", "button_text": t}
            for j, t in enumerate(row)
        ]
        rows.append({"buttons": buttons})
    return {"rows": rows, "resize_keyboard": True}


# ------------------------- متن و دکمه‌های دوزبانه -------------------------
BUTTON_TEXT = {
    "fa": {
        "my_info": "👤 اطلاعات من",
        "anon_msg": "✉️ پیغام ناشناس",
        "about": "ℹ️ درباره اُ",
        "channels": "📢 کانال های اُ",
        "cancel": "❌ لغو",
        "change_lang": "🌐 تغییر زبان",
        "back": "→ بازگشت",
    },
    "en": {
        "my_info": "👤 My Info",
        "anon_msg": "✉️ Anonymous Message",
        "about": "ℹ️ About O",
        "channels": "📢 O Channels",
        "cancel": "❌ Cancel",
        "change_lang": "🌐 Change Language",
        "back": "→ Back",
    },
}

WELCOME_TEXT = {
    "fa": "از منوی زیر انتخاب کنید:",
    "en": "Please choose from the menu below:",
}

FALLBACK_TEXT = {
    "fa": "لطفاً از دکمه‌های پایین صفحه استفاده کن 🙏",
    "en": "Please use the buttons below 🙏",
}

ANON_SENT_OK = {
    "fa": "✅ پیامت ارسال شد.",
    "en": "✅ Your message was sent.",
}

ANON_CANCELLED = {
    "fa": "❌ ارسال پیغام ناشناس لغو شد.",
    "en": "❌ Anonymous message cancelled.",
}

ANON_COOLDOWN_MSG = {
    "fa": lambda s: f"⏳ لطفاً {s} ثانیه دیگر دوباره امتحان کن.",
    "en": lambda s: f"⏳ Please wait {s} more second(s) and try again.",
}

LANG_PROMPT = "🌐 زبان خود را انتخاب کنید:\n🌐 Please select your language:"

ABOUT_CODE_BLOCK = (
    "const me = {\n"
    '  "status":"online🟢",\n'
    '  "user_info": {\n'
    '    "Name":"soras",\n'
    '    "nickName":none,\n'
    '    "Age":"none",\n'
    '    "City":None,\n'
    '    "Skills":"who can know ?",\n'
    '    "userName":" @CD_3443 @Felsoph -Offline⚫️ @Pv_SoRaS t.me/codakey",\n'
    '    "Channel":" @codakey @info_cia \n'
    "‌ t.me/aVaReGei\"\n"
    "  }\n"
    "}"
)

CHANNEL_LINKS_RUBIKA = ["RuBiKa.ir/codakey", "RuBiKa.ir/info_cia"]
CHANNEL_LINKS_TELEGRAM = ["T.me/aVaReGei", "T.me/GHoZaSTeH", "T.me/sRsSec"]


def lang_keypad():
    return build_keypad([["🇮🇷 فارسی", "🇬🇧 English"]])


def main_keypad(lang: str):
    t = BUTTON_TEXT[lang]
    return build_keypad([
        [t["my_info"], t["anon_msg"]],
        [t["channels"], t["about"]],
        [t["change_lang"]],
    ])


def cancel_keypad(lang: str):
    return build_keypad([[BUTTON_TEXT[lang]["cancel"]]])


def action_from_text(text: str, lang: str):
    for action, label in BUTTON_TEXT[lang].items():
        if text == label:
            return action
    return None


# ------------------------- ساخت متن‌های فرمت‌شده (متن + متادیتا) -------------------------
def anon_prompt_message(lang: str):
    text = (
        "پیغامت رو در یک قالب کوتاه و مختصر مطرح کن\nمیشنوم ."
        if lang == "fa"
        else "Keep your message short and to the point.\nI'm listening."
    )
    return text, make_meta(text, quote_parts=[text])


def info_message(sender_id: str, username: str, chat_id: str, name: str, lang: str):
    if lang == "fa":
        text = (
            "◎ اطلاعات شما 👤\n\n"
            f"• نام: {name}\n\n"
            f"• گوید:\n{sender_id}\n\n"
            f"• شناسه:\n{username}\n\n"
            f"• شناسه چت:\n{chat_id}"
        )
    else:
        text = (
            "◎ Your Info 👤\n\n"
            f"• Name: {name}\n\n"
            f"• GUID:\n{sender_id}\n\n"
            f"• ID:\n{username}\n\n"
            f"• Chat ID:\n{chat_id}"
        )
    meta = make_meta(text, mono_parts=[sender_id, username, chat_id], quote_parts=[sender_id, username, chat_id])
    return text, meta


def about_message(lang: str):
    intro = "ℹ️ درباره اُ\n\n𝙸𝚗 𝚝𝚑𝚎 𝚗𝚊𝚖𝚎 𝚘𝚏 𝙶𝚘𝙳\n\n" if lang == "fa" else "ℹ️ About O\n\n𝙸𝚗 𝚝𝚑𝚎 𝚗𝚊𝚖𝚎 𝚘𝚏 𝙶𝚘𝙳\n\n"
    text = intro + ABOUT_CODE_BLOCK
    return text, make_meta(text, quote_parts=[ABOUT_CODE_BLOCK])


def channels_message(lang: str):
    header = "📢 کانال‌های اُ" if lang == "fa" else "📢 O Channels"
    text = (
        f"{header}\n\n"
        "🔹 Rubika\n" + "\n".join(CHANNEL_LINKS_RUBIKA) + "\n\n"
        "🔹 Telegram\n" + "\n".join(CHANNEL_LINKS_TELEGRAM)
    )
    return text, make_meta(text, quote_parts=CHANNEL_LINKS_RUBIKA + CHANNEL_LINKS_TELEGRAM)


def anon_forward_message(user_text: str):
    text = "📩 پیام ناشناس جدید:\n\n" + user_text
    return text, make_meta(text, quote_parts=[user_text])


# ------------------------- دریافت اطلاعات کاربر -------------------------
def build_info_text(sender_id: str, chat_id: str, lang: str):
    name = "نامشخص" if lang == "fa" else "Unknown"
    username = "ندارد" if lang == "fa" else "None"
    chat = get_chat(chat_id)
    first = chat.get("first_name") or ""
    last = chat.get("last_name") or ""
    joined = f"{first} {last}".strip()
    if joined:
        name = joined
    uname = chat.get("username")
    if uname:
        username = f"@{uname}"
    return info_message(sender_id, username, chat_id, name, lang)


# ------------------------- استخراج داده از آپدیت (دیکشنری خام JSON) -------------------------
def extract_message(update: dict):
    update_type = update.get("type", "NewMessage")
    chat_id = update.get("chat_id")

    new_message = update.get("new_message") or {}
    text = new_message.get("text")
    sender_id = new_message.get("sender_id")
    message_id = new_message.get("message_id")

    if text is None:
        text = update.get("text")
    if sender_id is None:
        sender_id = update.get("sender_id")
    if message_id is None:
        message_id = update.get("message_id")

    return update_type, chat_id, sender_id, message_id, text


# ------------------------- پردازش هر آپدیت -------------------------
def process_update(update: dict):
    update_type, chat_id, sender_id, message_id, text = extract_message(update)
    if not chat_id or text is None:
        return
    text = text.strip()

    # ---- شروع بات ----
    if update_type == "StartedBot" or text == "/start":
        waiting_for_anon.discard(sender_id)
        send(chat_id, LANG_PROMPT, lang_keypad())
        return

    # ---- انتخاب زبان ----
    if text == "🇮🇷 فارسی":
        user_lang[sender_id] = "fa"
        send(chat_id, WELCOME_TEXT["fa"], main_keypad("fa"))
        return
    if text == "🇬🇧 English":
        user_lang[sender_id] = "en"
        send(chat_id, WELCOME_TEXT["en"], main_keypad("en"))
        return

    lang = user_lang.get(sender_id, "fa")

    # ---- کاربر در حالت انتظار پیغام ناشناس است ----
    if sender_id in waiting_for_anon:
        if text == BUTTON_TEXT[lang]["cancel"]:
            waiting_for_anon.discard(sender_id)
            send(chat_id, ANON_CANCELLED[lang], main_keypad(lang))
            return

        now = datetime.now().timestamp()
        last = last_anon_time.get(sender_id, 0)
        remaining = ANON_COOLDOWN_SECONDS - (now - last)
        if remaining > 0:
            send(chat_id, ANON_COOLDOWN_MSG[lang](int(remaining) + 1))
            return

        waiting_for_anon.discard(sender_id)
        last_anon_time[sender_id] = now
        fwd_text, fwd_meta = anon_forward_message(text)
        result = send_message(ANON_TARGET_CHAT_ID, fwd_text, metadata=fwd_meta)
        if result is None:
            print("⚠️ ارسال پیام ناشناس به ANON_TARGET_CHAT_ID ناموفق بود (خطای دقیق بالای همین خط).")
        send(chat_id, ANON_SENT_OK[lang], main_keypad(lang))
        return

    # ---- دکمه‌های منوی اصلی ----
    action = action_from_text(text, lang)
    if action is None:
        send(chat_id, FALLBACK_TEXT[lang])
        return

    if action == "my_info":
        info_text, info_meta = build_info_text(sender_id, chat_id, lang)
        send(chat_id, info_text, main_keypad(lang), info_meta)

    elif action == "anon_msg":
        now = datetime.now().timestamp()
        last = last_anon_time.get(sender_id, 0)
        remaining = ANON_COOLDOWN_SECONDS - (now - last)
        if remaining > 0:
            send(chat_id, ANON_COOLDOWN_MSG[lang](int(remaining) + 1))
            return
        waiting_for_anon.add(sender_id)
        prompt_text, prompt_meta = anon_prompt_message(lang)
        send(chat_id, prompt_text, cancel_keypad(lang), prompt_meta)

    elif action == "about":
        about_text, about_meta = about_message(lang)
        send(chat_id, about_text, main_keypad(lang), about_meta)

    elif action == "channels":
        ch_text, ch_meta = channels_message(lang)
        send(chat_id, ch_text, main_keypad(lang), ch_meta)

    elif action == "change_lang":
        send(chat_id, LANG_PROMPT, lang_keypad())


# ------------------------- اجرای بات (polling) -------------------------
def main():
    print("✅ بات روشن شد و منتظر پیام‌هاست (حالت polling، فقط requests)...")
    offset_id = load_state()
    if offset_id:
        print("🔄 وضعیت قبلی از فایل بازیابی شد؛ کاربرها زبانشون رو دوباره انتخاب نمی‌کنن.")
    else:
        # اولین اجرای این فایل: فقط offset فعلی رو می‌گیریم، بدون پردازش
        # بک‌لاگ قدیمی، تا پیام‌های قبلی دوباره برای کاربرها ارسال نشن.
        try:
            _, offset_id = get_updates(limit=10)
            save_state(offset_id)
            print("⏭️ بک‌لاگ قدیمی رد شد؛ از همین لحظه به بعد پیام‌ها پردازش می‌شن.")
        except Exception as e:
            print("⚠️ خطا در مقداردهی اولیه‌ی offset:", e)

    while True:
        try:
            updates, next_offset_id = get_updates(limit=10, offset_id=offset_id)
            if next_offset_id:
                offset_id = next_offset_id

            for update in updates:
                _, _, _, message_id, _ = extract_message(update)
                if message_id:
                    if message_id in seen_message_ids:
                        continue
                    seen_message_ids.add(message_id)
                    if len(seen_message_ids) > 1000:
                        seen_message_ids.clear()
                try:
                    process_update(update)
                except Exception as e:
                    print("⚠️ خطا در پردازش یک آپدیت:", e)
                    print("محتوای آپدیت برای دیباگ:", update)

            save_state(offset_id)

        except requests.exceptions.RequestException as e:
            print("⚠️ خطای شبکه/اتصال:", e)
        except Exception as e:
            print("⚠️ خطا در دریافت آپدیت‌ها:", e)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
    
