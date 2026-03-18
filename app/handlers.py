import random

import regex

from aiogram import F, Router
from aiogram.types import Message
from aiogram.filters import Command
from pyexpat.errors import messages

router = Router()

import main

game = None
voted = {}

game_states = None
survivors_states = None
true_or_fake_states = None
writers_states = None
emoji_battle_states = None
random_court_states = None
neuro_auction_states = None


#lobby

@router.message(Command('help'))
async def create_lobby(message: Message):
    import main

    await main.send_safe(chat_id=message.chat.id, text='💾Команды:\n\n/lobby - Создать лобби\n/delete_lobby - '
                                                       'Расформировать лобби (только для лидера)')


@router.message(Command('lobby'))
async def create_lobby(message: Message):
    import main

    if main.lobby is not None:
        await main.send_safe(chat_id=message.chat.id, text='Лобби уже создано')
        return

    main.lobby = main.Lobby(
        chat_id=message.chat.id,
        leader=message.from_user
    )
    await main.send_safe(chat_id=message.chat.id, text='Лобби создано')
    main.rate_limiter = main.SimpleRateLimiter(message.chat.id)
    await main.lobby.refresh_message()


@router.callback_query(F.data == 'join')
async def join_lobby(callback: Message):
    import main

    if main.lobby is None:
        await callback.answer(text='Лобби не существует')
        return

    if callback.from_user in main.lobby.participants:
        await callback.answer(text=f'❗Ты уже в лобби')
        return

    if not (
            main.survivors_game is None and main.true_or_fake_game is None and main.writers_game is None
            and main.emoji_battle_game is None and main.random_court_game is None and
            main.neuro_auction_game is None):
        await callback.answer(text=f"❗Дождись окончания игры")
        return

    main.lobby.participants.append(callback.from_user)
    await callback.answer(text='Ты присоединился к лобби')
    await main.lobby.refresh_message()


@router.message(Command('join'))
async def join_lobby(message: Message):
    import main

    if main.lobby is None:
        await main.send_safe(chat_id=message.chat.id, text='Лобби не существует')
        return

    if message.from_user in main.lobby.participants:
        await main.send_safe(chat_id=message.chat.id, text=f'❗{message.from_user.full_name}, ты уже в лобби')
        return

    if not (
            main.survivors_game is None and main.true_or_fake_game is None and main.writers_game is None
            and main.emoji_battle_game is None and main.random_court_game is None and
            main.neuro_auction_game is None):
        await main.send_safe(chat_id=message.chat.id, text=f"❗{message.from_user.full_name}, дождись окончания игры")
        return

    main.lobby.participants.append(message.from_user)
    await main.send_safe(chat_id=message.chat.id, text='Ты присоединился к лобби')
    await main.lobby.refresh_message()


@router.message(Command('start'))
async def start_game(message: Message):
    import main
    global game_states

    if main.lobby is None:
        await main.send_safe(chat_id=message.chat.id, text='❌Лобби не существует')
        return

    if message.from_user != main.lobby.leader:
        await main.send_safe(chat_id=message.chat.id, text='❗Ты не лидер лобби')
        return

    main.survivors_game = None
    main.true_or_fake_game = None
    main.writers_game = None
    main.emoji_battle_game = None
    main.random_court_game = None
    main.neuro_auction_game = None
    main.players = main.lobby.participants
    game_states = "waiting_for_game"
    await main.lobby.choose_game()


