# comando para instalar a api do  bot: pip install pytelegrambotapi (colocar no terminal)
# comando para instalar o modulo: pip install telethon
# comando para instalar o modulo: pip install pandas requests
# comando para instalar dependencia: pip install pytelegrambotapi openai pandas requests

"""Importação de Módulos"""
import getpass
import os
import telebot
from openai import OpenAI
import logging
import json
import base64
import requests
import pandas as pd
from datetime import datetime, date, time as dtime
from typing import Dict, Any, Literal
from langchain.chat_models import init_chat_model
from langchain_core.vectorstores import InMemoryVectorStore
from pathlib import Path
from IPython.display import Audio, display, clear_output, HTML
import time

# --- Configuração do Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

api_id = "29031832"
api_hash = "8773c6535de7804d47412184f2d0a867"
bot_token = "8335626426:AAHhixS3aWVjkJERQ4q37LFmqTqmFRFdqTw"
openai_key = "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"

if not bot_token or not openai_key:
    raise ValueError("Erro: Defina as variáveis de ambiente telegram_bot_token e openai_api_key")

# --- MÓDULO GOODWE CLIENT (Integrado) ---

Region = Literal["us", "eu"]
BASE_URLS = {"us": "https://us.semsportal.com", "eu": "https://eu.semsportal.com"}


def _initial_token() -> str:
    """Gera o Token inicial (pré-login) para a API SEMS."""
    original = {"uid": "", "timestamp": 0, "token": "", "client": "web", "version": "", "language": "en"}
    b = json.dumps(original).encode("utf-8")
    return base64.b64encode(b).decode("utf-8")


def crosslogin(account: str, pwd: str, region: Region = "us") -> str:
    """Faz o crosslogin na API SEMS e devolve o Token válido."""
    url = f"{BASE_URLS[region]}/api/v2/common/crosslogin"
    headers = {"Token": _initial_token(), "Content-Type": "application/json"}
    payload = {"account": account, "pwd": pwd}
    r = requests.post(url, json=payload, headers=headers, timeout=20)
    r.raise_for_status()
    js = r.json()
    if "data" not in js or js.get("code") not in (0, 1, 200):
        raise RuntimeError(f"Login na GoodWe falhou: {js}")
    data_to_string = json.dumps(js["data"])
    return base64.b64encode(data_to_string.encode("utf-8")).decode("utf-8")


