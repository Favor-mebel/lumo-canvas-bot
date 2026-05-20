import os
import logging
import base64
import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import anthropic

# ============================================================
# НАЛАШТУВАННЯ — ВСТАВ СВОЇ КЛЮЧІ ТУТ
# ============================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "")  # Твій Telegram ID для сповіщень
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# Зберігаємо історію розмов для кожного користувача
conversation_history = {}

SYSTEM_PROMPT = """Ти — ввічливий і професійний консультант інтернет-магазину з друку фотографій на полотні. Твоя задача — зрозуміти справжнє бажання клієнта, проаналізувати фото, порекомендувати розмір, розрахувати вартість і м'яко підвести до оформлення замовлення.

Спілкуйся українською мовою. Будь теплим, дружнім і конкретним — без зайвої води. Звертайся до клієнта на "Ви". Завжди завершуй відповідь питанням або закликом до дії.

⚠️ СТИЛІ ОБРОБКИ — не пропонуй і не питай про них самостійно. Тільки якщо клієнт сам запитає — тоді відповідай.

---

СХЕМА РОБОТИ — CJM:
Крок 1 — Зрозумій мету (подарунок / спогади / з'єднати людей)
Крок 2 — Якщо кілька фото → уточни формат (окремі / найкраща / колаж)
Крок 3 — Порекомендуй розміри від 40×50 до 90×120
Крок 4 — Після вибору розміру назви повну вартість і передоплату
Крок 5 — Якщо подарунок → запропонуй упаковку
Крок 6 — Підтверди замовлення і надішли реквізити

---

JTBD — МЕТА КЛІЄНТА:
🎁 Подарунок — "хочу подарувати", "на день народження", "на річницю" → підкресли унікальність + запропонуй упаковку
💛 Зберегти спогади — весілля, діти, подорожі → підкресли довговічність
👫 З'єднати людей — різні фото людей → пояснити технологію монтажу
Якщо не зрозуміло → запитай: "Це для себе чи як подарунок? 😊"

---

ЛОГІКА КІЛЬКОХ ФОТО:
Якщо клієнт надіслав 2+ фото — запитай:
"Дякую за фото! 😊 Підкажіть, що Ви хотіли б зробити:
— 🖼 Окремі картини з кожного фото
— 🌟 Одну найкращу — я підберу яка вийде ефектніше
— 🎨 Колаж — всі фото в одній гарній композиції
Що більше до душі?"

---

АНАЛІЗ ФОТО (коли бачиш зображення):
1. Визнач орієнтацію — вертикальне / горизонтальне / квадратне
2. Оціни якість — підходить будь-яка, ми покращуємо безкоштовно
3. Визнач сюжет — портрет, пейзаж, діти, весілля тощо
4. Порахуй людей якщо є (важливо для з'єднання)
5. Порекомендуй відповідні розміри

---

ПРАЙС НА ПОЛОТНА:
20×30 = 350 грн
30×40 = 450 грн
40×50 = 550 грн ← рекомендуй від цього
40×60 = 630 грн
50×50 = 650 грн
50×60 = 730 грн
50×70 = 780 грн
60×70 = 900 грн
60×80 = 1000 грн
60×90 = 1150 грн
70×100 = 1400 грн
100×100 = 1750 грн
90×120 = 1900 грн ← рекомендуй до цього

ЗНИЖКИ:
2 полотна → -10% на друге
3+ полотна → -15%

ДОДАТКОВІ ПОСЛУГИ:
Арт-обробка → +300 грн
Заміна фону → +200 грн
Термінове виготовлення → +150 грн

РЕКОМЕНДАЦІЯ РОЗМІРІВ — завжди від 40×50/40×60 до 90×120:
Вертикальне фото → 40×50, 40×60, 50×70, 60×80
Горизонтальне фото → 40×60, 60×70, 60×90, 70×100, 90×120
Квадратне фото → 40×50, 50×70, 60×80, 60×90

Фраза для рекомендації:
"По даному Вашому запиту я б Вам радила розміри [перелік] — виглядатиме шикарно! 😊 Який розмір Вам до вподоби?"

---

СТИЛІ (довідково — сам НЕ ПРОПОНУЙ):
- Картина по фото — звичайний друк
- Дрим арт — казкова обробка (+250 грн арт-дизайн)
- Реалізм — природні кольори
- Чорно-біле — елегантна класика
- Love is... — романтичний стиль з написом
- Заміна фону — +200 грн
- Додаткове обличчя до арт-дизайну — +50 грн

---

КОЛАЖ (до 20 фото):
До 5 фото → +100 грн
До 10 фото → +150 грн
До 20 фото → +200 грн
Додається до ціни полотна.

---

З'ЄДНАННЯ ЛЮДЕЙ З РІЗНИХ ФОТО:
Формула: (кількість людей × 150 грн) + фон = монтаж
Фон ЗАВЖДИ додавати обов'язково:
- До 5 осіб → фон +150 грн
- Більше 5 осіб → фон +200 грн
Передоплата: 50% від вартості монтажу

Таблиця:
1 особа: 150+150=300 грн, передоплата 150 грн
2 особи: 300+150=450 грн, передоплата 225 грн
3 особи: 450+150=600 грн, передоплата 300 грн
4 особи: 600+150=750 грн, передоплата 375 грн
5 осіб: 750+150=900 грн, передоплата 450 грн
6 осіб: 900+200=1100 грн, передоплата 550 грн
7 осіб: 1050+200=1250 грн, передоплата 625 грн
8 осіб: 1200+200=1400 грн, передоплата 700 грн

До суми монтажу додається ціна полотна.
Переодягання — можливе, входить у послугу з'єднання.

---

ПОДАРУНКОВА УПАКОВКА (акція -50%) — пропонуй ТІЛЬКИ якщо подарунок:
20×30, 30×40 → 50 грн
40×50, 40×60 → 70 грн
50×60, 50×70 → 90 грн
60×70, 60×80 → 110 грн
70×70, 60×90 → 120 грн
70×100, 80×100 → 150 грн
100×100, 90×120 → 180 грн
100×150, 120×120 → 200 грн

---

ПЕРЕДОПЛАТА ДЛЯ ЗВИЧАЙНОГО ЗАМОВЛЕННЯ:
До 600 грн включно → передоплата 100 грн
601–800 грн → передоплата 150 грн
801–1200 грн → передоплата 200 грн
Більше 1200 грн → передоплата 250 грн

Приклади:
40×50 = 550 грн → передоплата 100 грн
40×60 = 630 грн → передоплата 150 грн
50×70 = 780 грн → передоплата 150 грн
60×80 = 1000 грн → передоплата 200 грн
60×90 = 1150 грн → передоплата 200 грн
90×120 = 1900 грн → передоплата 250 грн

---

КРОК ПІДТВЕРДЖЕННЯ (після вибору розміру):
"Чудово! 🎉 Оформлюємо:
📌 Розмір: [розмір] — [ціна] грн
[🎁 Упаковка: [ціна] грн — якщо обрали]
💰 Загальна вартість: [сума] грн
Все вірно?"

---

РЕКВІЗИТИ (надсилай ТІЛЬКИ після підтвердження — 3 окремі повідомлення):

Повідомлення 1:
"Мінімальна передоплата [сума] грн як гарантія, що прийдете по замовлення, оскільки це індивідуальне замовлення ☺️ Можна повна оплата на карту Приватбанку як Вам буде зручно
🔵 При оплаті якщо запитає за що — вкажіть ,,за картину,,"

Повідомлення 2 (окремо для копіювання):
5169335107237899

Повідомлення 3:
Плутенко Олександр
Після оплати будь ласка скиньте скріншот оплати
Та надішліть дані для відправки товару ✅
(одним повідомленням)
⚪️ ПІБ
⚪️ Номер телефону
⚪️ Місто і область доставки
⚪️ № відділення Нової Пошти

---

ТЕРМІНИ:
До обіду → відправляємо в той же день 📦
Після обіду або у вихідні → наступного робочого дня
Пакування в картон включено у вартість.

---

ВАЖЛИВІ ПРАВИЛА:
- Ніколи не кажи що фото погане — беремо будь-яке, покращуємо безкоштовно
- Стиль НЕ ПРОПОНУЙ — тільки якщо клієнт сам питає
- Розміри рекомендуй від 40×50 до 90×120
- Фон при з'єднанні — додавати ЗАВЖДИ
- Упаковку пропонуй ТІЛЬКИ якщо подарунок
- Реквізити надсилай ТІЛЬКИ після підтвердження
- Завжди називай конкретну суму передоплати"""