async def choose_game(message: Message):
    import main
    global game
    global voted
    global game_states
    global true_or_fake_states
    global writers_states
    global emoji_battle_states
    global random_court_states
    global neuro_auction_states

    number_map = dict(
        list({'1️⃣': '1', '2️⃣': '2', '3️⃣': '3', '4️⃣': '4', '5️⃣': 5, '6️⃣': 6}.items())[:len(main.games)])

    if message.text not in number_map:
        await main.send_safe(chat_id=message.chat.id, text='❗Неккоректный номер игры')
        return

    if message.from_user in voted:
        await main.send_safe(chat_id=message.chat.id, text='❗Ты уже проголосовал')
        return

    voted[message.from_user] = number_map[message.text]
    await main.send_safe(chat_id=message.chat.id,
                         text=f'✅ {message.from_user.first_name} проголосовал за игру {message.text}')
    if len(voted) == len(main.lobby.participants):
        game_states = None
        votes = list(map(int, voted.values()))
        max_votes = max(votes, key=votes.count)
        main.lobby.game = main.games[max_votes - 1]
        voted = {}

        await main.send_safe(
            chat_id=message.chat.id,
            text=f'👥✅ Все проголосовали\n\nВыбрана игра: <b>{main.lobby.game}</b>'
        )

        game = main.lobby.game

        if game == 'Survivors':
            main.survivors_game = main.SurvivorsGame(main.lobby.chat_id)
            await main.survivors_game.start_game()
            await main.survivors_game.choose_theme()

        elif game == 'True or Fake':
            main.true_or_fake_game = main.TrueOrFakeGame(main.lobby.chat_id)
            await main.true_or_fake_game.start_game()
            await main.true_or_fake_game.choose_thematic()
            true_or_fake_states = "waiting_for_thematic"

        elif game == 'Writers':
            main.writers_game = main.WritersGame(main.lobby.chat_id)
            await main.writers_game.start_game()
            await main.writers_game.write_history()

        elif game == 'Emoji Battle':
            main.emoji_battle_game = main.EmojiBattleGame(main.lobby.chat_id)
            await main.emoji_battle_game.start_game()
            await main.emoji_battle_game.start_round()

        elif game == 'Random Court':
            if len(main.players) == 3:
                main.random_court_game = main.RandomCourtGame(main.lobby.chat_id)
                await main.random_court_game.start_game()
            else:
                await main.send_safe(chat_id=message.chat.id, text="Должно быть ровно 3 игрока! Голосуйте заново.")
                game_states = "waiting_for_game"

        elif game == 'Neuro Auction':
            main.neuro_auction_game = main.NeuroAuctionGame(main.lobby.chat_id)
            await main.neuro_auction_game.start_game()
            await main.neuro_auction_game.start_round()


@router.message(Command('delete_lobby'))
async def delete_lobby(message: Message):
    import main
    global game
    global voted
    global game_states
    global true_or_fake_states
    global writers_states
    global emoji_battle_states
    global random_court_states
    global neuro_auction_states
    global game_states
    global game

    if main.lobby is None:
        await main.send_safe(chat_id=message.chat.id, text="❗В этом чате нет созданных лобби")
        return

    if message.from_user != main.lobby.leader:
        await main.send_safe(chat_id=message.chat.id, text=f"❗{message.from_user.full_name}, Вы не лидер лобби")
        return

    leader = main.lobby.leader.full_name
    main.lobby = None
    main.survivors_game = None
    main.true_or_fake_game = None
    main.writers_game = None
    main.emoji_battle_game = None
    main.random_court_game = None
    main.neuro_auction_game = None
    true_or_fake_states = ''
    writers_states = ''
    emoji_battle_states = ''
    random_court_states = ''
    neuro_auction_states = ''
    game_states = ''
    game = ''
    voted = {}
    await main.send_safe(chat_id=message.chat.id, text=f"✅Лидер {leader} расформировал лобби")


#Survivors

@router.callback_query(F.data == 'surv_first_theme')
async def first_theme(callback: Message):
    import main
    global survivors_states

    if main.survivors_game is None:
        await callback.answer("❗Игра неактивна")
        return

    if callback.from_user.id != main.survivors_game.player_turn.id:
        await callback.answer('❗Не ты выбираешь тему')
        return

    await callback.answer('✅ Тема выбрана')

    main.survivors_game.current_theme = main.survivors_game.current_themes[0]
    await main.survivors_game.confirm_theme()
    survivors_states = "waiting_for_strategies"


@router.callback_query(F.data == 'surv_second_theme')
async def second_theme(callback: Message):
    import main
    global survivors_states

    if main.survivors_game is None:
        await callback.answer("❗Игра неактивна")
        return

    if callback.from_user != main.survivors_game.player_turn:
        await callback.answer('❗Не ты выбираешь тему')
        return

    await callback.answer('✅ Тема выбрана')

    main.survivors_game.current_theme = main.survivors_game.current_themes[1]
    await main.survivors_game.confirm_theme()
    survivors_states = "waiting_for_strategies"


@router.callback_query(F.data == 'surv_third_theme')
async def third_theme(callback: Message):
    import main
    global survivors_states

    if main.survivors_game is None:
        await callback.answer("❗Игра неактивна")
        return

    if callback.from_user != main.survivors_game.player_turn:
        await callback.answer('❗Не ты выбираешь тему')
        return

    await callback.answer('✅ Тема выбрана')

    main.survivors_game.current_theme = main.survivors_game.current_themes[2]
    await main.survivors_game.confirm_theme()
    survivors_states = "waiting_for_strategies"


