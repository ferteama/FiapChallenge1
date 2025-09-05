# app.py
# -------------------------------------------------------------------
# FIAP x GoodWe – Starter (Streamlit + mock SEMS data) - v2
# Inclui modo "Real (SEMS)" usando demo@goodwe.com / GoodweSems123!@#
# -------------------------------------------------------------------
import os
import json
from pathlib import Path
from datetime import datetime, date, time as dtime
import streamlit as st
import pandas as pd
import plotly.express as px

# Módulos locais
from ai import explicar_dia
from goodwe_client import crosslogin, get_inverter_data_by_column

# Caminhos
ROOT = Path(__file__).parent
MOCK_PATH = ROOT / "data" / "mock_today.json"

# ----------------------- Funções utilitárias ------------------------
def carregar_mock(path: Path) -> pd.DataFrame:
    """Carrega o arquivo JSON mock e devolve um DataFrame com datetime."""
    if not path.exists():
        st.error(f"Arquivo de mock não encontrado: {path}")
        return pd.DataFrame()
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    df = pd.DataFrame(payload["data"])
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
    df.attrs["meta"] = {
        "plant_id": payload.get("plant_id"),
        "inverter_sn": payload.get("inverter_sn"),
        "date": payload.get("date"),
        "timezone": payload.get("timezone"),
        "units": payload.get("units", {})
    }
    return df

def kwh(x: float) -> str:
    return f"{x:,.2f} kWh".replace(",", "X").replace(".", ",").replace("X", ".")

def kw(x: float) -> str:
    return f"{x:,.2f} kW".replace(",", "X").replace(".", ",").replace("X", ".")

def resumo_dia(df: pd.DataFrame) -> dict:
    """Calcula agregados simples para a análise."""
    if df.empty:
        return {}
    energia_dia = float(df["Eday"].dropna().iloc[-1]) if "Eday" in df.columns and not df["Eday"].dropna().empty else 0.0
    if "Pac" in df.columns and not df["Pac"].dropna().empty:
        idx_max = df["Pac"].idxmax()
        pico_p = float(df.loc[idx_max, "Pac"])
        pico_h = df.loc[idx_max, "time"] if "time" in df.columns else None
    else:
        pico_p, pico_h = 0.0, None
    soc_ini = int(df["Cbattery1"].dropna().iloc[0]) if "Cbattery1" in df.columns and not df["Cbattery1"].dropna().empty else None
    soc_fim = int(df["Cbattery1"].dropna().iloc[-1]) if "Cbattery1" in df.columns and not df["Cbattery1"].dropna().empty else None
    return {
        "energia_dia": energia_dia,
        "pico_potencia": pico_p,
        "hora_pico": pico_h,
        "soc_ini": soc_ini,
        "soc_fim": soc_fim,
    }

# ------------------ Integração SEMS (básica) ------------------------
def parse_column_timeseries(resp_json, column_name: str) -> pd.DataFrame:
    """
    Extrai série temporal do formato comum do SEMS.
    Suporta:
      - resp_json['data']['column1'] = [{'date': '...', 'column': <num>, ...}, ...]
      - listas em chaves: data/list/items/result/datas
      - itens com campos time/date/collectTime/cTime/tm e value/v/val/<column_name>/column
    """
    def _parse_time(ts):
        v = pd.to_datetime(ts, errors='coerce')
        if pd.isna(v):
            try:
                v = pd.to_datetime(ts, dayfirst=True, errors='coerce')
            except Exception:
                v = pd.NaT
        return v

    items = []
    if isinstance(resp_json, dict):
        data_obj = resp_json.get('data')
        if isinstance(data_obj, dict):
            for key in ('column1', 'column2', 'column3', 'items', 'list', 'datas', 'result'):
                if key in data_obj and isinstance(data_obj[key], list):
                    items = data_obj[key]
                    break
        if not items:
            for key in ('data', 'items', 'list', 'result', 'datas'):
                if key in resp_json and isinstance(resp_json[key], list):
                    items = resp_json[key]
                    break

    if not items:
        return pd.DataFrame()

    times, values = [], []
    for it in items:
        if not isinstance(it, dict):
            continue
        t = it.get('time') or it.get('date') or it.get('collectTime') or it.get('cTime') or it.get('tm')
        if column_name in it:
            v = it.get(column_name)
        else:
            v = it.get('value')
            if v is None: v = it.get('v')
            if v is None: v = it.get('val')
            if v is None: v = it.get('column')  # padrão GetInverterDataByColumn
        if t is None or v is None:
            continue
        t_parsed = _parse_time(t)
        if pd.isna(t_parsed):
            continue
        try:
            v_f = float(str(v).replace(',', '.'))
        except Exception:
            continue
        times.append(t_parsed)
        values.append(v_f)

    if not times:
        return pd.DataFrame()
    return pd.DataFrame({'time': times, column_name: values}).dropna()