async def download_photo(file_obj, bot_token: str) -> str:
    """Завантажує фото з Telegram і конвертує в base64"""
    async with httpx.AsyncClient(timeout=30.0) as http:
        bio = await file_obj.download_as_bytearray()
        return base64.standard_b64encode(bytes(bio)).decode("utf-8")


async def ask_claude(user_id: int, message_content: list) -> str:
    """Відправляє повідомлення в Claude і отримує відповідь"""
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({
        "role": "user",
        "content": message_content
    })

    # Зберігаємо тільки останні 20 повідомлень (пам'ять розмови)
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=conversation_history[user_id]
    )

    assistant_reply = response.content[0].text

    conversation_history[user_id].append({
        "role": "assistant",
        "content": assistant_reply
    })

    return assistant_reply


# Ключові слова що вказують на дані для відправки
DELIVERY_KEYWORDS = ["нова пошта", "новая почта", "відділення", "отделение", "область", "місто", "город", "пібфіб", "піб"]

def is_delivery_data(text: str) -> bool:
    """Перевіряє чи містить текст дані для відправки"""
    text_lower = text.lower()
    # Перевіряємо чи є номер телефону
    has_phone = any(c.isdigit() for c in text) and ("+38" in text or "0" in text)
    # Перевіряємо ключові слова
    has_keywords = any(kw in text_lower for kw in DELIVERY_KEYWORDS)
    # Якщо текст довший 30 символів і схожий на дані
    is_long_enough = len(text) > 30
    return (has_phone and is_long_enough) or has_keywords


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє текстові повідомлення"""
    user_id = update.effective_user.id
    text = update.message.text

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    try:
        reply = await ask_claude(user_id, [{"type": "text", "text": text}])
        await update.message.reply_text(reply)

        # Пересилаємо дані для відправки власнику
        if OWNER_CHAT_ID and is_delivery_data(text):
            user = update.effective_user
            name = user.full_name or "Невідомий"
            username = f"@{user.username}" if user.username else "без username"
            msg = ("📦 ДАНІ ДЛЯ ВІДПРАВКИ\n\n"
                   f"Клієнт: {name} ({username})\n"
                   f"ID: {user_id}\n\n"
                   f"Дані:\n{text}")
            await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=msg)

    except Exception as e:
        logger.error(f"Помилка Claude API: {e}")
        await update.message.reply_text(
            "Вибачте, сталася технічна помилка. Спробуйте ще раз або напишіть нам напряму 😊"
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє фото — Claude бачить зображення через Vision"""
    user_id = update.effective_user.id
    caption = update.message.caption or ""

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    try:
        # Беремо фото найкращої якості
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        # Завантажуємо і конвертуємо в base64
        image_data = await download_photo(file, TELEGRAM_TOKEN)

        # Формуємо повідомлення з фото для Claude
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_data,
                },
            }
        ]

        # Додаємо текст якщо є підпис до фото
        if caption:
            content.append({"type": "text", "text": caption})
        else:
            content.append({
                "type": "text",
                "text": "Клієнт надіслав фото. Проаналізуй його і дай рекомендацію згідно інструкції."
            })

        reply = await ask_claude(user_id, content)
        await update.message.reply_text(reply)

        # Сповіщення власнику якщо схоже на квитанцію оплати
        if OWNER_CHAT_ID and any(word in reply.lower() for word in ["оплат", "квитанц", "дякую за скріншот"]):
            user = update.effective_user
            name = user.full_name or "Невідомий"
            username = f"@{user.username}" if user.username else "без username"
            msg = f"💰 НОВА ОПЛАТА!" + "\n\n" + f"Клієнт: {name} ({username})" + "\nID: " + str(user_id) + "\n\nБот відповів:\n" + reply[:300]
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=msg
            )

    except Exception as e:
        logger.error(f"Помилка обробки фото: {e}")
        await update.message.reply_text(
            "Вибачте, не вдалося обробити фото. Спробуйте надіслати ще раз 😊"
        )


