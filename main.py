import asyncio
import random
import time
from logging import exception

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import FSInputFile
from openai import OpenAI
import logging
import os
import sys
from dotenv import load_dotenv
import aiohttp
from collections import deque

from app.handlers import router
import app.keyboards as kb

from aiogram.client.session.aiohttp import AiohttpSession


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_TOKEN = os.getenv("AI_TOKEN")

session = AiohttpSession(
    timeout=30.0
)

bot = Bot(token=BOT_TOKEN,
          default=DefaultBotProperties(parse_mode='HTML'),
          session=session)
dp = Dispatcher()

model_ai = 'deepseek-ai/DeepSeek-V3.2'

with open("topics.txt", "r", encoding="utf-8") as file:
    TOPICS_DATABASE = [line.strip() for line in file if line.strip()]

rate_limiter = None
lobby = None
survivors_game = None
true_or_fake_game = None
writers_game = None
emoji_battle_game = None
random_court_game = None
neuro_auction_game = None
games = ['Survivors', 'True or Fake', 'Writers', 'Emoji Battle', 'Random Court', 'Neuro Auction']
games_with_emoji = [
    ("🧟", "Survivors", "‍🔥"),
    ("🎭", "True or Fake", "❓"),
    ("✍️", "Writers", "📖"),
    ("⚔️", "Emoji Battle", "😄"),
    ("⚖️", "Random Court", "🎲"),
    ("💰", "Neuro Auction", "🧠")
]
players = []

last_send_time = {}


async def send_safe(chat_id, text, reply_markup=None, **kwargs):
    global last_send_time

    current_time = time.time()
    if chat_id in last_send_time:
        time_since_last = current_time - last_send_time[chat_id]
        if time_since_last < 0.3:
            await asyncio.sleep(0.3 - time_since_last)

    last_send_time[chat_id] = time.time()

    if 'photo' in kwargs:
        for attempt in range(3):
            try:
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=kwargs['photo'],
                    caption=text,
                    reply_markup=reply_markup
                )
            except Exception as e:
                if attempt < 2:
                    print("Ошибка, следующая попытка через 1 сек")
                    await asyncio.sleep(1)
                else:
                    return await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup
                    )
    else:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            **kwargs
        )


async def edit_safe(chat_id, message_id, text, reply_markup=None, **kwargs):
    global last_send_time

    current_time = time.time()
    if chat_id in last_send_time:
        time_since_last = current_time - last_send_time[chat_id]
        if time_since_last < 0.3:
            await asyncio.sleep(0.3 - time_since_last)

    last_send_time[chat_id] = time.time()

    if 'photo' in kwargs:
        for attempt in range(3):
            try:
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=kwargs['photo'],
                    caption=text,
                    reply_markup=reply_markup
                )
            except Exception as e:
                if attempt < 2:
                    print("Ошибка, следующая попытка через 1 сек")
                    await asyncio.sleep(1)
                else:
                    return await bot.edit_message_text(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        message_id=message_id
                    )
    else:
        return await bot.edit_message_text(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            message_id=message_id,
            **kwargs
        )


class SimpleRateLimiter:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.last_message_time = {}
        self.message_count = {}

    async def wait_for_chat(self):
        now = time.time()

        if self.chat_id not in self.last_message_time:
            self.last_message_time[self.chat_id] = now
            self.message_count[self.chat_id] = 1
            return

        time_since_last = now - self.last_message_time[self.chat_id]

        if time_since_last > 60:
            self.message_count[self.chat_id] = 1
            self.last_message_time[self.chat_id] = now
            return

        if self.message_count[self.chat_id] >= 18:
            wait_time = 60 - time_since_last
            if wait_time > 0:
                print(f"⚠️ Превышен лимит!")
                await asyncio.sleep(wait_time + 0.5)
                self.message_count[self.chat_id] = 1
                self.last_message_time[self.chat_id] = time.time()
                return

        self.message_count[self.chat_id] += 1

        if time_since_last < 0.2:
            await asyncio.sleep(0.2 - time_since_last)


class Lobby:
    def __init__(self, chat_id, leader):
        self.chat_id = chat_id
        self.message_id = None
        self.leader = leader
        self.participants = [leader]
        self.game = None
        self.games_list = None

    async def refresh_message(self):
        text = self.get_lobby_text()
        img_path = "assets/images/lobby.png"

        if os.path.exists(img_path):
            img = FSInputFile(img_path)

            if self.message_id is not None:
                try:
                    await bot.delete_message(chat_id=self.chat_id, message_id=self.message_id)
                    msg = await send_safe(
                        chat_id=self.chat_id,
                        photo=img,
                        text=text,
                        reply_markup=kb.join
                    )
                    self.message_id = msg.message_id
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
            else:
                msg = await send_safe(
                    chat_id=self.chat_id,
                    photo=img,
                    text=text,
                    reply_markup=kb.join
                )
                self.message_id = msg.message_id
        else:
            msg = await send_safe(
                chat_id=self.chat_id,
                text=text,
                reply_markup=kb.join
            )

            self.message_id = msg.message_id

    def get_lobby_text(self):
        participants = "\n".join(
            [f"👑 {p.full_name}" if p.id == self.leader.id else f"👤 {p.full_name}"
             for p in self.participants]
        )

        return (
            f"🎮 Лобби для игры с AI\n\n"
            f"Создатель: {self.leader.full_name}\n\n"
            f"Участники ({len(self.participants)}):\n{participants}\n\n"
            f"<b>Лидер</b> может начать игру командой \n{'-' * 11}/start{'-' * 11}\n\n"
            f"<b>Ты</b> можешь присоединиться командой \n{'-' * 11}/join{'-' * 12}"
        )

    async def choose_game(self):

        width = 20
        text = "⌚Время выбирать игру!\n\n🕹️Выберите игру:\n" + "\n".join(
            [
                f"{i + 1}. <code>{game[0]}{'-' * ((width - len(game[1])) // 2)}{game[1]}{'-' * ((width - len(game[1])) // 2)}{game[2]}</code>"
                for i, game in enumerate(games_with_emoji)]
        )

        await send_safe(
            chat_id=self.chat_id,
            text=text,
            reply_markup=kb.choose_game
        )


class SurvivorsGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        random.shuffle(self.players)
        self.round = 1
        self.max_rounds = 5
        self.results = {player.id: [] for player in players}
        self.current_theme = ""
        self.current_themes = []
        self.player_turn = None
        self.strategies = {}
        self.theme_message_id = None
        self.time_left = 120

    def next_round(self):
        self.round += 1
        self.current_theme = ""
        self.current_themes = []
        self.player_turn = None
        self.strategies = {}
        self.theme_message_id = None

    async def start_game(self):
        text = (
            f"👋 Добро пожаловать в игру <b>Выжившие</b>!\n\n"
            f"🤖 В этой игре вы будете придумывать стратегии выживания в различных ситуациях.\n"
            f"💬 Игроки будут выбирать ситуацию, а бот оценивать их стратегии. Удачи!"
        )

        await send_safe(chat_id=self.chat_id, text=text)

    async def choose_theme(self):
        self.player_turn = self.players[0]
        self.players = self.players[1:] + [self.players[0]]
        self.current_themes = random.sample(TOPICS_DATABASE, 3)

        text = (
                f"🎤 {self.player_turn.full_name}, выберите тему:\n"
                + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(self.current_themes))
        )

        msg = await send_safe(
            chat_id=self.chat_id,
            text=text,
            reply_markup=kb.theme
        )
        self.theme_message_id = msg.message_id

    async def own_theme(self):
        text = (
            f"✏️{self.player_turn.full_name}, напиши свою тему"
        )

        await edit_safe(
            chat_id=self.chat_id,
            text=text,
            message_id=self.theme_message_id
        )

    async def confirm_theme(self):
        text = (
            f"✍️Напиши свою стратегию выживания\n\n"
            f"📜Тема: <b>{self.current_theme}</b>\n\n\n"
            f"👥Игроков прислало стратегии: {len(self.strategies)}/{len(self.players)}\n\n"
        )

        await bot.delete_message(chat_id=self.chat_id,
                                 message_id=self.theme_message_id)

        msg = await send_safe(chat_id=self.chat_id,
                              text=text)

        self.theme_message_id = msg.message_id

    async def update_states(self):
        text = (
            f"✍️Напиши свою стратегию выживания\n\n"
            f"📜Тема: <b>{self.current_theme}</b>\n"
            f"👥Игроков прислало стратегии: {len(self.strategies)}/{len(self.players)}\n\n"
        )

        if len(self.strategies) == len(self.players) - 1:
            missing_player = next(player for player in self.players if player.id not in self.strategies)
            text += f"Ждём стратегию от: {missing_player.full_name}"

        await edit_safe(
            chat_id=self.chat_id,
            text=text,
            message_id=self.theme_message_id
        )

    async def evaluate_strategies_message(self):
        evaluated_strategies = await self.evaluate_strategies()

        for player in self.players:
            try:
                result_text = (
                    f"👤 {player.full_name}\n"
                    f"📜 Стратегия: {self.strategies[player.id]}\n\n"
                    f"📖 История:\n{evaluated_strategies[str(player.id)][0]}\n\n"
                    f"🔍 Вердикт: {'❤️ Выжил' if evaluated_strategies[str(player.id)][1] else '💀 Погиб'}"
                )

                survived = True if evaluated_strategies[str(player.id)][1] else False
                self.results[player.id].append(survived)

                await send_safe(chat_id=self.chat_id, text=result_text)

                await asyncio.sleep(0.1)

            except Exception as e:
                try:
                    print(self.strategies[player.id])
                except Exception:
                    print('Ошибка в стратегии')

                try:
                    print(evaluated_strategies[str(player.id)][0])
                except Exception:
                    print('Ошибка в истории')

                print(str(e))

                print(f'evaluated_strategies: {evaluated_strategies}')
                print(str(player.id))
                result_text = (
                    f"👤 {player.full_name}\n"
                    f"❗ОШИБКА ОБРАБОТКИ ОТВЕТА\n"
                    f"📖 {evaluated_strategies}"
                )

                if random.randint(0, 1) == 0:
                    survived = True
                else:
                    survived = False
                self.results[player.id].append(survived)

                await send_safe(chat_id=self.chat_id, text=result_text)

                await asyncio.sleep(0.1)

        await self.results_round()

    async def evaluate_strategies(self):
        try:

            import requests

            strategies = ''
            for player in self.players:
                strategies += str(player.id) + ": "
                strategies += self.strategies[player.id] + "\n"

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": model_ai,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Ты - бот, выносящий реалистичный вердикт в игре, где игроки придумывают стратегию выживания в "
                            "различных ситуациях. Опиши развитие событий (4-6 предложений) в разговорном, непринуждённом стиле. "
                            "Не пиши своих рассуждений ни в каком виде!. Мне нужна только одна история и вердикт. "
                            "Если стратегия хорошая и может сработать - оставь в живых, иначе, придумай реалистичную ситуацию, "
                            "где игрок погибает. Разбавь ответ юмором. Твоя задача, чтобы игрок погиб, однако ты должен "
                            "справедливо оценивать "
                            "ситуацию. Обязательно учитывай условия игрока, если они не дают ему фантастических преимуществ (например  "
                            "бессмертие). Как пример, если игрок говорит, что в данной ситуации он ведёт себя аккуратно, он не "
                            "может случайно споткнуться или наступить на что-то. Игрок может допускать небольшие ошибки в "
                            "стратегии. Если игрок нарушает правила, выдавая себе невозможные способности, придумай реалистичное "
                            "развитие событий. Учитывай, что фантастические предметы игрок может использовать (в пределах "
                            "разумного), если указал более-менее реалистичный способ их создания/приобретения. Не выделяй текст, учитывай регистр, не используй имена игроков.\n"
                            f"Тема раунда: {self.current_theme}\n, стратегии игроков: {strategies}\n"
                            "ОБЯЗАТЕЛЬНО! Формат:\nИгрок: [Имя_игрока]\nИстория: [текст]\nВердикт: [Выжил/Погиб]\n---\n")
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            text = data['choices'][0]['message']['content']

            try:
                parts = text.split("\n---\n")
                evaluated_strategies = {str(player.id): [] for player in players}
                for part in parts:
                    part_player = part.split('\n')
                    name = part_player[0].replace('Игрок:', '').strip()
                    name = part_player[0].replace('игрок:', '').strip()
                    story = part_player[1].replace('История:', '').strip()
                    story = story.replace('история:', '').strip()
                    survived = part_player[2].replace('Вердикт:', '').strip()
                    survived = survived.replace('вердикт:', '').strip()
                    survived = True if 'выжил' in survived.lower() else False
                    evaluated_strategies[name] = [story, survived]

                return evaluated_strategies
            except:
                print('\n\n')
                print(f'text: {text}')
                return f"⚠️ Ошибка обработки ответа", False

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки стратегии: {str(e)}", False

    async def results_round(self):
        text = f"Результаты раунда {self.round}:\n\n"
        for player in self.players:
            if self.results[player.id][-1]:
                text += f"❤️ {player.full_name} выжил!\n"
            else:
                text += f"💀 {player.full_name} погиб!\n"

        await send_safe(chat_id=self.chat_id, text=text)

        if self.round == self.max_rounds:
            await self.final_results()
        else:
            self.next_round()
            await self.choose_theme()

    async def final_results(self):
        global survivors_game

        winner = ['никто', 0]
        text = "🕹️Игра завершена! Общие результаты:\n\n"
        for player in self.players:
            wins = sum(1 for result in self.results[player.id] if result)
            if wins > winner[1]:
                winner = [player.full_name, wins]
            elif wins == winner[1] and wins != 0:
                winner[0] += f", {player.full_name}"
            text += f"👤 {player.full_name}: выжил {wins} раз(а) из {self.max_rounds}❤️\n"

        if winner[1] == 0:
            winner[0] = "никто"
        elif winner[0].count(",") == 0:
            text += f"\n🏆 Победитель: {winner[0]} с {winner[1]} выживанием(ями)!\n\n"
        else:
            text += f"\n🏆 Победители: {winner[0]} с {winner[1]} выживанием(ями)!\n\n"
        await send_safe(chat_id=self.chat_id, text=text)
        survivors_game = None


class TrueOrFakeGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.round = 1
        self.max_rounds = 5
        self.results = {player.id: [] for player in players}
        self.votes = {}
        self.results = {player.id: [] for player in players}
        self.facts = {}
        self.current_fact = ""
        self.true_or_fake = None
        self.thematic = ""

    def next_round(self):
        self.round += 1
        self.current_fact = ""
        self.votes = {}

    async def start_game(self):
        text = (
            f"👋 Добро пожаловать в игру <b>Правда или Ложь</b>!\n\n"
            f"🤖 Бот будет генерировать факты, а вы должны будете угадать, правда это или ложь.\n"
            f"💬 Выберите 'правда' или 'ложь' в сообщении, чтобы проголосовать. Удачи!"
        )

        await send_safe(chat_id=self.chat_id, text=text)

    async def choose_thematic(self):
        text = (
            f"🎤 Лидер выбирает тематику фактов"
        )

        await send_safe(
            chat_id=self.chat_id,
            text=text,
        )

    async def forming_facts(self):
        self.facts = await self.get_facts()

    async def write_fact(self):
        import app.handlers as handlers

        self.current_fact, self.true_or_fake = self.facts[self.round - 1][0], self.facts[self.round - 1][1]

        text = (
            f"🕹️Раунд {self.round} из {self.max_rounds}\n\n"
            f"🤖 Факт: {self.current_fact}\n\n"
            f"💬 Выберите 'правда' или 'ложь' в сообщении, чтобы проголосовать."
        )

        await send_safe(chat_id=self.chat_id,
                        text=text,
                        reply_markup=kb.answer
                        )

    async def get_facts(self):
        try:

            import requests

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": model_ai,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Создай 5 фактов для "Правда или Ложь" по теме: {self.thematic}

Требования:
1. Факты должны быть удивительными, малоизвестными
2. Случайно распредели: правда/ложь
3. Ложь должна звучать правдоподобно
4. Только факты, без пояснений

Формат:
Факт: [текст]
Ответ: [правда/ложь]
(повторить 5 раз)"""
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            text = data['choices'][0]['message']['content']

            try:
                num = 0
                facts = {}
                facts_and_answers = text.split('\n\n')
                for i in facts_and_answers:
                    parts = i.split('Ответ:')
                    fact = parts[0].replace('Факт:', '').strip()
                    fact = fact.replace('факт:', '').strip()
                    true_or_fake = True if 'правда' in parts[1].lower() else False
                    facts[num] = (fact, true_or_fake)
                    num += 1
            except:
                print("Ошибка")
                return f"⚠️ Ошибка обработки ответа", False

            return facts

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки стратегии: {str(e)}", False

    async def evaluate_votes(self):
        text = f"Результаты раунда {self.round}:\n\n"
        for player in self.players:
            text += f"⚖️ {player.full_name} проголосовал за {"<u>Правду</u>" if self.votes[player.id] else "<u>Ложь</u>"}!\n"
            self.results[player.id].append(True if self.true_or_fake == self.votes[player.id] else False)

        text += "\n\n🤖 Факт был: " + ("<b>правдой</b>" if self.true_or_fake else "<b>ложью</b>") + "\n\n"

        await send_safe(chat_id=self.chat_id, text=text)

        if self.round == self.max_rounds:
            await self.final_results()
        else:
            self.next_round()
            await self.write_fact()

    async def final_results(self):
        global true_or_fake_game

        winner = ['никто', 0]
        text = "🕹️Игра завершена! Общие результаты:\n\n"
        for player in self.players:
            wins = sum(1 for result in self.results[player.id] if result)
            if wins > winner[1]:
                winner = [player.full_name, wins]
            elif wins == winner[1] and wins != 0:
                winner[0] += f", {player.full_name}"
            text += f"👤 {player.full_name}: отгадал {wins} раз(а) из {self.max_rounds}\n"

        if winner[1] == 0:
            winner[0] = "никто"
        elif winner[0].count(",") == 0:
            text += f"\n🏆 Победитель: <b>{winner[0]}</b> с {winner[1]} правильным(и) ответом(ами)!\n\n"
        else:
            text += f"\n🏆 Победители: <b>{winner[0]}</b> с {winner[1]} правильным(и) ответом(ами)!\n\n"

        await send_safe(chat_id=self.chat_id, text=text)
        true_or_fake_game = None


class WritersGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.num_sentence = 0
        self.max_rounds = 3
        self.round = 0
        self.max_sentences = (len(players) * self.max_rounds) + (self.max_rounds + 1)
        self.story = ""
        self.last_sentence = ""
        self.player_turn = None
        self.message_id = None
        self.last_sentence_id = None
        self.max_in_round = len(self.players) + 1

    async def next_sentence(self):
        self.num_sentence += 1
        self.player_turn = self.players[0]
        self.players = self.players[1:] + [self.players[0]]
        if self.message_id is not None:
            await bot.delete_message(chat_id=self.chat_id,
                                     message_id=self.message_id)

    async def start_game(self):
        text = ("👋Добро пожаловать в игру <b>Писатели</b>!\n\n"
                "🕹️В этой игре вы будете по очереди писать отрывок текста, который будет добавляться к общей истории.\n"
                "🤖В конце каждого круга, первое и последнее предложение будет генерировать бот. Удачи!")

        await send_safe(chat_id=self.chat_id,
                        text=text)

    async def write_history(self):
        import app.handlers as handlers

        if self.num_sentence % (len(players) + 1) == 0 or self.num_sentence == 0:
            msg = await send_safe(chat_id=self.chat_id,
                                  text=(f"🔁<b>Круг {self.round + 1}/{self.max_rounds}</b>\n"
                                        f"📒<b>Предложение {self.num_sentence - (self.max_in_round * self.round)}/{self.max_in_round}</b>\n\n"
                                        f"🤖Сейчас <u>бот</u> придумывает предложение...\n\n")
                                  )
            self.message_id = msg.message_id

            if self.num_sentence != 0:
                self.round += 1

            self.last_sentence = await self.get_AI_sentence()
            await self.confirm_sentence()
        else:
            msg = await send_safe(chat_id=self.chat_id,
                                  text=(f"🔁<b>Круг {self.round + 1}/{self.max_rounds}</b>\n"
                                        f"📒<b>Предложение {self.num_sentence - (self.max_in_round * self.round)}/{self.max_in_round}</b>\n\n"
                                        f"👤Игрок <u>{self.player_turn.full_name}</u> пишет предложение!\n\n"
                                        )
                                  )

            last_sentence_id = await send_safe(chat_id=self.player_turn.id,
                                               text=f"Предыдущее предложение: {self.last_sentence}")

            self.last_sentence_id = last_sentence_id.message_id
            self.message_id = msg.message_id
            handlers.writers_states = "waiting_for_sentence"

    async def clear_last_sentence(self):
        await bot.delete_message(chat_id=self.player_turn.id,
                                 message_id=self.last_sentence_id)

    async def get_AI_sentence(self):
        try:

            import requests

            if self.num_sentence == 0:
                prompt = f"""Придумай первое предложение для истории (игра "Писатели").