def get_inverter_data_by_column(token: str, inv_id: str, column: str, date_str: str, region: Region = "eu") -> Dict[
    str, Any]:
    """Busca dados de uma coluna específica do inversor."""
    url = f"{BASE_URLS[region]}/api/PowerStationMonitor/GetInverterDataByColumn"
    headers = {"Token": token, "Content-Type": "application/json"}
    payload = {"date": date_str, "column": column, "id": inv_id}
    r = requests.post(url, json=payload, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def client_from_env() -> Dict[str, str]:
    """Lê as credenciais da GoodWe (SEMS) das variáveis de ambiente."""
    acc = ("SEMS_ACCOUNT", "ecopower.management@gmail.com")
    pwd = ("SEMS_PASSWORD", "Goodwe2018")
    if not acc or not pwd:
        raise RuntimeError("Defina SEMS_ACCOUNT e SEMS_PASSWORD no ambiente para usar o comando /resumo.")
    return {"account": acc, "password": pwd}


def parse_column_timeseries(resp_json: dict, column_name: str) -> pd.DataFrame:
    """Extrai e parseia a série temporal da resposta da API SEMS."""
    items = []
    if isinstance(resp_json, dict):
        data_obj = resp_json.get('data', {})
        if isinstance(data_obj, dict):
            items = data_obj.get('column1', [])
    if not items: return pd.DataFrame()

    times, values = [], []
    for it in items:
        t, v = it.get('date'), it.get('column')
        if t is None or v is None: continue
        try:
            times.append(pd.to_datetime(t, errors='coerce'))
            values.append(float(str(v).replace(',', '.')))
        except (ValueError, TypeError):
            continue
    df = pd.DataFrame({'time': times, column_name: values}).dropna()
    return df


def fetch_sems_data_and_process(account: str, password: str, inverter_sn: str, req_date: date) -> pd.DataFrame:
    """Orquestra o login, busca de dados de múltiplas colunas e unificação em um DataFrame."""
    token = crosslogin(account, password, "us")
    dt_str = datetime.combine(req_date, dtime(0, 0)).strftime("%Y-%m-%d %H:%M:%S")
    columns = ["Pac", "Eday", "Cbattery1"]
    dfs = []
    for col in columns:
        js = get_inverter_data_by_column(token, inverter_sn, col, dt_str, "eu")
        df_col = parse_column_timeseries(js, col)
        if not df_col.empty:
            dfs.append(df_col)
    if not dfs: return pd.DataFrame()

    out = dfs[0]
    for df_next in dfs[1:]:
        out = pd.merge_asof(out.sort_values("time"), df_next.sort_values("time"), on="time", direction="nearest")
    return out


# --- MÓDULO DE ANÁLISE E IA (Integrado) ---

def resumo_dia(df: pd.DataFrame) -> dict:
    """Calcula agregados simples a partir do DataFrame de dados do inversor."""
    if df.empty: return {}
    energia_dia = df["Eday"].dropna().iloc[-1] if "Eday" in df.columns and not df["Eday"].dropna().empty else 0.0
    if "Pac" in df.columns and not df["Pac"].dropna().empty:
        idx_max = df["Pac"].idxmax()
        pico_p = float(df.loc[idx_max, "Pac"])
        pico_h = df.loc[idx_max, "time"] if "time" in df.columns else None
    else:
        pico_p, pico_h = 0.0, None
    soc_ini = int(df["Cbattery1"].dropna().iloc[0]) if "Cbattery1" in df.columns and not df[
        "Cbattery1"].dropna().empty else None
    soc_fim = int(df["Cbattery1"].dropna().iloc[-1]) if "Cbattery1" in df.columns and not df[
        "Cbattery1"].dropna().empty else None
    return {"energia_dia": energia_dia, "pico_potencia": pico_p, "hora_pico": pico_h, "soc_ini": soc_ini,
            "soc_fim": soc_fim}


def explicar_dia(resumo: dict) -> str:
    """Gera uma explicação em texto simples a partir dos dados agregados."""
    if not resumo: return "Não foi possível gerar um resumo pois não há dados para analisar."
    energia, pico = resumo.get("energia_dia", 0.0), resumo.get("pico_potencia", 0.0)
    hora, soc_ini, soc_fim = resumo.get("hora_pico"), resumo.get("soc_ini"), resumo.get("soc_fim")
    hora_str = hora.strftime("%H:%M") if hora else "não registrado"
    if soc_fim is not None and soc_ini is not None:
        tendencia = "carga" if soc_fim >= soc_ini else "descarga"
        soc_str = f"O estado da bateria variou de {soc_ini}% para {soc_fim}% (tendência de {tendencia})."
    else:
        soc_str = "Dados de bateria (SOC) não disponíveis."

    return (
        f"Resumo do dia:\n"
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
    response_text = "Esse ChatBot foi criado com a OpenAI API e integrado com a API da GoodWe para análises de geração de energia. 🤖"
    bot.send_message(message.chat.id, response_text)
    logging.info(f'Comando /info recebido de {message.from_user.username}')


@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = (
        "Comandos disponíveis:\n"
        "/start - Inicia a conversa com o bot.\n"
        "/help - Mostra esta mensagem de ajuda.\n"
        "/info - Exibe informações sobre o bot.\n"
        "/resumo <inverter_sn> <data> - Gera um resumo da produção de energia.\n"
        "  ↳ Exemplo: /resumo 5010KETU229W6177 2025-08-12\n\n"
        "Para outras dúvidas, apenas envie sua pergunta que a IA irá responder!"
    )
    bot.reply_to(message, help_text)
    logging.info(f"Comando /help recebido de {message.from_user.username}")


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


@bot.message_handler(func=lambda message: True)
def handle_all_other_messages(message):
    """Handler genérico que usa a IA da OpenAI."""
    try:
        logging.info(f"Mensagem recebida de {message.from_user.username}: {message.text}")
        bot.send_chat_action(message.chat.id, 'typing')

        response = ai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages = [{"role": "user","content": f"{message.text}Responda como se você fosse um assistente da empresa GoodWe, uma empresa que auxilia o usuário a ver dados sobre consumo de energia na sua casa (em KWh)" }],
            max_tokens=2000
        )
        ai_response = response.choices[0].message.content
        bot.send_message(message.chat.id, ai_response)

    except Exception as e:
        logging.error(f"Erro ao processar mensagem com OpenAI: {e}")
        bot.reply_to(message, "Desculpe, ocorreu um erro ao processar sua solicitação.")


# --- INICIA O BOT ---
logging.info("Bot integrado iniciado. Aguardando mensagens...")
bot.polling()