def fetch_realtime_df(account: str, password: str, inverter_sn: str, req_date: date, columns: list[str],
                      login_region: str = "us", data_region: str = "eu") -> pd.DataFrame:
    """
    Executa crosslogin e busca várias colunas via GetInverterDataByColumn, unificando por 'time'.
    """
    token = crosslogin(account, password, login_region)
    # SEMS costuma exigir datetime com horário; usamos meia-noite local
    dt_str = datetime.combine(req_date, dtime(0, 0)).strftime("%Y-%m-%d %H:%M:%S")
    dfs = []
    for col in columns:
        try:
            js = get_inverter_data_by_column(token, inverter_sn, col, dt_str, data_region)
            df_col = parse_column_timeseries(js, col)
            if not df_col.empty:
                dfs.append(df_col)
            else:
                st.warning(f"Não consegui parsear a coluna '{col}'. Veja JSON bruto abaixo.")
                with st.expander(f"Ver resposta JSON ({col})"):
                    st.code(json.dumps(js, ensure_ascii=False, indent=2))
        except Exception as e:
            st.error(f"Erro ao buscar coluna '{col}': {e}")
    if not dfs:
        return pd.DataFrame()
    # Merge progressivo por 'time'
    out = dfs[0]
    for df_next in dfs[1:]:
        out = pd.merge_asof(out.sort_values("time"), df_next.sort_values("time"), on="time", direction="nearest")
    return out

# ---------------------------- UI -----------------------------------
st.set_page_config(page_title="GoodWe Assistant (MVP)", layout="wide", page_icon="⚡")

st.title("⚡ GoodWe Assistant — MVP")
st.caption("Streamlit starter • mock + modo real (SEMS) básico")

with st.sidebar:
    st.header("Configuração")
    modo = st.selectbox("Modo de dados", ["Mock (recomendado para começar)", "Real (SEMS)"], index=0)

    # Comuns
    inverter_sn_input = st.text_input("Inverter SN", value="5010KETU229W6177")
    data_ref = st.date_input("Data", value=date(2025, 8, 12))

    if modo == "Real (SEMS)":
        st.markdown("---")
        st.subheader("Login SEMS")
        env_acc = os.getenv("SEMS_ACCOUNT", "demo@goodwe.com")
        env_pwd = os.getenv("SEMS_PASSWORD", "GoodweSems123!@#")
        login_region = st.selectbox("Região de login", ["us", "eu"], index=0)
        data_region = st.selectbox("Região de dados", ["eu", "us"], index=0)
        account = st.text_input("SEMS_ACCOUNT (email)", value=env_acc)
        password = st.text_input("SEMS_PASSWORD", value=env_pwd, type="password")
        columns = st.multiselect("Colunas desejadas", ["Pac", "Eday", "Cbattery1", "Temp"], default=["Pac", "Eday", "Cbattery1"])
    else:
        columns = ["Pac", "Eday", "Cbattery1"]
        login_region = "us"
        data_region = "eu"
        account = ""
        password = ""

# Carrega dados conforme modo
if modo == "Mock (recomendado para começar)":
    df = carregar_mock(MOCK_PATH)
    if not df.empty:
        df = df[(df["time"].dt.date == pd.to_datetime(data_ref).date())]
else:
    with st.spinner("Conectando ao SEMS e buscando dados..."):
        df = fetch_realtime_df(account, password, inverter_sn_input, data_ref, columns, login_region, data_region)

# KPIs
if df is not None and not df.empty:
    col1, col2, col3 = st.columns(3)
    res = resumo_dia(df)
    col1.metric("Energia do dia", kwh(res.get("energia_dia", 0.0)))
    if res.get("hora_pico"):
        col2.metric("Pico de potência", kw(res.get("pico_potencia", 0.0)), res["hora_pico"].strftime("%H:%M"))
    else:
        col2.metric("Pico de potência", "—")
    soc_ini = res.get("soc_ini")
    soc_fim = res.get("soc_fim")
    soc_txt = f"{soc_ini}% → {soc_fim}%" if soc_ini is not None and soc_fim is not None else "—"
    col3.metric("Bateria (início → fim)", soc_txt)

    # Gráficos
    left, right = st.columns(2)
    with left:
        if "Pac" in df.columns:
            fig_p = px.line(df, x="time", y="Pac", markers=True, title="Potência (Pac) ao longo do dia")
            fig_p.update_layout(margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig_p, use_container_width=True)
        else:
            st.info("Sem coluna 'Pac' para plotar.")

    with right:
        if "Cbattery1" in df.columns:
            fig_soc = px.line(df, x="time", y="Cbattery1", markers=True, title="Estado de Carga da Bateria (SOC %)")
            fig_soc.update_layout(margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig_soc, use_container_width=True)
        else:
            st.info("Sem coluna 'Cbattery1' para plotar.")

    # Tabela
    with st.expander("Ver tabela de dados"):
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Downloads
    st.download_button(
        "Baixar CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"goodwe_{inverter_sn_input}_{data_ref}.csv",
        mime="text/csv"
    )

    st.markdown("---")
    if st.button("🔍 Analisar com IA (stub)"):
        res_info = resumo_dia(df)
        st.info(explicar_dia(res_info))
else:
    st.warning("Nenhum dado disponível. Revise as configurações ou tente o modo Mock.")