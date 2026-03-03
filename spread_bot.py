"""
Telegram-бот для расчёта спреда и PnL
Библиотека: aiogram v3
Токен читается из переменной окружения BOT_TOKEN
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ─────────────────────────────────────────────
#  Токен берётся из переменной окружения
#  На Render: Settings → Environment → BOT_TOKEN
# ─────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ══════════════════════════════════════════════
#  FSM — состояния пошагового ввода
# ══════════════════════════════════════════════
class SpreadCalc(StatesGroup):
    waiting_for_buy = State()
    waiting_for_sell = State()
    waiting_for_size = State()


# ══════════════════════════════════════════════
#  Клавиатуры
# ══════════════════════════════════════════════
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Рассчитать спред")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие...",
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


# ══════════════════════════════════════════════
#  Хендлеры
# ══════════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Привет!</b> Я бот для расчёта торгового спреда и PnL.\n\n"
        "Нажми <b>📊 Рассчитать спред</b>, чтобы начать.",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    await message.answer(
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


@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять 🙂", reply_markup=main_keyboard())
        return
    await state.clear()
    await message.answer("❌ Расчёт отменён.", reply_markup=main_keyboard())


@dp.message(F.text == "📊 Рассчитать спред")
async def start_calculation(message: Message, state: FSMContext):
    await state.set_state(SpreadCalc.waiting_for_buy)
    await message.answer(
        "💰 Введи <b>цену покупки (Buy)</b>:\n<i>Пример: 100 или 1500.50</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


@dp.message(SpreadCalc.waiting_for_buy)
async def process_buy(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".")
    try:
        buy = float(raw)
        if buy <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "⚠️ Некорректное значение. Введи числовую цену покупки.\n<i>Пример: 100 или 1500.50</i>",
            parse_mode="HTML",
        )
        return
    await state.update_data(buy=buy)
    await state.set_state(SpreadCalc.waiting_for_sell)
    await message.answer(
        f"✅ Buy: <b>{buy:,.4f}</b>\n\n💸 Теперь введи <b>цену продажи (Sell)</b>:",
        parse_mode="HTML",
    )


@dp.message(SpreadCalc.waiting_for_sell)
async def process_sell(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".")
    try:
        sell = float(raw)
        if sell <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Некорректное значение. Введи числовую цену продажи.", parse_mode="HTML")
        return
    await state.update_data(sell=sell)
    await state.set_state(SpreadCalc.waiting_for_size)
    await message.answer(
        f"✅ Sell: <b>{sell:,.4f}</b>\n\n📦 Введи <b>размер позиции (Size)</b>:\n"
        "<i>Если хочешь пропустить — введи</i> <code>-</code>",
        parse_mode="HTML",
    )


@dp.message(SpreadCalc.waiting_for_size)
async def process_size(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".")
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
            await message.answer(
                "⚠️ Некорректное значение. Введи положительное число или <code>-</code> для пропуска.",
                parse_mode="HTML",
            )
            return

    data = await state.get_data()
    buy: float = data["buy"]
    sell: float = data["sell"]

    spread_pct = (sell - buy) / buy * 100
    pnl = (sell - buy) * size

    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    spread_emoji = "📈" if spread_pct >= 0 else "📉"

    result_text = (
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

    await state.clear()
    await message.answer(result_text, parse_mode="HTML", reply_markup=main_keyboard())


@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Не понимаю эту команду 🤔\nНажми <b>📊 Рассчитать спред</b> или <b>❓ Помощь</b>.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


# ══════════════════════════════════════════════
#  Точка входа
# ══════════════════════════════════════════════
async def main():
    logger.info("Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
