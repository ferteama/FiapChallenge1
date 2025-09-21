# comando para instalar a api do  bot: pip install pytelegrambotapi (colocar no terminal)
# comando para instalar o modulo: pip install telethon
# comando para instalar o modulo: pip install pandas requests
# comando para instalar dependencia: pip install pytelegrambotapi openai pandas requests

"""Importação de Módulos"""
import os
import telebot
from openai import OpenAI
import logging
import pandas as pd
from datetime import datetime

# --- Configuração do Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

api_id = "29031832"
api_hash = "8773c6535de7804d47412184f2d0a867"
bot_token = "8335626426:AAHhixS3aWVjkJERQ4q37LFmqTqmFRFdqTw"
openai_key = "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"

if not bot_token or not openai_key:
    raise ValueError("Erro: Defina as variáveis de ambiente telegram_bot_token e openai_api_key")

# --- MÓDULO DE ANÁLISE E IA (Customizado para planilha) ---

def resumo_dia(df: pd.DataFrame) -> dict:
    """Calcula agregados simples a partir do DataFrame, tolerando colunas diferentes."""
    if df.empty:
        return {}

    resumo = {}

    # Energia do dia
    if "Eday" in df.columns and not df["Eday"].dropna().empty:
        resumo["energia_dia"] = df["Eday"].dropna().iloc[-1]
    elif "Energia" in df.columns and not df["Energia"].dropna().empty:
        resumo["energia_dia"] = df["Energia"].sum()
    elif "Consumo" in df.columns and not df["Consumo"].dropna().empty:
        resumo["energia_dia"] = df["Consumo"].sum()
    else:
        resumo["energia_dia"] = 0.0

    # Pico de potência
    if "Pac" in df.columns and not df["Pac"].dropna().empty:
        idx_max = df["Pac"].idxmax()
        resumo["pico_potencia"] = float(df.loc[idx_max, "Pac"])
        resumo["hora_pico"] = df.loc[idx_max, "time"] if "time" in df.columns else None
    elif "Potencia" in df.columns and not df["Potencia"].dropna().empty:
        idx_max = df["Potencia"].idxmax()
        resumo["pico_potencia"] = float(df.loc[idx_max, "Potencia"])
        resumo["hora_pico"] = df.loc[idx_max, "time"] if "time" in df.columns else None
    else:
        resumo["pico_potencia"] = 0.0
        resumo["hora_pico"] = None

    # Estado da bateria
    if "Cbattery1" in df.columns and not df["Cbattery1"].dropna().empty:
        resumo["soc_ini"] = int(df["Cbattery1"].dropna().iloc[0])
        resumo["soc_fim"] = int(df["Cbattery1"].dropna().iloc[-1])
    else:
        resumo["soc_ini"] = None
        resumo["soc_fim"] = None

    return resumo


def explicar_dia(resumo: dict) -> str:
    """Gera uma explicação em texto simples a partir dos dados agregados."""
    if not resumo: return "Não foi possível gerar um resumo pois não há dados para analisar."
    energia, pico = resumo.get("energia_dia", 0.0), resumo.get("pico_potencia", 0.0)
    hora, soc_ini, soc_fim = resumo.get("hora_pico"), resumo.get("soc_ini"), resumo.get("soc_fim")
    hora_str = hora.strftime("%H:%M") if hora is not None and hasattr(hora, 'strftime') else "não registrado"
    if soc_fim is not None and soc_ini is not None:
        tendencia = "carga" if soc_fim >= soc_ini else "descarga"
        soc_str = f"O estado da bateria variou de {soc_ini}% para {soc_fim}% (tendência de {tendencia})."
    else:
        soc_str = "Dados de bateria (SOC) não disponíveis."

    return (
        f"Resumo do dia selecionado:\n"
        f"- Geração total de energia: {energia:.2f} kWh.\n"
        f"- Pico de potência atingido: {pico:.2f} kW às {hora_str}.\n"
        f"- {soc_str}"
    )


