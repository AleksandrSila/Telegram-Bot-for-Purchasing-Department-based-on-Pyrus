# bot.py
import logging
from enum import Enum, auto

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import config
from pyrus_api import PyrusAPI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

pyrus = PyrusAPI()


class State(Enum):
    IDLE = auto()
    AWAIT_TASK_ID = auto()
    AWAIT_SEARCH_MODE = auto()
    AWAIT_SEARCH_QUERY = auto()
    TASK_SELECTED = auto()
    AWAIT_RECEIVE_COMMENT = auto()
    AWAIT_TRANSFER_COMMENT = auto()


class SearchMode(Enum):
    BY_COUNTERPARTY = auto()
    BY_AMOUNT = auto()
    BY_TITLE = auto()


user_states = {}
user_search_modes = {}
user_selected_task = {}
user_comment_buffers = {}


def set_state(user_id: int, state: State):
    user_states[user_id] = state


def get_state(user_id: int) -> State:
    return user_states.get(user_id, State.IDLE)


def reset_comment_buffer(user_id: int, mode: str):
    user_comment_buffers[user_id] = {
        "text": None,
        "photos": [],
        "mode": mode,
    }


def format_task_brief(task) -> str:
    return (
        f"Закупка #{task.id}\n"
        f"Название: {task.title or '-'}\n"
        f"Контрагент: {task.counterpart or '-'}\n"
        f"Сумма: {task.amount or '-'}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    set_state(user_id, State.IDLE)
    user_selected_task.pop(user_id, None)
    user_comment_buffers.pop(user_id, None)

    keyboard = [
        [InlineKeyboardButton("Поиск закупки", callback_data="main:search")],
        [InlineKeyboardButton("Ввести ID", callback_data="main:enter_id")],
    ]
    await update.message.reply_text(
        "Выберите закупку для оприходования или передачи.\n"
        "Введите ID или воспользуйтесь поиском.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)

    if state not in (State.AWAIT_RECEIVE_COMMENT, State.AWAIT_TRANSFER_COMMENT):
        await update.message.reply_text(
            "Сначала выберите закупку и режим Оприходовать/Передать."
        )
        return

    buf = user_comment_buffers.get(user_id)
    if not buf or not buf["text"] or not buf["photos"]:
        await update.message.reply_text(
            "Нужны и фото, и текст.\n"
            f"- текст: {'да' if buf and buf['text'] else 'нет'}\n"
            f"- фото: {'да' if buf and buf['photos'] else 'нет'}\n\n"
            "Отправьте недостающее и снова нажмите /send."
        )
        return

    task_id = user_selected_task.get(user_id)
    if not task_id:
        await update.message.reply_text("Сначала выберите закупку.")
        return

    mode = buf["mode"]
    prefix = "Оприходование" if mode == "receive" else "Передача"
    full_text = f"{prefix}:\n{buf['text']}"

    try:
        pyrus.add_comment(task_id, full_text, file_guids=buf["photos"])
    except Exception as e:
        logger.exception("Ошибка при добавлении комментария")
        await update.message.reply_text(f"Ошибка при добавлении комментария: {e}")
        return

    await update.message.reply_text("Комментарий с фото добавлен в Pyrus.")

    task = pyrus.get_task_brief(task_id)
    set_state(user_id, State.TASK_SELECTED)
    keyboard = [
        [InlineKeyboardButton("Оприходовать", callback_data="task_action:receive")],
        [InlineKeyboardButton("Передать", callback_data="task_action:transfer")],
        [InlineKeyboardButton("Назад", callback_data="task_action:back")],
    ]
    await update.message.reply_text(
        format_task_brief(task),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "main:search":
        set_state(user_id, State.AWAIT_SEARCH_MODE)
        keyboard = [
            [InlineKeyboardButton("По контрагенту", callback_data="search_mode:counterparty")],
            [InlineKeyboardButton("По сумме", callback_data="search_mode:amount")],
            [InlineKeyboardButton("По названию", callback_data="search_mode:title")],
            [InlineKeyboardButton("Назад", callback_data="main:back")],
        ]
        await query.edit_message_text(
            "Выберите тип поиска:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data == "main:enter_id":
        set_state(user_id, State.AWAIT_TASK_ID)
        await query.edit_message_text(
            "Введите ID закупки цифрами.\nДля отмены отправьте /start."
        )
    elif data == "main:back":
        set_state(user_id, State.IDLE)
        keyboard = [
            [InlineKeyboardButton("Поиск закупки", callback_data="main:search")],
            [InlineKeyboardButton("Ввести ID", callback_data="main:enter_id")],
        ]
        await query.edit_message_text(
            "Выберите закупку для оприходования или передачи.\nВведите ID или воспользуйтесь поиском.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_search_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "search_mode:counterparty":
        user_search_modes[user_id] = SearchMode.BY_COUNTERPARTY
        set_state(user_id, State.AWAIT_SEARCH_QUERY)
        await query.edit_message_text("Введите часть имени контрагента:")
    elif data == "search_mode:amount":
        user_search_modes[user_id] = SearchMode.BY_AMOUNT
        set_state(user_id, State.AWAIT_SEARCH_QUERY)
        await query.edit_message_text("Введите сумму (числом):")
    elif data == "search_mode:title":
        user_search_modes[user_id] = SearchMode.BY_TITLE
        set_state(user_id, State.AWAIT_SEARCH_QUERY)
        await query.edit_message_text("Введите часть названия сделки:")


async def handle_task_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("task_select:"):
        task_id = int(data.split(":")[1])
        task = pyrus.get_task_brief(task_id)
        if not task:
            await query.edit_message_text("Заявка не найдена.")
            return
        user_selected_task[user_id] = task_id
        set_state(user_id, State.TASK_SELECTED)

        keyboard = [
            [InlineKeyboardButton("Оприходовать", callback_data="task_action:receive")],
            [InlineKeyboardButton("Передать", callback_data="task_action:transfer")],
            [InlineKeyboardButton("Назад", callback_data="task_action:back")],
        ]
        await query.edit_message_text(
            format_task_brief(task),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("task_action:"):
        action = data.split(":")[1]

        if action == "back":
            set_state(user_id, State.IDLE)
            keyboard = [
                [InlineKeyboardButton("Поиск закупки", callback_data="main:search")],
                [InlineKeyboardButton("Ввести ID", callback_data="main:enter_id")],
            ]
            await query.edit_message_text(
                "Выберите закупку для оприходования или передачи.\nВведите ID или воспользуйтесь поиском.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        task_id = user_selected_task.get(user_id)
        if not task_id:
            await query.edit_message_text("Сначала выберите закупку.")
            return

        if action == "receive":
            set_state(user_id, State.AWAIT_RECEIVE_COMMENT)
            reset_comment_buffer(user_id, mode="receive")
            await query.edit_message_text(
                "Режим: ОПРИХОДОВАТЬ.\n"
                "Отправьте фото и текст.\n"
                "Можно одним сообщением (фото с подписью) или по отдельности.\n"
                "Когда всё готово — нажмите /send."
            )

        elif action == "transfer":
            set_state(user_id, State.AWAIT_TRANSFER_COMMENT)
            reset_comment_buffer(user_id, mode="transfer")
            await query.edit_message_text(
                "Режим: ПЕРЕДАТЬ.\n"
                "Отправьте фото и текст.\n"
                "Можно одним сообщением (фото с подписью) или по отдельности.\n"
                "Когда всё готово — нажмите /send."
            )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)

    msg = update.message
    text = msg.text or msg.caption or ""
    text = text.strip() if text else ""
    has_photo = bool(msg.photo)

    # --- режимы ОПРИХОДОВАТЬ / ПЕРЕДАТЬ: только накапливаем ---
    if state in (State.AWAIT_RECEIVE_COMMENT, State.AWAIT_TRANSFER_COMMENT):
        buf = user_comment_buffers.get(user_id)
        if not buf:
            mode = "receive" if state == State.AWAIT_RECEIVE_COMMENT else "transfer"
            reset_comment_buffer(user_id, mode)
            buf = user_comment_buffers[user_id]

        if has_photo:
            photo = msg.photo[-1]
            file = await photo.get_file()
            file_bytes = await file.download_as_bytearray()
            guid = pyrus.upload_file(file_bytes, f"{file.file_unique_id}.jpg")
            logger.info(f"Uploaded photo guid={guid}, buffer photos before: {buf['photos']}")
            buf["photos"].append(guid)
            logger.info(f"Buffer photos after: {buf['photos']}")

        if text:
            if buf["text"]:
                buf["text"] += "\n" + text
            else:
                buf["text"] = text

        await msg.reply_text(
            "Данные сохранены.\n"
            f"Сейчас в буфере: текст={'да' if buf['text'] else 'нет'}, "
            f"фото={len(buf['photos'])} шт.\n"
            "Когда всё готово — нажмите /send."
        )
        return

    # --- AWAIT_TASK_ID ---
    if state == State.AWAIT_TASK_ID:
        if not text.isdigit():
            await msg.reply_text("ID должен быть числом. Попробуйте ещё раз или введите /start.")
            return
        task_id = int(text)
        task = pyrus.get_task_brief(task_id)
        if not task:
            await msg.reply_text("Заявка не найдена или закрыта.")
            return
        user_selected_task[user_id] = task_id
        set_state(user_id, State.TASK_SELECTED)
        keyboard = [
            [InlineKeyboardButton("Оприходовать", callback_data="task_action:receive")],
            [InlineKeyboardButton("Передать", callback_data="task_action:transfer")],
            [InlineKeyboardButton("Назад", callback_data="task_action:back")],
        ]
        await msg.reply_text(
            format_task_brief(task),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- AWAIT_SEARCH_QUERY ---
    elif state == State.AWAIT_SEARCH_QUERY:
        mode = user_search_modes.get(user_id)
        if not mode:
            await msg.reply_text("Не выбран тип поиска. Нажмите /start.")
            return

        if mode == SearchMode.BY_AMOUNT:
            try:
                amount = float(text.replace(",", "."))
            except ValueError:
                await msg.reply_text("Сумма должна быть числом. Попробуйте ещё раз.")
                return
            tasks = pyrus.search_by_amount(amount)
        elif mode == SearchMode.BY_COUNTERPARTY:
            tasks = pyrus.search_by_counterparty(text)
        else:
            tasks = pyrus.search_by_title(text)

        if not tasks:
            await msg.reply_text("Ничего не найдено среди открытых закупок.")
            return

        keyboard = []
        for t in tasks[:25]:
            caption = f"#{t.id} | {t.title or '-'} | {t.counterpart or '-'} | {t.amount or ''}"
            keyboard.append(
                [InlineKeyboardButton(caption, callback_data=f"task_select:{t.id}")]
            )

        set_state(user_id, State.IDLE)
        await msg.reply_text(
            "Выберите закупку:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:
        await msg.reply_text("Нажмите /start, чтобы начать работать с закупками.")


def main():
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send", send_command))

    app.add_handler(CallbackQueryHandler(handle_main_menu_callback, pattern="^main:"))
    app.add_handler(CallbackQueryHandler(handle_search_mode_callback, pattern="^search_mode:"))
    app.add_handler(CallbackQueryHandler(handle_task_action_callback, pattern="^(task_select:|task_action:)"))

    app.add_handler(MessageHandler(~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
