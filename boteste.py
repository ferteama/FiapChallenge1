# comando para instalar a api do  bot: pip install pytelegrambotapi (colocar no terminal)
# comando para instalar o modulo: pip install telethon

"""Importação de modulos"""
import telebot
import nest_asyncio
nest_asyncio.apply()
import logging
import asyncio
from telethon import TelegramClient, events
from openai import OpenAI

"""Tokens"""
api_id = "29031832"
api_hash = "8773c6535de7804d47412184f2d0a867"
token_bot= "8335626426:AAHhixS3aWVjkJERQ4q37LFmqTqmFRFdqTw"
openai_token = "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"
'''Inicio'''
# setando o logging
logging.basicConfig(level=logging.INFO)

# criando um telegram cliente
client = TelegramClient('bot', api_id, api_hash)
# criando uma ia cliente
ai_client = OpenAI(api_key=openai_token)

'''Meio'''
async def main():
    # start the client
    await client.start(token_bot=token_bot)

    # handler para o comando /start
    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        await event.respond("Olá!, seja bem-vindo ao chatbot da EcoPowerManagement, como podemos te ajudar hoje?")
        logging.info(f'Comando Start recebido pelo {event.sender_id}')

    # handler para o comando /info
    @client.on(events.NewMessage(pattern='/info'))
    async def info_handler(event):
        await event.respond("Esse ChatBot IA foi criado com a OpenAI API.")
        logging.info(f'Comando Info recebido pelo {event.sender_id}')

    # handler para o comando /help
    @client.on(events.NewMessage(pattern='/help'))
    async def help_hander(event):
        help_text = (
            "Aqui alguns comandos que você pode utilizar com a gente:\n"
            "/start - Para iniciar o Bot\n"
            "/help - Para solicitar informações que podem te ajudar\n"
            "/info - Para solicitar informações sobre o nosso Bot!\n"
        )
        await event.respond(help_text)
        logging.info(f"Comando Help recebido pelo {event.sender_id}")

    # keyword based response handler
    @client.on(events.NewMessage)
    async def keyword_responder(event):
        # get the message text
        message = event.text.lower()
        if message in ['/start', '/help', '/info']:
            return

        # get response from AI client
        response = ai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    'role': 'user', "content": message
                }
            ],
            max_tokens=1000
        )

        # get content from response
        response = response.choices[0].message.content
        if response:
            await event.respond(response)
        logging.info(f"Message received from {event.sender_id}: {event.text}")

    await client.run_until_disconnected()

logging.info("Bot iniciado. Aguardando mensagens...")
bot.polling()