# --- INICIALIZAÇÃO DOS CLIENTES ---
ai_client = OpenAI(api_key=openai_key)
bot = telebot.TeleBot(bot_token)


# --- HANDLERS DO TELEGRAM BOT ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    start_text = (
        "Olá! Seja bem-vindo ao chatbot da EcoPowerManagement. Como podemos te ajudar hoje? 💡\n\n"
        "Caso queira descobrir mais sobre nossos comandos, digite /help."
    )
    bot.send_message(message.chat.id, start_text)
    logging.info(f'Comando /start recebido de {message.from_user.username}')


@bot.message_handler(commands=['info'])
def handle_info(message):
    response_text = "Esse ChatBot foi criado com a OpenAI API e integrado com dados de planilha para análises de geração de energia. 🤖"
    bot.send_message(message.chat.id, response_text)
    logging.info(f'Comando /info recebido de {message.from_user.username}')


@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = (
        "Comandos disponíveis:\n"
        "/start - Inicia a conversa com o bot.\n"
        "/help - Mostra esta mensagem de ajuda.\n"
        "/info - Exibe informações sobre o bot.\n"
        "/prioridade - Exibe a distribuição de prioridade dos seus dispositivos de casa e suas potências.\n"
        "/alexa - Saiba mais sobre a nossa interação com a Alexa.\n"
        "/resumo <data> - Gera um resumo da produção de energia a partir da planilha.\n"
        "  ↳ Exemplo: /resumo 2025-01-09\n\n"
        "Para outras dúvidas, apenas envie sua pergunta que a IA irá responder!"
    )
    bot.reply_to(message, help_text)
    logging.info(f"Comando /help recebido de {message.from_user.username}")

