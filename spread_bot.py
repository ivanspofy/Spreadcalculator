"""
Telegram-бот для расчёта спреда и PnL
Библиотека: pyTelegramBotAPI (telebot)
Токен берётся из переменной окружения BOT_TOKEN
"""

import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# ─────────────────────────────────────────────
#  Токен из переменной окружения
#  На Render: Settings → Environment → BOT_TOKEN
# ─────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")

bot = telebot.TeleBot(TOKEN)

# ══════════════════════════════════════════════
#  Хранилище состояний пользователей (вместо FSM)
#  { user_id: { "step": "buy"/"sell"/"size", "buy": float, "sell": float } }
# ══════════════════════════════════════════════
user_state: dict = {}


# ══════════════════════════════════════════════
#  Клавиатуры
# ══════════════════════════════════════════════
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📊 Рассчитать спред"))
    kb.add(KeyboardButton("❓ Помощь"))
    return kb


def cancel_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ Отмена"))
    return kb


# ══════════════════════════════════════════════
#  Хендлеры
# ══════════════════════════════════════════════

@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_state.pop(message.from_user.id, None)
    bot.send_message(
        message.chat.id,
        "👋 <b>Привет!</b> Я бот для расчёта торгового спреда и PnL.\n\n"
        "Нажми <b>📊 Рассчитать спред</b>, чтобы начать.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == "❓ Помощь")
def cmd_help(message):
    bot.send_message(
        message.chat.id,
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Нажми «📊 Рассчитать спред»\n"
        "2️⃣ Введи цену покупки <i>(Buy)</i>\n"
        "3️⃣ Введи цену продажи <i>(Sell)</i>\n"
        "4️⃣ Введи размер позиции <i>(Size)</i>\n"
        "   — если не нужно, введи <code>-</code>\n\n"
        "<b>Формулы:</b>\n"
        "• Spread % = (Sell − Buy) / Buy × 100\n"
        "• PnL = (Sell − Buy) × Size",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == "❌ Отмена")
def cmd_cancel(message):
    uid = message.from_user.id
    if uid in user_state:
        user_state.pop(uid)
        bot.send_message(message.chat.id, "❌ Расчёт отменён.", reply_markup=main_keyboard())
    else:
        bot.send_message(message.chat.id, "Нечего отменять 🙂", reply_markup=main_keyboard())


@bot.message_handler(func=lambda m: m.text == "📊 Рассчитать спред")
def start_calculation(message):
    uid = message.from_user.id
    user_state[uid] = {"step": "buy"}
    bot.send_message(
        message.chat.id,
        "💰 Введи <b>цену покупки (Buy)</b>:\n<i>Пример: 100 или 1500.50</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


# ──────────────────────────────────────────────
#  Обработка пошагового ввода
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.from_user.id in user_state)
def handle_steps(message):
    uid = message.from_user.id
    state = user_state[uid]
    step = state["step"]
    raw = message.text.strip().replace(",", ".")

    # ── ШАГ 1: Buy ────────────────────────────
    if step == "buy":
        try:
            buy = float(raw)
            if buy <= 0:
                raise ValueError
        except ValueError:
            bot.send_message(
                message.chat.id,
                "⚠️ Некорректное значение. Введи числовую цену покупки.\n<i>Пример: 100 или 1500.50</i>",
                parse_mode="HTML",
            )
            return
        state["buy"] = buy
        state["step"] = "sell"
        bot.send_message(
            message.chat.id,
            f"✅ Buy: <b>{buy:,.4f}</b>\n\n💸 Теперь введи <b>цену продажи (Sell)</b>:",
            parse_mode="HTML",
        )

    # ── ШАГ 2: Sell ───────────────────────────
    elif step == "sell":
        try:
            sell = float(raw)
            if sell <= 0:
                raise ValueError
        except ValueError:
            bot.send_message(
                message.chat.id,
                "⚠️ Некорректное значение. Введи числовую цену продажи.",
                parse_mode="HTML",
            )
            return
        state["sell"] = sell
        state["step"] = "size"
        bot.send_message(
            message.chat.id,
            f"✅ Sell: <b>{sell:,.4f}</b>\n\n📦 Введи <b>размер позиции (Size)</b>:\n"
            "<i>Если хочешь пропустить — введи</i> <code>-</code>",
            parse_mode="HTML",
        )

    # ── ШАГ 3: Size + расчёт ──────────────────
    elif step == "size":
        if raw == "-":
            size = 1.0
            size_label = "1 <i>(по умолчанию)</i>"
        else:
            try:
                size = float(raw)
                if size <= 0:
                    raise ValueError
                size_label = f"{size:,.4f}"
            except ValueError:
                bot.send_message(
                    message.chat.id,
                    "⚠️ Некорректное значение. Введи положительное число или <code>-</code> для пропуска.",
                    parse_mode="HTML",
                )
                return

        buy: float = state["buy"]
        sell: float = state["sell"]

        spread_pct = (sell - buy) / buy * 100
        pnl = (sell - buy) * size

        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        spread_emoji = "📈" if spread_pct >= 0 else "📉"

        result = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "     📊 <b>РЕЗУЛЬТАТ РАСЧЁТА</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 <b>Buy:</b>       <code>{buy:,.4f}</code>\n"
            f"💸 <b>Sell:</b>      <code>{sell:,.4f}</code>\n"
            f"📦 <b>Size:</b>      <code>{size_label}</code>\n\n"
            f"{spread_emoji} <b>Spread %:</b>  <code>{spread_pct:+.4f}%</code>\n"
            f"{pnl_emoji} <b>PnL:</b>       <code>{pnl:+,.4f}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

        user_state.pop(uid)
        bot.send_message(message.chat.id, result, parse_mode="HTML", reply_markup=main_keyboard())


# ──────────────────────────────────────────────
#  Fallback — всё остальное
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.send_message(
        message.chat.id,
        "Не понимаю эту команду 🤔\nНажми <b>📊 Рассчитать спред</b> или <b>❓ Помощь</b>.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


# ══════════════════════════════════════════════
#  Точка входа
# ══════════════════════════════════════════════
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