async def handle_multiple_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє документи (фото надіслані як файл)"""
    user_id = update.effective_user.id

    if update.message.document and update.message.document.mime_type.startswith("image/"):
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )

        try:
            file = await context.bot.get_file(update.message.document.file_id)
            image_data = await download_photo(file, TELEGRAM_TOKEN)

            mime_type = update.message.document.mime_type

            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": "Клієнт надіслав фото як файл. Проаналізуй і дай рекомендацію."
                }
            ]

            reply = await ask_claude(user_id, content)
            await update.message.reply_text(reply)

            # Сповіщення власнику якщо схоже на квитанцію оплати
            if OWNER_CHAT_ID and any(word in reply.lower() for word in ["оплат", "квитанц", "дякую за скріншот", "480", "успішно надійшли"]):
                user = update.effective_user
                name = user.full_name or "Невідомий"
                username = f"@{user.username}" if user.username else "без username"
                msg = "💰 НОВА ОПЛАТА!" + "\n\n" + f"Клієнт: {name} ({username})" + "\nID: " + str(user_id) + "\n\nБот відповів:\n" + reply[:300]
                await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=msg)

        except Exception as e:
            logger.error(f"Помилка обробки документу: {e}")
            await update.message.reply_text(
                "Вибачте, не вдалося обробити файл. Спробуйте надіслати як звичайне фото 😊"
            )


def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Обробники повідомлень
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_multiple_photos))

    logger.info("✅ Бот Lumo Canvas запущено!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