@bot.message_handler(commands=['resumo'])
def handle_resumo(message):
    """Handler para o comando de resumo usando dados da planilha Excel."""
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Formato incorreto. Use: /resumo <data_AAAA-MM-DD>")
        return

    date_str = args[1]
    try:
        req_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        bot.reply_to(message, "Formato de data inválido. Use AAAA-DD-MM (ex: 2025-01-09).")
        return

    bot.reply_to(message, f"Entendido! Buscando dados na planilha para o dia {date_str}...")
    bot.send_chat_action(message.chat.id, 'typing')

    try:
        # 1) Abrir arquivo (CSV preferencialmente, com sep=';' e header na 3ª linha)
        df = None
        if os.path.exists("apresentacao.csv"):
           try:
                df = pd.read_csv("apresentacao.csv", sep=";", header=2, encoding="utf-8")
           except Exception:
                df = pd.read_csv("apresentacao.csv", sep=";", header=2, engine="python", encoding="utf-8", low_memory=False)
        elif os.path.exists("apresentacao.xlsx"):
            df = pd.read_excel("apresentacao.xlsx", header=2)
        elif os.path.exists("apresentacao.xls"):
            try:
                df = pd.read_excel("apresentacao.xls", header=2)
            except Exception as e:
                raise RuntimeError("Erro lendo .xls: instale 'xlrd' no ambiente ou converta para .xlsx/.csv. " + str(e))
        else:
            raise FileNotFoundError("Nenhum arquivo 'apresentacao.csv/.xls/.xlsx' encontrado no diretório do script.")

        logging.info(f"Colunas encontradas: {list(df.columns)}")

        # 2) achar coluna de data/hora automaticamente
        def find_col_by_keywords(cols, keywords):
            for c in cols:
                lower = str(c).lower()
                for k in keywords:
                    if k in lower:
                        return c
            return None

        cols = list(df.columns)
        time_col = find_col_by_keywords(cols, ["time", "date", "data", "hora", "timestamp", "dia"])
        if not time_col:
            bot.send_message(message.chat.id, f"A planilha não possui coluna de data reconhecível. Colunas: {cols}")
            return

        # 3) tentar parsear datas (dayfirst=True pois seu CSV tem '09.01.2025')
        df[time_col] = pd.to_datetime(df[time_col], dayfirst=True, errors="coerce", infer_datetime_format=True)
        # se nada parseou, tentar sem dayfirst
        if df[time_col].isna().all():
            df[time_col] = pd.to_datetime(df[time_col], dayfirst=False, errors="coerce", infer_datetime_format=True)

        if df[time_col].isna().all():
            bot.send_message(message.chat.id, f"A coluna de tempo '{time_col}' não conseguiu ser convertida para datas. Envie as 3 primeiras células dessa coluna para eu analisar.")
            return

        # 4) informar intervalo de datas e filtrar pela data pedida
        available_dates = sorted(pd.unique(df[time_col].dt.date.dropna()))
        if not available_dates:
            bot.send_message(message.chat.id, "Nenhuma data válida encontrada na planilha.")
            return

        if req_date not in available_dates:
            bot.send_message(
                message.chat.id,
                f"Nenhum dado para {req_date}. Datas disponíveis: {available_dates[0]} até {available_dates[-1]}. "
                f"Ex.: /resumo {available_dates[0]}"
            )
            return

        dados_dia = df[df[time_col].dt.date == req_date]

        if dados_dia.empty:
            bot.send_message(message.chat.id, "Não encontrei linhas para a data (apesar de a data existir no índice).")
            return

        # 5) detectar colunas de potência/energia/soc e renomear para compatibilidade
        power_col = find_col_by_keywords(cols, ["(w)", "pac", "p meter", "p backup", "power"])
        energy_col = find_col_by_keywords(cols, ["(kwh)", "eday", "pv generation", "total output", "generation", "output"])
        soc_col = find_col_by_keywords(cols, ["soc", "cbattery", "battery"])

        rename_map = {}
        if time_col: rename_map[time_col] = "time"
        if power_col: rename_map[power_col] = "Pac"
        if energy_col: rename_map[energy_col] = "Eday"
        if soc_col: rename_map[soc_col] = "Cbattery1"

        df_ren = dados_dia.rename(columns=rename_map)

        # 6) chama suas funções de resumo
        resumo_dados = resumo_dia(df_ren)
        explicacao = explicar_dia(resumo_dados)
        bot.send_message(message.chat.id, explicacao)

    except Exception as e:
        logging.error(f"Erro ao processar comando /resumo: {e}")
        bot.send_message(message.chat.id, f"Ocorreu um erro ao buscar os dados: {e}")


@bot.message_handler(commands=['Alexa'])
def handle_alexa(message):
    """Handler para o comando Alexa"""

@bot.message_handler(commands=['prioridade'])
def handle_prioridade(message):
    """Handler para o comando de prioridade"""

@bot.message_handler(func=lambda message: True)
def handle_todas_as_outras_mensagens(message):
    """Handler genérico que usa a IA da OpenAI."""
    try:
        logging.info(f"Mensagem recebida de {message.from_user.username}: {message.text}")
        bot.send_chat_action(message.chat.id, 'typing')

        response = ai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages = [{"role": "user","content": f"{message.text}Responda como se você fosse um assistente da empresa GoodWe, uma empresa que auxilia o usuário a ver dados sobre consumo de energia na sua casa (em KWh), utilize uma linguagem meio informal para que os nossos usuários se adequem mais as informações, aliás utilize emojis em casos e tópicos ou explicações" }],
            max_tokens=3000
        )
        ai_response = response.choices[0].message.content
        bot.send_message(message.chat.id, ai_response)

    except Exception as e:
        logging.error(f"Erro ao processar mensagem com OpenAI: {e}")
        bot.reply_to(message, "Desculpe, ocorreu um erro ao processar sua solicitação.")


# --- INICIA O BOT ---
logging.info("Bot integrado iniciado. Aguardando mensagens...")
bot.polling()
