# comando para instalar a api do  bot: pip install pytelegrambotapi (colocar no terminal)
# comando para instalar o modulo: pip install telethon
# omando para instalar o modulo: pip install pandas requests

"""Importação de modulos"""
import os
import telebot
from openai import OpenAI
import logging

# --- Configuração do Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Carregue as Chaves de Forma Segura ---
api_id = "29031832"
api_hash = "8773c6535de7804d47412184f2d0a867"
bot_token = "8335626426:AAHhixS3aWVjkJERQ4q37LFmqTqmFRFdqTw"
openai_key = "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"

# Verificação para garantir que as chaves foram carregadas
if not bot_token or not openai_key:
    raise ValueError("Erro: Defina as variáveis de ambiente telegram_bot_token e openai_api_key")

# --- Inicialização dos Clientes ---
# Cliente da OpenAI (com o argumento nomeado 'api_key')
ai_client = OpenAI(api_key=openai_key)

# Cliente do Telegram Bot
bot = telebot.TeleBot(bot_token)

# --- Handlers (Funções que respondem a mensagens) ---

@bot.message_handler(commands=['start'])
def handle_start(message):
        start_text = (
            "Olá! Seja bem-vindo ao chatbot da EcoPowerManagement. Como podemos te ajudar hoje? 💡\n\n"
            "Caso queira descobrir mais sobre nossos comandos, digite /help. "
            "Se não, apenas digite uma mensagem de seu interesse que responderei!"
        )
        bot.send_message(message.chat.id, start_text)
        logging.info(f'Comando /start recebido de {message.from_user.username}')

@bot.message_handler(commands=['info'])
def handle_info(message):
    response_text = "Esse ChatBot foi criado com a OpenAI API para te auxiliar. 🤖"
    bot.send_message(message.chat.id, response_text)
    logging.info(f'Comando /info recebido de {message.from_user.username}')

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = (
        "Comandos disponíveis junto do nosso chatbot!:\n"
        "/start - Inicia a conversa com o bot.\n"
        "/help - Mostra esta mensagem de ajuda.\n"
        "/info - Exibe informações sobre o bot.\n\n"
        "Para o resto, basta me enviar sua pergunta!"
    )
    bot.reply_to(message, help_text)
    logging.info(f"Comando /help recebido de {message.from_user.username}")

# Este handler responde a qualquer mensagem de texto que NÃO seja um dos comandos acima
@bot.message_handler(func=lambda message: True)
def handle_all_other_messages(message):
    try:
        logging.info(f"Mensagem recebida de {message.from_user.username}: {message.text}")
        # Informa ao usuário que o bot está "digitando..."
        bot.send_chat_action(message.chat.id, 'typing')

        # Chama a API da OpenAI
        response = ai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', "content": message.text}],
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content

        # Envia a resposta da IA
        bot.send_message(message.chat.id, ai_response)

    except Exception as e:
        logging.error(f"Erro ao processar mensagem: {e}")
        bot.reply_to(message, "Desculpe, ocorreu um erro. Tente novamente mais tarde.")


@bot.message_handler(commands=['resumo'])
def handle_resumo(message):
    """Handler para o novo comando de resumo da GoodWe."""
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, "Formato incorreto. Use: /resumo <inverter_sn> <data_AAAA-MM-DD>")
        return

    inverter_sn, date_str = args[1], args[2]
    try:
        req_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        bot.reply_to(message, "Formato de data inválido. Use AAAA-MM-DD (ex: 2025-08-12).")
        return

    bot.reply_to(message,
                 f"Entendido! Buscando dados para o inversor {inverter_sn} no dia {date_str}. Isso pode levar um momento...")
    bot.send_chat_action(message.chat.id, 'typing')

    try:
        creds = client_from_env()
        df = fetch_sems_data_and_process(creds['account'], creds['password'], inverter_sn, req_date)

        if df.empty:
            bot.send_message(message.chat.id,
                             "Não encontrei dados para a data e inversor informados. Verifique se os dados estão corretos.")
            return

        resumo_dados = resumo_dia(df)
        explicacao = explicar_dia(resumo_dados)
        bot.send_message(message.chat.id, explicacao)

    except Exception as e:
        logging.error(f"Erro ao processar comando /resumo: {e}")
        bot.send_message(message.chat.id, f"Ocorreu um erro ao buscar os dados: {e}")
        
# --- Inicia o Bot ---
logging.info("Bot iniciado. Aguardando mensagens...")
bot.polling()