from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, 
                           ReplyKeyboardMarkup, KeyboardButton)

#lobby

choose_game = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text='1️⃣'), KeyboardButton(text='2️⃣'), KeyboardButton(text='3️⃣')],
    [KeyboardButton(text='4️⃣'), KeyboardButton(text='5️⃣'), KeyboardButton(text='6️⃣')]
], resize_keyboard=True)

join = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Присоединиться', callback_data='join')]
])

#Survivors

theme = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='1️⃣', callback_data='surv_first_theme'),
     InlineKeyboardButton(text='2️⃣', callback_data='surv_second_theme'),
     InlineKeyboardButton(text='3️⃣', callback_data='surv_third_theme')],
    [InlineKeyboardButton(text='✏️Своя тема', callback_data='surv_own_theme'),]
])

#True or Fake

answer = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Правда', callback_data='true_answer'),
     InlineKeyboardButton(text='Ложь', callback_data='false_answer')]
])

#Random Court

role = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Подсудимый', callback_data='defendant')],
    [InlineKeyboardButton(text='Прокурор', callback_data='prosecutor')],
    [InlineKeyboardButton(text='Адвокат', callback_data='lawyer')]
], row_width=2)

#Neuro Auction

neuro_auction_giveaway = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🎁 Получить нейро', callback_data='neuro_auction_giveaway')]
])