Требования:
1. Одно предложение - начало истории
2. Должно быть необычным, загадочным или смешным
3. Случайная тема, объект, ситуация
4. Избегай повторений с прошлыми историями
5. Никак не выделяй текст!

Пример: Собрались как-то в лес трое друзей, чтобы найти клад, зарытый много лет назад..."""

            elif self.num_sentence == self.max_sentences - 1:
                prompt = f"""Продолжи историю (игра "Писатели").

Предыдущее предложение: {self.last_sentence}

Требования:
1. Добавь одно новое предложение
2. Сделай неожиданный поворот, который будет логическим продолжением предыдущего
3. Можно добавить юмор
4. Только предложение, без пояснений
5. Никак не выделяй текст!"""

            else:
                prompt = f"""Заверши историю (игра "Писатели").

Предыдущее предложение: {self.last_sentence}

Требования:
1. Одно финальное предложение
2. Неожиданный, но логичный конец
3. Можно добавить юмор
4. Только предложение, без пояснений
5. Никак не выделяй текст!"""

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": model_ai,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            text = answer

            return text

        except Exception as e:
            print(str(e))
            return f"⚠️ Ошибка обработки стратегии: {str(e)}", False

    async def confirm_sentence(self):
        self.story += " " + self.last_sentence

        await self.next_sentence()

        if self.num_sentence == self.max_sentences:
            await self.get_results()
            return

        await self.write_history()

    async def get_results(self):
        text = f"🎉 Игра завершена! История:\n\n{self.story}"

        await send_safe(chat_id=self.chat_id,
                        text=text)


class EmojiBattleGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.round = 1
        self.max_rounds = 3
        self.emojies = {player.full_name: "" for player in players}
        self.all_emojies = {player.full_name: "" for player in players}
        self.results = {player.id: [] for player in players}
        self.thematic = ""
        self.thematics = []
        self.message_id = None

    def next_round(self):
        self.round += 1
        self.thematic = ""
        self.emojies = {player.full_name: "" for player in players}

    async def start_game(self):
        text = ("👋Добро пожаловать в игру 'Эмодзи Битва'!\n\n"
                "🕹️ В этой игре вы будете придумывать наборы эмодзи, которые в наибольшей степени соответствуют "
                "заданной тематике. Удачи!")

        await send_safe(chat_id=self.chat_id,
                        text=text)

        text = "🕑Бот генерирует тематики для игры..."

        await send_safe(chat_id=self.chat_id,
                        text=text)

        self.thematics = await self.get_thematics()

    async def start_round(self):
        self.thematic = self.thematics[self.round - 1]

        await self.start_timer()

    async def start_timer(self):
        import app.handlers as handlers

        text = (f"🕹️Раунд {self.round} из {self.max_rounds}\n\n"
                f"🤖 Тематика: {self.thematic}\n\n"
                f"💬 Напишите свой набор эмодзи, наиболее подходящий к данной тематике.\n\n"
                f"⏳У вас есть 45 секунд, чтобы придумать свой набор эмодзи и отправить его в чат!\n\n"
                )

        msg = await send_safe(chat_id=self.chat_id,
                              text=text)
        self.message_id = msg.message_id

        timer_msg = await send_safe(chat_id=self.chat_id,
                                    text=f"⏱️Осталось: 45 секунд")
        timer_msg_id = timer_msg.message_id

        handlers.emoji_battle_states = "waiting_for_emoji"
        start_time = time.time()
        counter = 45
        while counter > 0 and not handlers.emoji_battle_states is None:
            elapsed_time = time.time() - start_time
            if elapsed_time >= 5:
                counter -= 5
                await edit_safe(chat_id=self.chat_id,
                                message_id=timer_msg_id,
                                text=f"⏱️Осталось: {counter} секунд")
                start_time = time.time()
            await asyncio.sleep(0.001)

        await bot.delete_message(chat_id=self.chat_id,
                                 message_id=timer_msg_id)

        if not handlers.emoji_battle_states is None:
            handlers.emoji_battle_states = None

            text = (f"🕹️Раунд {self.round} из {self.max_rounds}\n\n"
                    f"🤖 Тематика: {self.thematic}\n\n"
                    f"💬 Напишите свой набор эмодзи, наиболее подходящий к данной тематике.\n\n"
                    f"⏰Время вышло!"
                    )

            await edit_safe(chat_id=self.chat_id,
                            message_id=self.message_id,
                            text=text)

        await self.evaluate_emojies()

    async def get_thematics(self):
        try:

            import requests

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": model_ai,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Создай {self.max_rounds} тематик для "Эмодзи Битва".

Требования:
1. Тематики: необычные, забавные, абсурдные
2. Конкретные ситуации (пример: "поход в кино")
3. Без эмодзи в описании
4. Только список тематик
5. Никак не выделяй текст!

Формат:
Тематика 1
---
Тематика 2
---
..."""
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            text = answer
            thematics = text.split("\n---\n")

            return thematics

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки тематики: {str(e)}", False

    async def evaluate_emojies(self):
        text = f"Результаты раунда {self.round}:\n\n"
        verdicts = {}
        if any(self.emojies.values()):
            verdicts = await self.evaluate_emoji()

        for player in self.players:
            text += f"👤 {player.full_name}: "
            if self.emojies[player.full_name] == "":
                text += "❌ Не отправил набор эмодзи!\n"
                self.results[player.id].append("0")
                continue

            try:
                verdict = verdicts[player.full_name]
            except Exception as e:
                print(f'Ошибка поиска игрока: {str(e)}\n')
                print(verdicts)
                print(player.full_name)
                print(type(player.full_name))
                await send_safe(chat_id=self.chat_id,
                                text=f"⚠️ Ошибка при оценивании {player.full_name}, оценка будет выставлена случайно")
                verdict = str(random.randint(1, 10))

            text += verdict
            self.results[player.id].append(verdict.split('/')[0])
            text += f" - {self.emojies[player.full_name]}\n\n"

        await send_safe(chat_id=self.chat_id,
                        text=text)

        if self.round == self.max_rounds:
            await self.final_results()
        else:
            self.next_round()
            await self.start_round()

    async def evaluate_emoji(self):

        import requests

        text = ''
        for player in self.players:
            if self.emojies[player.full_name] == "":
                continue
            text += f"{player.full_name}: {self.emojies[player.full_name]}\n"

        url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_TOKEN}"
        }

        data = {
            "model": model_ai,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Ты - бот, который оценивает набор эмодзи в игре 'Эмодзи Битва'. Твоя задача - оценить "
                        "набор эмодзи, который игрок отправил на определённую тематику. Оцени набор эмодзи по "
                        "шкале от 1 до 10, где 1 - это полный провал, а 10 - это идеальный набор эмодзи. Не пиши "
                        "своих рассуждений ни в каком виде!. Мне нужно только оценка и не выделяй текст. Твой "
                        "ответ должен выглядеть так: '{кол-во баллов}/10'. Ты должен достаточной строго оценивать "
                        "набор на соответвие с тематикой, но не занижай оценку, оценивай справедливо."
                        f"Тематика раунда: '{self.thematic}'. Набор эмодзи: '{text}'. Обязательно! Формат:\n "
                        f"Игрок: [имя_игрока]\n[баллы]/10\n---\n.")
                }
            ]
        }

        parts = ''
        player = ''
        score = ''
        try:
            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            text = answer
            parts = text.split('\n---\n')
            verdicts = {}
            for part in parts:
                part_player = part.split('\n')

                player = part_player[0].replace(":", '').strip()
                player = player.replace("Игрок", '').strip()
                player = player.replace("игрок", '').strip()

                score = part_player[1].replace(":", '').strip()
                score = score.replace("/10", '').strip()
                verdicts[player] = score
            return verdicts

        except Exception as e:
            print(e)
            print(parts)
            print(player)
            print(score)
            return f"⚠️ Ошибка обработки эмодзи: {str(e)}", False

    async def final_results(self):
        global emoji_battle_game

        await send_safe(chat_id=self.chat_id,
                        text="🕹️Игра завершена! Оценка общих результатов...")

        winner = ['никто', 0]
        text = "🕹️Игра завершена! Общие результаты:\n\n"
        for player in self.players:
            wins = sum(int(result) for result in self.results[player.id])
            if wins > winner[1]:
                winner = [player.full_name, wins]
            elif wins == winner[1] and wins != 0:
                winner[0] += f", {player.full_name}"
            text += f"👤 {player.full_name}: набрал {wins} баллов из {self.max_rounds * 10}❤️\n"

        if winner[1] == 0:
            winner[0] = "никто"
        elif winner[0].count(",") == 0:
            text += f"\n🏆 Победитель: <b>{winner[0]}</b> с {winner[1]} баллом(ами)!\n\n"
            text += f"История его последней битвы:\n\n"
        else:
            text += f"\n🏆 Победители: <b>{winner[0]}</b> с {winner[1]} баллом(ами)!\n\n"
            text += f"История их последней битвы:\n\n"

        text += await self.get_story(winner[0])

        await send_safe(chat_id=self.chat_id, text=text)
        emoji_battle_game = None

    async def get_story(self, winner):

        import requests

        players_emoji = ''
        for player in self.players:
            players_emoji += f"{player.full_name}: {self.all_emojies[player.full_name]}\n"

        url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_TOKEN}"
        }

        data = {
            "model": model_ai,
            "messages": [
                {
                    "role": "user",
                    "content": f"""Напиши историю битвы эмодзи.

Победитель: {winner}
Всего игроков: {len(self.players)}
Эмодзи игроков:
{players_emoji}

Правила:
1. Победитель сражается с выдуманным врагом/ами (если один)
2. Если победителей много - они в команде
3. Если все победили - против вымышленного врага
4. Используй только указанные эмодзи
5. Каждый игрок - только свои эмодзи
6. Никак не выделяй текст!"""
                }
            ]
        }

        response = requests.post(url, headers=headers, json=data)
        data = response.json()
        answer = data['choices'][0]['message']['content']

        text = answer

        return text


class RandomCourtGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.answers = []
        self.roles = {"Подсудимый": None, "Прокурор": None, "Адвокат": None}
        self.case = ""
        self.role_turn = None
        self.round = 1
        self.max_rounds = 5
        self.turn = deque(["Прокурор", "Адвокат", "Подсудимый"])

    def next_round(self):
        self.round += 1

    async def start_game(self):
        text = (
            f"Добро пожаловать в игру <b>Случайный Суд</b>! ⚖️\n"
            f"В этой игре вы будете играть роли в суде, где каждый из вас будет выступать в роли подсудимого, "
            f"прокурора или адвоката.\n\n"
            f"Сейчас каждый должен определить свою роль.\n\n"
            f"•Подсудимый🧍‍♂️🚓\n"
            f"Главный герой «преступления», которого обвиняют. Может защищать себя или промолчать.\n\n"
            f"•Прокурор👨‍💼🔨\n"
            f"Обвинитель, который должен доказать вину подсудимого. Может задавать вопросы и делать выводы.\n\n"
            f"•Адвокат👨‍💼⚖️\n"
            f"Защитник подсудимого, который должен доказать его невиновность. Может задавать вопросы и делать выводы.\n\n"
            f"<s>•Свидетель</s>\n"
            f"<s>Можно выбрать, если игроков больше 3-х. Свидетель может быть как на стороне подсудимого, так и на стороне прокурора.</s>\n\n"
            f"•Судья👨‍⚖️\n"
            f"Судьёй будет выступать ИИ. Он вынесет окончательное решение, основываясь на предоставленных данных.\n\n"
        )

        await send_safe(chat_id=self.chat_id,
                        text=text,
                        reply_markup=kb.role)

    async def confirm_role(self, role, player):
        await send_safe(chat_id=self.chat_id,
                        text=f"Игрок {player} выбрал роль <b>{role}</b>.\n\n")

        if None not in self.roles.values():
            await send_safe(chat_id=self.chat_id,
                            text=f"Все роли выбраны. Игра начинается!")
            await self.write_case()

    async def write_case(self):
        import app.handlers as handlers

        await send_safe(chat_id=self.chat_id,
                        text=f"⏱️Нейросеть придумывает случайный случай...")

        defendant_text, prosecutor_text, lawyer_text, self.case = await self.get_case()

        await send_safe(chat_id=self.roles["Подсудимый"].id,
                        text="Вы -- подсудимый🧍‍♂️🚓. Вот, что вы знаете:\n\n" + defendant_text)
        await send_safe(chat_id=self.roles["Прокурор"].id,
                        text="Вы -- прокурор👨‍💼🔨. Вот, что вы знаете:\n\n" + prosecutor_text)
        await send_safe(chat_id=self.roles["Адвокат"].id,
                        text="Вы -- адвокат👨‍💼⚖️. Вот, что вы знаете:\n\n" + lawyer_text)

        await send_safe(chat_id=self.chat_id,
                        text=f"В игру!\n"
                             f"У вас есть 5 раундов, чтобы выяснить, кто прав, а кто виноват.\n\n"
                             f"Обвиняется игрок <u>{self.roles["Подсудимый"].full_name}</u>.\n\n"
                             f"Его защищает игрок <u>{self.roles["Адвокат"].full_name}</u>.\n\n"
                             f"Обвиняет его игрок <u>{self.roles["Прокурор"].full_name}</u>.\n\n")

        self.role_turn = self.roles[self.turn[0]]
        handlers.random_court_states = "waiting_for_prosecutor"

        await send_safe(chat_id=self.chat_id,
                        text=f"🔁Раунд {self.round} из {self.max_rounds}\n\n"
                             f"🗣️Сейчас говорит игрок <u>{self.role_turn.full_name}</u>.")

    async def next_turn(self):
        next_p = self.turn.popleft()
        self.turn.append(next_p)
        self.role_turn = self.roles[next_p]

        await send_safe(chat_id=self.chat_id,
                        text=f"🔁Раунд {self.round} из {self.max_rounds}\n\n"
                             f"🗣️Сейчас говорит игрок <u>{self.role_turn.full_name}</u>.")

    async def get_case(self):
        try:
            import requests

            prompt = (
                "Ты - бот, который генерирует случайный случай для игры 'Случайный Суд'. Твоя задача - "
                "придумать один случай, который будет интересным и необычным. Ты должен распределить информацию "
                "об одной и той же истории между участниками: подсудимым, прокурором и адвокатом. Случай должен "
                "быть связан с чем-то конкретным, например, 'кража', 'убийство', 'разгром' и т.д. Учитывай, "
                "что кто-то может иметь неверные сведения (и, если например это обвиняемый, то и адвокат, возможно, "
                "имеет те же сведения, и наоборот). Также учитывай, что адвокат или прокурор может раздобыть некоторые данные ("
                "возможно даже нечестным путём, но об этом знает возможно лишь он). Помни, что в правильной "
                "истории нет лжи, в ней всё так, как было на самом деле. Не пиши своих"
                "рассуждений ни в каком виде и не выделяй текст!. Твой ответ должен выглядеть так:\n\n(знания о "
                "ситуации для подсудимого)\n\n---\n\n(знания о ситуации для прокурора)\n\n---\n\n(знания о ситуации для "
                "адвоката)\n\n---\n\n(как всё было на самом деле)\n\nОБЯЗАТЕЛЬНО! Ты должен разделять информацию таким "
                "образом: '\n\n---\n\n'"
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": model_ai,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']
            text = answer

            parts = text.split('\n\n---\n\n')

            return parts[0], parts[1], parts[2], parts[3]

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки тематики: {str(e)}", False

    async def end_game(self):
        global random_court_game

        text = f"🎉 Игра завершена! Вот как всё было на самом деле:\n\n{self.case}"

        await send_safe(chat_id=self.chat_id,
                        text=text)

        await send_safe(chat_id=self.chat_id,
                        text="🕹️Игра завершена! Судья выносит приговор...")

        text = f"Судья вынес приговор:\n\n"
        text += await self.get_results()

        await send_safe(chat_id=self.chat_id,
                        text=text)

        random_court_game = None

    async def get_results(self):
        try:
            import requests

            print(self.answers)
            print(self.roles)

            prompt = (
                f"Ты - бот, который выносит приговор в игре 'Случайный Суд'. Представь, будто ты опытный юрист, "
                f"основывайся на реальных действующих законах РФ и выноси справедливый приговор. Твоя задача - "
                f"вынести приговор по случаю, который был представлен. Ты должен учитывать всё, что было озвучено "
                f"игроками. Вынеси приговор, основываясь на предоставленных данных. Не пиши своих "
                f"рассуждений ни в каком виде и не выделяй текст!. Твой ответ должен выглядеть так:\n\n"
                f"(приговор)\n\n(наказание)\n\n(объяснение приговора). Игроки выступали со следущими ролями: "
                f"{self.roles}. Вот все показания игроков (игроки высказывались по представленному порядку и имели "
                f"свои сведения о ситуации): {self.answers}"
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": model_ai,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            text = answer
            print(text)
            return text

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки приговора: {str(e)}", False


class NeuroAuctionGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.player_items = {player.full_name: [] for player in players}
        self.current_item = None
        self.current_description = None
        self.balance = {player.full_name: 1000 for player in players}
        self.bet = ['', 0]
        self.round = 1
        self.max_rounds = len(self.players) + 2
        self.gift_msg_id = 0
        self.can_get_neuro = True
        self.can_send_neuro = True
        self.the_most_expensive_item = ['', '', -1]
        self.the_most_cheap_item = ['', '', 999999999]
        self.items = []

    async def next_round(self):
        if self.can_send_neuro == False and self.can_get_neuro == True:
            try:
                await bot.delete_message(chat_id=self.chat_id,
                                         message_id=self.gift_msg_id)
            except Exception as e:
                print(str(e))

        self.round += 1
        self.current_item = None
        self.bet = ['', 0]
        self.can_get_neuro = True
        self.can_send_neuro = True

    async def start_game(self):
        text = (f"🕹️Игра 'Нейро-Аукцион' начинается!\n\n"
                f"У вас есть {self.max_rounds} раундов, чтобы купить как можно больше ценных предметов.\n\n"
                f"💰Каждый игрок начинает с 1000 нейро-рублей.\n\n"
                f"💎В каждом раунде будет выставлен один предмет на аукцион.\n\n"
                f"⏱️У вас есть 30 секунд, чтобы сделать ставку на предмет.\n\n"
                f"🏆После {self.max_rounds} раундов будет выбрана лучшая коллекция. Удачи!")

        await send_safe(chat_id=self.chat_id,
                        text=text)

        text = "🕑Нейросеть генерирует предметы..."

        await send_safe(chat_id=self.chat_id,
                        text=text)

        await self.get_items()

    async def start_round(self):
        import app.handlers as handlers

        try:
            self.current_item, self.current_description = self.items[self.round - 1][0], self.items[self.round - 1][1]
        except IndexError:
            print('---')
            print(self.current_item)
            print(self.current_description)
            print(self.items)
            print(self.round)
            print('---')

        text = (f"🕹️Раунд {self.round} из {self.max_rounds}\n\n"
                f"💎Предмет на аукционе: {self.current_item}\n\n"
                f"📜Описание: {self.current_description}\n\n"
                f"💰У вас будет 30 секунд, чтобы сделать ставку на предмет.\n\n"
                f"💬 Напишите свою ставку в нейро-рублях.")

        await send_safe(chat_id=self.chat_id,
                        text=text)

        await self.timer()

    async def got_neuro(self, player, count):
        await send_safe(chat_id=self.chat_id,
                        text=(f'✅ {player.full_name} получил {count} нейро!\n\n'
                              f'🤑Теперь у него на балансе {self.balance[player.full_name]} нейро'))
        await bot.delete_message(chat_id=self.chat_id,
                                 message_id=self.gift_msg_id)

    async def timer(self):
        import app.handlers as handlers

        text = f"🕑У вас есть 15 секунд, чтобы оценить предмет перед началом аукциона"
        msg = await send_safe(chat_id=self.chat_id,
                              text=text)
        timer_msg_id = msg.message_id

        start_time = time.time()
        counter = 15
        while counter > 0:
            elapsed_time = time.time() - start_time
            if elapsed_time >= 5:
                counter -= 5
                text = f"🕑У вас есть {counter} секунд, чтобы оценить предмет перед началом аукциона"
                await edit_safe(chat_id=self.chat_id,
                                message_id=timer_msg_id,
                                text=text)

                start_time = time.time()
            await asyncio.sleep(0.001)

        await bot.delete_message(chat_id=self.chat_id,
                                 message_id=timer_msg_id)

        text = f"👨‍⚖️🕑Время ставок!"
        await send_safe(chat_id=self.chat_id,
                        text=text)

        handlers.neuro_auction_states = "waiting_for_bet"

        text = f"⏱️Осталось: 30 секунд"
        msg = await send_safe(chat_id=self.chat_id,
                              text=text)
        timer_msg_id = msg.message_id

        start_time = time.time()
        counter = 25
        while counter > -1:
            elapsed_time = time.time() - start_time

            if elapsed_time >= 5:
                await edit_safe(chat_id=self.chat_id,
                                message_id=timer_msg_id,
                                text=f"⏱️Осталось: {counter} секунд")

                if random.randint(0, 5) == 1 and self.can_send_neuro:
                    msg = await send_safe(chat_id=self.chat_id,
                                          text=("🏅Немедленный розыгрыш!\n\n"
                                                f"👇Нажми на кнопку ниже и получи нейро-рубли!"),
                                          reply_markup=kb.neuro_auction_giveaway)
                    self.gift_msg_id = msg.message_id
                    self.can_send_neuro = False

                counter -= 5
                start_time = time.time()

            await asyncio.sleep(0.001)

        handlers.neuro_auction_states = None

        text = f"⌛️Время вышло!\n\n"
        await edit_safe(chat_id=self.chat_id,
                        message_id=timer_msg_id,
                        text=text)

        await self.evaluate_bets()

    async def evaluate_bets(self):
        if self.bet[0] != '':
            self.balance[self.bet[0]] -= self.bet[1]
            self.player_items[self.bet[0]].append([self.items[self.round - 1][0], self.items[self.round - 1][1]])

            if self.bet[1] > self.the_most_expensive_item[2]:
                self.the_most_expensive_item = [self.bet[0], self.current_item, self.bet[1]]
            if self.bet[1] < self.the_most_cheap_item[2]:
                self.the_most_cheap_item = [self.bet[0], self.current_item, self.bet[1]]

            text = (f"Результаты раунда <b>{self.round}</b>:\n\n"
                    f"Игрок <u>{self.bet[0]}</u> забрал предмет <b>{self.current_item}</b> за <b>{self.bet[1]}</b> нейро-рублей\n\n"
                    f"Баланс всех игроков:\n\n"
                    f"{'\n'.join([f'{player.full_name} - {self.balance[player.full_name]}' for player in self.players])}\n\n")
        else:
            text = (f"Результаты раунда <b>{self.round}</b>:\n\n"
                    f"<u>Никто</u> не сделал ставку на предмет <b>{self.current_item}</b>.\n\n"
                    f"Баланс всех игроков:\n\n"
                    f"{'\n'.join([f'{player.full_name} - {self.balance[player.full_name]}' for player in self.players])}\n\n")

        await send_safe(chat_id=self.chat_id,
                        text=text)

        if self.round == self.max_rounds:
            await self.final_results()
        else:
            await self.next_round()
            await self.start_round()

    async def get_items(self):
        try:
            import requests

            prompt = (
                f"Ты - бот, который генерирует предметы для игры 'Нейро-Аукцион'. Твоя задача - придумать {self.max_rounds}"
                f"предметов, которые будут интересными и необычными. Предметы должны быть связаны с чем-то "
                f"конкретным, например «Амулет, защищающий от понедельников» или «Невидимый кактус». Не пиши своих "
                f"рассуждений ни в каком виде и не выделяй текст! Твой ответ должен выглядеть так:\nНазвание: [название_"
                f"предмета]\nОписание: [описание]\n---\nНазвание: [название_предмета]\nОписание: [описание]\n---\n"
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": model_ai,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            text = answer
            parts = text.split('\n---\n')
            for part in parts:
                part_message = part.split("\n")
                name = part_message[0].replace("Название: ", '').strip()
                name = name.replace("название: ", '').strip()
                description = part_message[1].replace("Описание: ", '').strip()
                description = description.replace("описание: ", '').strip()
                self.items.append([name,
                                   description])
            print(text)
            print(self.items)
            return 0

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки предмета: {str(e)}", False

    async def final_results(self):
        global neuro_auction_game

        if self.can_send_neuro == False and self.can_get_neuro == True:
            try:
                await bot.delete_message(chat_id=self.chat_id,
                                         message_id=self.gift_msg_id)
            except Exception as e:
                print(str(e))

        text = "🕹️Игра завершена! Итоги аукциона:\n\n"
        for player in self.players:
            text += f"👤 {player.full_name}:\n\n"
            if self.player_items[player.full_name]:
                items = ', '.join([f"{', '.join([item[0] for item in self.player_items[player.full_name]])}"])
                text += f"Предметы: {items}\n"
            else:
                text += "Не купил ни одного предмета.\n"
            text += f"Баланс: {self.balance[player.full_name]}\n\n"

        if self.the_most_cheap_item[0] == '':
            self.the_most_cheap_item = ['никто', 'ничего', 0]
        if self.the_most_expensive_item[0] == '':
            self.the_most_expensive_item = ['никто', 'ничего', 0]
        if self.the_most_expensive_item[0] == '' and self.the_most_cheap_item[0] == '':
            text += "😮Никто не купил ни одного предмета на аукционе.\n\n"

        text += (
            f"💲Самый <u>дешёвый</u> предмет: <b>{self.the_most_cheap_item[1]}</b> за <b>{self.the_most_cheap_item[2]}</b> нейро-рублей. "
            f"Его приобрёл игрок <u>{self.the_most_cheap_item[0]}</u>\n\n"
            f"💰Самый <u>дорогой</u> предмет: <b>{self.the_most_expensive_item[1]}</b> за <b>{self.the_most_expensive_item[2]}</b> нейро-рублей. "
            f"Его приобрёл игрок <u>{self.the_most_expensive_item[0]}</u>\n\n")

        await send_safe(chat_id=self.chat_id,
                        text=text)

        await send_safe(chat_id=self.chat_id,
                        text="🤖Сейчас нейросеть оценит коллекции игроков и выберет победителя...")

        winner, story, criteria = await self.get_winner()

        text = (f"🏆 Победитель: <b>{winner}</b>\n\n"
                f"📖История его победы:\n\n{story}\n\n"
                f"🧾Критерии оценки коллекций:\n\n{criteria}")

        await send_safe(chat_id=self.chat_id,
                        text=text)

        neuro_auction_game = None

    async def get_winner(self):
        try:
            import requests

            items = ', '.join([
                f"{player.full_name}: {', '.join([item[0] + " " + item[1] for item in self.player_items[player.full_name]])}"
                for player in self.players])
            print(items)
            print('\n\n')

            prompt = (
                f"Ты - бот, который оценивает коллекции игроков в игре 'Нейро-Аукцион'. Твоя задача - оценить "
                f"коллекции игроков и выбрать победителя. Критерии, по которым ты оцениваешь коллекции, "
                f"ты придумываешь сам. Учитывай, что ты оцениваешь все коллекции по одним критериям. Твой ответ "
                "должен выглядеть так:\n\n{Победитель}\n\n---\n\n{История его победы}\n\n---\n\n{Критерии "
                "оценки коллекций}\n\nТы должен разделять части ответа таким образом: '\n\n---\n\n'. Не пиши "
                f"рассуждений и не выделяй текст! Можешь добавить в ответ юмора (оценивать по комичным критериям, "
                f"придумывать комичные сюжеты и тп). Вот коллекции игроков: {items}"
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": model_ai,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']
            # text = answer.split('/think\n')[1]
            text = answer
            print(text)
            print('\n\n')
            parts = text.split('\n\n---\n\n')
            print(parts)
            print('\n\n')

            return parts[0], parts[1], parts[2]

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки победителя: {str(e)}", False


async def health_check(request):
    return web.Response(text="OK", status=200)


async def start_health_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_get('/ping', health_check)

    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"🌐 Сервер запущен, порт: {port}")
    return runner


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def is_server():
    return os.getenv('RAILWAY_ENVIRONMENT') is not None or os.getenv('PORT') is not None


async def main():
    try:
        logger.info("🚀 Запуск...")

        if is_server():
            logger.info("🌐 Запущено на сервере")
            logger.info(f"Токен бота: {bool(BOT_TOKEN)}")
            logger.info(f"AI токен: {bool(AI_TOKEN)}")

            asyncio.create_task(start_health_server())

        dp.include_router(router)

        logger.info("🤖 Bot is starting polling...")
        await dp.start_polling(bot, skip_updates=True)

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлено")
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