@router.callback_query(F.data == 'surv_own_theme')
async def own_theme(callback: Message):
    import main
    global survivors_states

    if main.survivors_game is None:
        await callback.answer("❗Игра неактивна")
        return

    if callback.from_user != main.survivors_game.player_turn:
        await callback.answer('❗Не ты выбираешь тему')
        return

    survivors_states = "waiting_for_theme"
    await main.survivors_game.own_theme()


async def receive_theme(message: Message):
    import main
    global survivors_states

    if message.chat.id != main.survivors_game.chat_id:
        return

    if message.from_user != main.survivors_game.player_turn:
        await main.send_safe(chat_id=message.chat.id, text=f'❗{message.from_user.first_name}, не ты выбираешь тему')
        return

    main.survivors_game.current_theme = message.text
    try:
        await message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    await main.survivors_game.confirm_theme()
    survivors_states = "waiting_for_strategies"


async def receive_strategy(message: Message):
    import main
    global survivors_states

    if message.chat.id != main.survivors_game.chat_id:
        return

    if message.from_user not in main.survivors_game.players:
        return

    if message.from_user.id in main.survivors_game.strategies:
        return

    if message.text is None:
        return

    main.survivors_game.strategies[message.from_user.id] = message.text
    await main.survivors_game.update_states()
    try:
        await message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    await main.send_safe(chat_id=message.chat.id, text=f'✅ {message.from_user.first_name}, стратегия принята!')
    if len(main.survivors_game.strategies) == len(main.survivors_game.players):
        await main.send_safe(chat_id=message.chat.id, text='👥✅ Все стратегии приняты, начинаем оценку!')
        survivors_states = None
        await main.survivors_game.evaluate_strategies_message()


#True or Fake

async def receive_thematic(message: Message):
    import main
    global true_or_fake_states

    if message.chat.id != main.true_or_fake_game.chat_id:
        return

    if message.from_user != main.lobby.leader:
        await main.send_safe(chat_id=message.chat.id, text=f'❗{message.from_user.full_name}, не ты выбираешь тематику')
        return

    main.true_or_fake_game.thematic = message.text
    true_or_fake_states = None
    try:
        await message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")
    await main.send_safe(chat_id=message.chat.id,
                         text=f"✅ Выбрана тематика <b>{message.text}</b>\n\n🕑Формируем факты...")
    await main.true_or_fake_game.forming_facts()
    await main.true_or_fake_game.write_fact()


async def answer(callback: Message, true_or_fake):
    import main
    global true_or_fake_states

    if main.true_or_fake_game is None:
        await callback.answer("❗Игра неактивна")
        return

    if callback.from_user not in main.true_or_fake_game.players:
        await callback.answer('❗Ты не в лобби')
        return

    if callback.from_user.id in main.true_or_fake_game.votes:
        await callback.answer('❗Ты уже проголосовал')
        return

    await callback.answer('✅ Ты проголосовал')

    main.true_or_fake_game.votes[callback.from_user.id] = true_or_fake
    await main.bot.send_message(chat_id=main.lobby.chat_id,
                                text=f'✅ {callback.from_user.first_name} проголосовал')
    if len(main.true_or_fake_game.votes) == len(main.true_or_fake_game.players):
        await main.bot.send_message(chat_id=main.lobby.chat_id,
                                    text='👥✅ Все проголосовали, начинаем проверку!')
        true_or_fake_states = None
        await main.true_or_fake_game.evaluate_votes()


@router.callback_query(F.data == 'true_answer')
async def true_answer(callback: Message):
    await answer(callback, True)


@router.callback_query(F.data == 'false_answer')
async def true_answer(callback: Message):
    await answer(callback, False)


#Writers


async def receive_sentence(message: Message):
    import main
    global writers_states

    if message.chat.id != main.writers_game.chat_id:
        return

    if message.from_user != main.writers_game.player_turn:
        await main.send_safe(chat_id=message.chat.id,
                             text=f'❗{message.from_user.first_name}, не ты выбираешь предложение')
        return

    text = message.text.strip()
    if text[-1] != '.':
        text += '.'
    if not text[0].isupper():
        text = text[0].upper() + text[1:]

    main.writers_game.last_sentence = text
    await main.writers_game.clear_last_sentence()
    writers_states = None
    try:
        await message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    await main.writers_game.confirm_sentence()


