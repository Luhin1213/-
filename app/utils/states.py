# app/utils/states.py
from aiogram.fsm.state import State, StatesGroup


class RegState(StatesGroup):
    choose_lang      = State()
    enter_nickname   = State()
    confirm_nickname = State()  # вибір зі схожих нікнеймів з таблиці


class AddChipsState(StatesGroup):
    search_player = State()
    choose_player = State()
    enter_amount  = State()
    enter_comment = State()


class SubtractChipsState(StatesGroup):
    search_player = State()
    choose_player = State()
    enter_amount  = State()
    enter_comment = State()


class GiveBonusState(StatesGroup):
    search_player     = State()
    choose_player     = State()
    choose_bonus_type = State()


class LinkPlayerState(StatesGroup):
    enter_telegram_id = State()
    enter_player_id   = State()


class AdminBetState(StatesGroup):
    choose_type      = State()
    enter_creator_no = State()
    enter_target_no  = State()
    enter_amount     = State()


class BetRednessState(StatesGroup):
    enter_amount = State()


class BetAgainstState(StatesGroup):
    choose_color  = State()
    choose_number = State()
    enter_amount  = State()


class BetSideState(StatesGroup):
    choose_color = State()
    enter_amount = State()


class SpendChooseSeatState(StatesGroup):
    enter_number = State()


class SpendSilenceState(StatesGroup):
    enter_number = State()


class SpendBlindState(StatesGroup):
    enter_number = State()


class SpendBuyRoleState(StatesGroup):
    enter_role_text = State()


class SearchPlayerState(StatesGroup):
    enter_query = State()
