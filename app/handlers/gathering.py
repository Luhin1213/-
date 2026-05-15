# app/handlers/gathering.py
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from app.database.queries import (
    is_admin, create_gathering, get_active_gatherings,
    get_gathering, cancel_gathering, signup_gathering,
    cancel_signup, get_gathering_signups,
    get_all_linked_telegram_ids, get_player_by_linked_user,
    get_user_language, save_gathering_message_id,
)
from app.keyboards.main_kb import (
    gathering_signup_keyboard, active_gatherings_keyboard,
    admin_gathering_keyboard,
)
from app.handlers.group_handler import (
    post_gathering_to_group, cancel_gathering_in_group,
)
from app.utils.i18n import ui

logger = logging.getLogger(__name__)
router = Router()


class GatheringCreateState(StatesGroup):
    enter_date        = State()
    enter_time        = State()
    enter_location    = State()
    enter_description = State()


@router.message(F.text.in_(["🎮 Збір", "🎮 Сбор"]))
async def gather_menu(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Тільки для адміністратора.")
        return
    lang = await get_user_language(message.from_user.id)
    b    = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=ui("gather_create", lang), callback_data="gather_create"))
    b.row(InlineKeyboardButton(text=ui("gather_active", lang), callback_data="gather_active"))
    await message.answer(
        f"🎮 <b>{ui('gather_title', lang)}</b>",
        parse_mode="HTML", reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "gather_create")
async def gather_create_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    lang = await get_user_language(callback.from_user.id)
    await callback.message.edit_text(ui("gather_enter_date", lang), parse_mode="HTML")
    await state.set_state(GatheringCreateState.enter_date)
    await callback.answer()