#Emoji Battle


async def receive_emoji(message: Message):
    import main
    global emoji_battle_states

    if message.chat.id != main.emoji_battle_game.chat_id:
        return

    if main.emoji_battle_game.emojies[message.from_user.full_name] != "":
        await main.send_safe(chat_id=message.chat.id,
                             text=f"❗{message.from_user.first_name}, ты уже прислал набор эмодзи")
        return

    if not is_only_emojis(message.text):
        await main.send_safe(chat_id=message.chat.id, text="❗Сообщение должно содержать только эмодзи")
        return

    await main.send_safe(chat_id=message.chat.id, text=f'✅ {message.from_user.first_name}, эмодзи приняты!')

    main.emoji_battle_game.emojies[message.from_user.full_name] = message.text
    main.emoji_battle_game.all_emojies[message.from_user.full_name] += message.text
    try:
        await message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    n = 0
    for i in main.emoji_battle_game.emojies.values():
        if i != "":
            n += 1

    if n == len(main.emoji_battle_game.players):
        await main.send_safe(chat_id=message.chat.id, text='👥✅ Все эмодзи приняты, начинаем оценку!')
        emoji_battle_states = None


def is_only_emojis(text):
    text = regex.sub(r'[\u200d\uFE0F]', '', text)

    emoji_pattern = regex.compile(r'^\p{Emoji}+$')
    return bool(emoji_pattern.fullmatch(text))


#RandomCourt


@router.callback_query(F.data == 'defendant')
async def defendant(callback: Message):
    import main

    if main.random_court_game is None:
        await callback.answer("❗Игра неактивна")
        return

    if main.random_court_game.roles["Подсудимый"] is not None:
        await callback.answer(f'❗Эта роль уже занята игроком {main.random_court_game.roles["Подсудимый"].first_name}')
        return

    if callback.from_user in main.random_court_game.roles.values():
        await callback.answer('❗Ты уже выбрал роль')
        return

    main.random_court_game.roles["Подсудимый"] = callback.from_user
    await callback.answer("✅ Ты выбрал роль Подсудимый")
    await main.random_court_game.confirm_role("Подсудимый", callback.from_user.full_name)


@router.callback_query(F.data == 'prosecutor')
async def prosecutor(callback: Message):
    import main

    if main.random_court_game is None:
        await callback.answer("❗Игра неактивна")
        return

    if main.random_court_game.roles["Прокурор"] is not None:
        await callback.answer(f'❗Эта роль уже занята игроком {main.random_court_game.roles["Прокурор"].first_name}')
        return

    if callback.from_user in main.random_court_game.roles.values():
        await callback.answer('❗Ты уже выбрал роль')
        return

    main.random_court_game.roles["Прокурор"] = callback.from_user
    await callback.answer("✅ Ты выбрал роль Прокурор")
    await main.random_court_game.confirm_role("Прокурор", callback.from_user.full_name)


@router.callback_query(F.data == 'lawyer')
async def lawyer(callback: Message):
    import main

    if main.random_court_game is None:
        await callback.answer("❗Игра неактивна")
        return

    if main.random_court_game.roles["Адвокат"] is not None:
        await callback.answer(f'❗Эта роль уже занята игроком {main.random_court_game.roles["Адвокат"].first_name}')
        return

    if callback.from_user in main.random_court_game.roles.values():
        await callback.answer('❗Ты уже выбрал роль')
        return

    main.random_court_game.roles["Адвокат"] = callback.from_user
    await callback.answer("✅ Ты выбрал роль Адвокат")
    await main.random_court_game.confirm_role("Адвокат", callback.from_user.full_name)


async def waiting_for_prosecutor(message: Message):
    import main
    global random_court_states

    if message.chat.id != main.random_court_game.chat_id:
        return

    if message.from_user != main.random_court_game.role_turn:
        await main.send_safe(chat_id=message.chat.id, text=f'❗{message.from_user.first_name}, сейчас не твой ход')
        return

    main.random_court_game.answers.append(f"{message.from_user.full_name} (Прокурор) сказал {message.text}")
    random_court_states = "waiting_for_defendant"
    await main.random_court_game.next_turn()


