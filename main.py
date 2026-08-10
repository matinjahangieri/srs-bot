import requests, time, json, os

TOKEN = "CBFJAC0EUURCJJRDYAHDCTVZSSYCZKNDJJKCIKBOQHKDEBPAKSDJTIHPEFLZZOMG"
ADMIN_CHAT_ID = "b0JdCXS0o4d0385908ded26062d7d947"

API = f"https://botapi.rubika.ir/v3/{TOKEN}/"
OFFSET_FILE = "offset.json"

anonymous_mode = set()
next_offset_id = None


def utf16_len(s):
    return len(str(s).encode("utf-16-le")) // 2


def make_meta(text, mono_parts=None, quote_parts=None):
    meta_parts = []

    if mono_parts:
        for value in mono_parts:
            start = text.find(value)
            if start != -1:
                meta_parts.append({
                    "type": "Mono",
                    "from_index": utf16_len(text[:start]),
                    "length": utf16_len(value)
                })

    if quote_parts:
        for value in quote_parts:
            start = text.find(value)
            if start != -1:
                meta_parts.append({
                    "type": "Quote",
                    "from_index": utf16_len(text[:start]),
                    "length": utf16_len(value)
                })

    return {"meta_data_parts": meta_parts}


def load_offset():
    global next_offset_id
    if os.path.exists(OFFSET_FILE):
        try:
            with open(OFFSET_FILE, "r") as f:
                next_offset_id = json.load(f).get("next_offset_id")
        except:
            next_offset_id = None


def save_offset():
    if next_offset_id:
        with open(OFFSET_FILE, "w") as f:
            json.dump({"next_offset_id": next_offset_id}, f)


def api(method, data=None):
    if data is None:
        data = {}

    try:
        r = requests.post(API + method, json=data, timeout=20)
        print(method, r.text)
        return r.json()
    except Exception as e:
        print("API ERROR:", e)
        return None


def main_keypad():
    return {
        "rows": [
            {
                "buttons": [
                    {"id": "my_info", "type": "Simple", "button_text": "👤 اطلاعات من"},
                    {"id": "anonymous", "type": "Simple", "button_text": "✉️ پیغام ناشناس"}
                ]
            },
            {
                "buttons": [
                    {"id": "channels", "type": "Simple", "button_text": "📢 کانال‌های اُ"},
                    {"id": "about", "type": "Simple", "button_text": "ℹ️ درباره اُ"}
                ]
            }
        ],
        "resize_keyboard": True
    }


def send(chat_id, text, keypad=None, metadata=None):
    data = {"chat_id": str(chat_id), "text": text}

    if metadata:
        data["metadata"] = metadata

    if keypad:
        data["chat_keypad_type"] = "New"
        data["chat_keypad"] = keypad

    return api("sendMessage", data)


def get_chat_name(chat_id):
    res = api("getChat", {"chat_id": chat_id})
    try:
        return res["data"]["chat"]["first_name"]
    except:
        return "کاربر"


def get_updates():
    global next_offset_id

    data = {"limit": 10}
    if next_offset_id:
        data["offset_id"] = next_offset_id

    res = api("getUpdates", data)

    if not res or res.get("status") != "OK":
        return []

    result = res["data"]
    next_offset_id = result.get("next_offset_id", next_offset_id)
    save_offset()

    return result.get("updates", [])


def handle(update):
    msg = update.get("new_message") or {}
    chat_id = update.get("chat_id")
    text = msg.get("text", "") or ""
    user_guid = msg.get("sender_id", "نامشخص")

    if not chat_id:
        return

    if text == "/start":
        anonymous_mode.discard(chat_id)
        send(chat_id, "از منوی زیر انتخاب کن:", main_keypad())
        return

    if text == "👤 اطلاعات من":
        name = get_chat_name(chat_id)

        answer = f"""👤 اطلاعات من

◎ اطلاعات شما 👤

• نام: {name}

• گوید:
{user_guid}

• شناسه چت:
{chat_id}"""

        send(
            chat_id,
            answer,
            main_keypad(),
            make_meta(
                answer,
                mono_parts=[user_guid, str(chat_id)],
                quote_parts=[user_guid, str(chat_id)]
            )
        )
        return

    if text == "✉️ پیغام ناشناس":
        anonymous_mode.add(chat_id)

        answer = "پیغامت رو در یک قالب کوتاه و مختصر مطرح کن\nمیشنوم ."

        send(
            chat_id,
            answer,
            metadata=make_meta(
                answer,
                quote_parts=[answer]
            )
        )
        return

    if text == "📢 کانال‌های اُ":
        ch1 = "RuBiKa.ir/codakey"
        ch2 = "RuBiKa.ir/info_cia"

        answer = f"""📢 کانال‌های اُ

{ch1}

{ch2}"""

        send(
            chat_id,
            answer,
            main_keypad(),
            make_meta(
                answer,
                quote_parts=[ch1, ch2]
            )
        )
        return

    if text == "ℹ️ درباره اُ":
        intro = "درباره اُ\n\n𝙸𝚗 𝚝𝚑𝚎 𝚗𝚊𝚖𝚎 𝚘𝚏 𝙶𝚘𝙳\n\n"

        code_block = """const me = {
  "status":"online🟢",
  "user_info": {
    "Name":"SoRaS",
    "nickName":None,
    "Age":"23",
    "City":None,
    "Skills":"who can know ?",
    "userName":" @CD_3443 @Felsoph -Offline⚫️ @Pv_SoRaS t.me/Felsoph",
    "Channel":" @codakey @info_cia 
‌ t.me/aVaReGei t.me/nouboqe"
  }
}"""

        full_text = intro + code_block

        send(
            chat_id,
            full_text,
            main_keypad(),
            make_meta(
                full_text,
                quote_parts=[code_block]
            )
        )
        return

    if chat_id in anonymous_mode and text.strip():
        answer = "✉️ پیام ناشناس جدید:\n\n" + text

        result = send(
            ADMIN_CHAT_ID,
            answer,
            metadata=make_meta(
                answer,
                quote_parts=[text]
            )
        )

        print("ANON SEND RESULT:", result)

        send(chat_id, "✅ پیامت ارسال شد.", main_keypad())
        anonymous_mode.discard(chat_id)


load_offset()

if not next_offset_id:
    old = api("getUpdates", {"limit": 10})
    if old and old.get("status") == "OK":
        next_offset_id = old["data"].get("next_offset_id")
        save_offset()

print("Bot is running...")

while True:
    try:
        for update in get_updates():
            handle(update)
        time.sleep(1)
    except Exception as e:
        print("MAIN ERROR:", e)
        time.sleep(3)
