import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from google import genai

BLOCCHI_VALUTE = {
    "EUR": ["EURUSD=X", "EURGBP=X", "EURJPY=X", "EURAUD=X", "EURCAD=X", "EURCHF=X"],
    "GBP": ["GBPUSD=X", "EURGBP=X", "GBPJPY=X", "GBPAUD=X", "GBPCAD=X", "GBPCHF=X"],
    "USD": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCAD=X", "AUDUSD=X", "USDCHF=X"]
}

def scarica_calendario_oggi():
    url = "https://faireconomy.media"
    try:
        res = requests.get(url, timeout=15)
        if res.status_code != 200:
            return "Calendario non disponibile."
        eventi = res.json()
        oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rilevanti = []
        for ev in eventi:
            data_ev = ev.get("date", "")[:10]
            valuta = ev.get("country", "")
            impatto = ev.get("impact", "")
            if data_ev == oggi and valuta in ["EUR", "GBP", "USD"] and impatto in ["High", "Medium"]:
                ora = ev.get("date", "")[11:16]
                rilevanti.append(f"{ora} UTC - {valuta} ({impatto}): {ev.get('title', '')}")
        return "\n".join(rilevanti) if rilevanti else "Nessuna news ad alto/medio impatto oggi per EUR, GBP, USD."
    except Exception as e:
        return f"Errore calendario: {e}"

def analizza_blocchi():
    report = ""
    cache_dati = {}

    for valuta, lista_coppie in BLOCCHI_VALUTE.items():
        rapporti = []
        for simbolo in lista_coppie:
            if simbolo not in cache_dati:
                try:
                    df_h1 = yf.download(simbolo, period="5d", interval="1h", progress=False)
                    if not df_h1.empty:
                        if isinstance(df_h1.columns, pd.MultiIndex):
                            df_h1.columns = df_h1.columns.get_level_values(0)
                        tr = df_h1['High'] - df_h1['Low']
                        atr_breve = float(tr.tail(6).mean())
                        atr_lungo = float(tr.tail(48).mean())
                        cache_dati[simbolo] = round(atr_breve / atr_lungo, 2) if atr_lungo > 0 else 1.0
                except Exception:
                    continue
            if simbolo in cache_dati:
                rapporti.append(cache_dati[simbolo])

        if rapporti:
            media_vol = round(sum(rapporti) / len(rapporti), 2)
            report += f"- Blocco {valuta}: Indice Volatilita Attuale = {media_vol} (<0.85 = mercato compresso/laterale, >1.15 = mercato espansivo/volatile).\n"
    return report

def chiedi_a_gemini(dati_tecnici, calendario):
    if not dati_tecnici:
        return "Mercati chiusi o dati non disponibili al momento."

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt = (
        "Sei un analista Forex sintetico. Devi dare al trader solo una visione generale e rapida della giornata.\n"
        "NON fare l'analisi cross per cross. Dividi la risposta ESCLUSIVAMENTE in queste 3 sezioni: EUR, GBP, USD.\n\n"
        "Dati tecnici di volatilita sui panieri valutari:\n"
        f"{dati_tecnici}\n"
        "Calendario economico di oggi (orari in UTC):\n"
        f"{calendario}\n\n"
        "Regole di risposta:\n"
        "- Per EUR e GBP indica chiaramente cosa aspettarsi nella sessione europea (Lateralita oppure Molta volatilita) e come si comporteranno all'apertura americana del pomeriggio/sera.\n"
        "- Per USD indica cosa aspettarsi fino al primo pomeriggio (Lateralita oppure Volatilita) e cosa aspettarsi all'apertura americana.\n"
        "- Usa massimo 2-3 righe per valuta, linguaggio diretto, emoji pulite e niente asterischi doppi."
    )

    for modello in ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-2.0-flash"]:
        try:
            risposta = client.models.generate_content(model=modello, contents=prompt)
            if risposta and risposta.text:
                return risposta.text
        except Exception as e:
            print(f"Tentativo con {modello} fallito: {e}")

    return "Impossibile generare il report al momento."

def invia_telegram(testo):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = "https://api." + "telegram.org" + f"/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": testo[:4000]}, timeout=30)

if __name__ == "__main__":
    dati = analizza_blocchi()
    cal = scarica_calendario_oggi()
    print("Dati:\n", dati)
    print("Calendario:\n", cal)
    messaggio = chiedi_a_gemini(dati, cal)
    invia_telegram(messaggio)