async def waiting_for_defendant(message: Message):
    import main
    global random_court_states

    if message.chat.id != main.random_court_game.chat_id:
        return

    if message.from_user != main.random_court_game.role_turn:
        await main.send_safe(chat_id=message.chat.id, text=f'❗{message.from_user.first_name}, сейчас не твой ход')
        return

    main.random_court_game.answers.append(f"{message.from_user.full_name} (Подсудимый) сказал {message.text}")
    random_court_states = "waiting_for_lawyer"
    await main.random_court_game.next_turn()
    if main.random_court_game.round == main.random_court_game.max_rounds:
        random_court_states = None
        await main.random_court_game.end_game()
        return

    main.random_court_game.next_round()


async def waiting_for_lawyer(message: Message):
    import main
    global random_court_states

    if message.chat.id != main.random_court_game.chat_id:
        return

    if message.from_user != main.random_court_game.role_turn:
        await main.send_safe(chat_id=message.chat.id, text=f'❗{message.from_user.first_name}, сейчас не твой ход')
        return

    main.random_court_game.answers.append(f"{message.from_user.full_name} (Адвокат) сказал {message.text}")
    random_court_states = "waiting_for_prosecutor"
    await main.random_court_game.next_turn()


#Neuro Auction

@router.callback_query(F.data == 'neuro_auction_giveaway')
async def neuro_auction_giveaway(callback: Message):
    try:
        import main
        global neuro_auction_states

        if main.neuro_auction_game is None:
            await callback.answer("❗Игра неактивна")
            return

        if main.neuro_auction_game.can_get_neuro is False:
            await callback.answer('❗Нейро уже забрали')
            return

        main.neuro_auction_game.can_get_neuro = False
        neuro = random.randint(1, 500)
        main.neuro_auction_game.balance[callback.from_user.full_name] += neuro
        await callback.answer("✅ Ты получил нейро!")
        await main.neuro_auction_game.got_neuro(callback.from_user, neuro)
    except TelegramBadRequest:
        await callback.answer('❗Нейро уже нейдействителен')


async def receive_bet(message: Message):
    import main
    global neuro_auction_states

    if message.chat.id != main.neuro_auction_game.chat_id:
        return

    if message.from_user not in main.neuro_auction_game.players:
        return

    if message.text == '':
        return

    try:
        bet = int(message.text)
    except ValueError:
        await main.send_safe(chat_id=message.chat.id,
                             text=f'❗{message.from_user.full_name}, неверный формат, введите число')
        return

    if bet <= 0:
        await main.send_safe(chat_id=message.chat.id,
                             text=f'❗{message.from_user.full_name}, ставка должна быть больше 0')
        return

    if bet > main.neuro_auction_game.balance[message.from_user.full_name]:
        await main.send_safe(chat_id=message.chat.id,
                             text=f'❗{message.from_user.full_name}, недостаточно нейро для ставки')
        return

    if bet <= main.neuro_auction_game.bet[1]:
        await main.send_safe(chat_id=message.chat.id,
                             text=f'❗{message.from_user.full_name}, ставка должна быть больше предыдущей')
        return

    main.neuro_auction_game.bet = [message.from_user.full_name, bet]
    await message.delete()
    await main.send_safe(chat_id=message.chat.id,
                         text=f'✅ <u>{message.from_user.first_name}</u> сделал ставку <b>{bet}</b> нейро')


@router.message()
async def start_func(message: Message):
    if game_states == "waiting_for_game":
        await choose_game(message)
    else:
        if game == 'Survivors':
            if survivors_states == "waiting_for_theme":
                await receive_theme(message)
            elif survivors_states == "waiting_for_strategies":
                await receive_strategy(message)
        elif game == 'True or Fake':
            if true_or_fake_states == "waiting_for_thematic":
                await receive_thematic(message)
        elif game == 'Writers':
            if writers_states == "waiting_for_sentence":
                await receive_sentence(message)
        elif game == 'Emoji Battle':
            if emoji_battle_states == "waiting_for_emoji":
                await receive_emoji(message)
        elif game == 'Random Court':
            if random_court_states == "waiting_for_prosecutor":
                await waiting_for_prosecutor(message)
            elif random_court_states == "waiting_for_defendant":
                await waiting_for_defendant(message)
            elif random_court_states == "waiting_for_lawyer":
                await waiting_for_lawyer(message)
        elif game == 'Neuro Auction':
            if neuro_auction_states == "waiting_for_bet":
                await receive_bet(message)