@router.message(GatheringCreateState.enter_date)
async def gather_date(message: Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    await state.update_data(date=message.text.strip())
    await message.answer(ui("gather_enter_time", lang), parse_mode="HTML")
    await state.set_state(GatheringCreateState.enter_time)


@router.message(GatheringCreateState.enter_time)
async def gather_time(message: Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    await state.update_data(time=message.text.strip())
    await message.answer(ui("gather_enter_loc", lang), parse_mode="HTML")
    await state.set_state(GatheringCreateState.enter_location)


@router.message(GatheringCreateState.enter_location)
async def gather_location(message: Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    await state.update_data(location=message.text.strip())
    await message.answer(ui("gather_enter_desc", lang), parse_mode="HTML")
    await state.set_state(GatheringCreateState.enter_description)


@router.message(GatheringCreateState.enter_description)
async def gather_description(message: Message, state: FSMContext, bot: Bot):
    desc = message.text.strip()
    if desc == "—":
        desc = ""
    data = await state.get_data()
    await state.clear()

    gathering_id = await create_gathering(
        game_date=data["date"], game_time=data.get("time",""),
        location=data.get("location",""), description=desc,
        created_by=message.from_user.id,
    )

    created_msg = "✅ Збір створено!" if await get_user_language(message.from_user.id) == "UA" \
                  else "✅ Сбор создан!"
    await message.answer(
        f"{created_msg}\n📅 {data['date']}  ⏰ {data.get('time','')}\n"
        f"📍 {data.get('location','')}\n\n⏳ Публікую та розсилаю...",
        parse_mode="HTML"
    )

    group_msg_id = await post_gathering_to_group(
        bot=bot, gathering_id=gathering_id,
        game_date=data["date"], game_time=data.get("time",""),
        location=data.get("location",""), description=desc, signed_count=0,
    )
    if group_msg_id:
        await save_gathering_message_id(gathering_id, group_msg_id)

    tg_ids  = await get_all_linked_telegram_ids()
    success = 0
    for tg_id in tg_ids:
        try:
            lang = await get_user_language(tg_id)
            kb   = gathering_signup_keyboard(gathering_id, lang)
            base = ui("gather_announce", lang,
                      date=data["date"], time=data.get("time",""),
                      location=data.get("location",""))
            desc_line = f"\n📝 {desc}" if desc else ""
            text = f"{base}{desc_line}\n\n{ui('gather_sign_up', lang)}"
            await bot.send_message(tg_id, text, parse_mode="HTML", reply_markup=kb)
            success += 1
        except Exception:
            pass

    await message.answer(
        f"✅ Опубліковано в «Анонси»\n✅ Оповіщення: {success} гравців"
    )


async def _update_group_message(bot: Bot, gathering_id: int):
    gathering = await get_gathering(gathering_id)
    if not gathering or not gathering.get("group_message_id"):
        return
    await post_gathering_to_group(
        bot=bot, gathering_id=gathering_id,
        game_date=gathering["game_date"], game_time=gathering.get("game_time",""),
        location=gathering.get("location",""), description=gathering.get("description",""),
        signed_count=gathering["signed_count"], max_players=gathering["max_players"],
        message_id=gathering["group_message_id"],
    )


@router.callback_query(F.data.startswith("gather_join_"))
async def gather_join(callback: CallbackQuery, bot: Bot):
    gid    = int(callback.data.split("_")[-1])
    player = await get_player_by_linked_user(callback.from_user.id)
    lang   = await get_user_language(callback.from_user.id)
    if not player:
        await callback.answer(ui("no_profile", lang), show_alert=True)
        return
    ok  = await signup_gathering(gid, player["id"])
    msg = ui("gather_joined", lang) if ok else ui("gather_already", lang)
    if ok:
        await _update_group_message(bot, gid)
    await callback.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("gather_leave_"))
async def gather_leave(callback: CallbackQuery, bot: Bot):
    gid    = int(callback.data.split("_")[-1])
    player = await get_player_by_linked_user(callback.from_user.id)
    lang   = await get_user_language(callback.from_user.id)
    if not player:
        await callback.answer(ui("no_profile", lang), show_alert=True)
        return
    await cancel_signup(gid, player["id"])
    await _update_group_message(bot, gid)
    await callback.answer(ui("gather_left", lang), show_alert=True)


@router.callback_query(F.data == "gather_active")
async def gather_active(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    lang       = await get_user_language(callback.from_user.id)
    gatherings = await get_active_gatherings()
    if not gatherings:
        await callback.message.edit_text(ui("gather_none", lang))
        await callback.answer()
        return
    await callback.message.edit_text(
        f"📋 <b>{'Активні збори' if lang=='UA' else 'Активные сборы'}:</b>",
        parse_mode="HTML",
        reply_markup=active_gatherings_keyboard(gatherings)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gather_view_"))
async def gather_view(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    gid      = int(callback.data.split("_")[-1])
    gathering = await get_gathering(gid)
    if not gathering:
        await callback.answer("Не знайдено", show_alert=True)
        return
    lang = await get_user_language(callback.from_user.id)
    await callback.message.edit_text(
        f"🎮 <b>{'Збір' if lang=='UA' else 'Сбор'} #{gid}</b>\n\n"
        f"📅 {gathering['game_date']}  ⏰ {gathering.get('game_time','')}\n"
        f"📍 {gathering.get('location','')}\n"
        f"👥 {'Записано' if lang=='UA' else 'Записано'}: "
        f"<b>{gathering['signed_count']}/{gathering['max_players']}</b>\n"
        + (f"📝 {gathering['description']}" if gathering.get("description") else ""),
        parse_mode="HTML",
        reply_markup=admin_gathering_keyboard(gid)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gather_list_"))
async def gather_list(callback: CallbackQuery):
    gid     = int(callback.data.split("_")[-1])
    lang    = await get_user_language(callback.from_user.id)
    signups = await get_gathering_signups(gid)
    if not signups:
        no_one = "Ніхто ще не записався." if lang=="UA" else "Никто ещё не записался."
        await callback.answer(no_one, show_alert=True)
        return
    title = f"👥 <b>{'Записані' if lang=='UA' else 'Записаны'} ({len(signups)}):</b>\n"
    lines = [title]
    for i, s in enumerate(signups, 1):
        lines.append(f"{i}. {s['nickname']}")
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"gather_view_{gid}"))
    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gather_cancel_"))
async def gather_cancel(callback: CallbackQuery, bot: Bot):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нема прав", show_alert=True)
        return
    gid       = int(callback.data.split("_")[-1])
    gathering = await get_gathering(gid)
    if not gathering:
        await callback.answer("Не знайдено", show_alert=True)
        return
    if gathering.get("group_message_id"):
        await cancel_gathering_in_group(bot, gathering["group_message_id"], gathering["game_date"])
    await cancel_gathering(gid)
    await callback.message.edit_text(f"❌ Збір #{gid} скасовано.")

    tg_ids = await get_all_linked_telegram_ids()
    for tg_id in tg_ids:
        try:
            lang = await get_user_language(tg_id)
            await bot.send_message(
                tg_id,
                ui("gather_cancelled", lang, date=gathering["game_date"]),
                parse_mode="HTML"
            )
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data == "gather_back")
async def gather_back(callback: CallbackQuery):
    lang       = await get_user_language(callback.from_user.id)
    gatherings = await get_active_gatherings()
    if not gatherings:
        await callback.message.edit_text(ui("gather_none", lang))
    else:
        await callback.message.edit_text(
            f"📋 <b>{'Активні збори' if lang=='UA' else 'Активные сборы'}:</b>",
            parse_mode="HTML",
            reply_markup=active_gatherings_keyboard(gatherings)
        )
    await callback.answer()
