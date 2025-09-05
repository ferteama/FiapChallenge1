# ai.py
"""
Camada de IA (stub). Para começar sem custos, gera um texto simples
a partir de agregados. Depois, troque por chamada a um LLM.
"""
from __future__ import annotations

def explicar_dia(resumo: dict) -> str:
    if not resumo:
        return "Sem dados para analisar."
    energia = resumo.get("energia_dia", 0.0)
    pico = resumo.get("pico_potencia", 0.0)
    hora = resumo.get("hora_pico")
    soc_ini = resumo.get("soc_ini")
    soc_fim = resumo.get("soc_fim")
    hora_str = hora.strftime("%H:%M") if hora else "--:--"
    tendencia = "carga" if soc_fim is not None and soc_ini is not None and soc_fim >= soc_ini else "descarga"
    return (
        f"Geração total ~{energia:.2f} kWh. Pico ~{pico:.2f} kW às {hora_str}. "
        f"SOC {soc_ini}% → {soc_fim}% ({tendencia})."
    )
