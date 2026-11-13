import os
import requests
import yfinance as yf
import pandas as pd
from google import genai

COPPIE = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "EURJPY=X", "AUDUSD=X"]

def analizza_dati():
    riepilogo_tecnico = ""
    for simbolo in COPPIE:
        nome = simbolo.replace("=X", "")
        try:
            df_h1 = yf.download(simbolo, period="5d", interval="1h", progress=False)
            df_m15 = yf.download(simbolo, period="2d", interval="15m", progress=False)
            
            if df_h1.empty or df_m15.empty:
                continue

            if isinstance(df_h1.columns, pd.MultiIndex):
                df_h1.columns = df_h1.columns.get_level_values(0)
            if isinstance(df_m15.columns, pd.MultiIndex):
                df_m15.columns = df_m15.columns.get_level_values(0)

            max_24h = float(df_h1['High'].tail(24).max())
            min_24h = float(df_h1['Low'].tail(24).min())
            prezzo_attuale = float(df_m15['Close'].iloc[-1])

            tr_h1 = df_h1['High'] - df_h1['Low']
            atr_breve = float(tr_h1.tail(6).mean())
            atr_lungo = float(tr_h1.tail(48).mean())
            rapporto_vol = round(atr_breve / atr_lungo, 2) if atr_lungo > 0 else 1.0

            riepilogo_tecnico += (
                f"- {nome}: Prezzo={prezzo_attuale:.4f}, Max24h={max_24h:.4f}, Min24h={min_24h:.4f}, "
                f"Rapporto Volatilita H1={rapporto_vol} "
                f"(<0.8 = compressione/lateralita, >1.2 = espansione/direzionalita).\n"
            )
        except Exception as e:
            print(f"Errore su {nome}: {e}")
            continue

    return riepilogo_tecnico

def chiedi_a_gemini(dati):
    if not dati:
        return "Nessun dato di mercato disponibile al momento (mercati chiusi o errore download)."

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt = (
        "Sei un analista Forex intraday esperto in timeframe bassi (M1, M5, M15) e struttura (H1, H4).\n"
        "Ecco i dati matematici attuali delle coppie alle 07:30 del mattino:\n"
        f"{dati}\n"
        "Scrivi un messaggio schematico e diretto per Telegram (massimo 2500 caratteri totali, usa emoji pulite, non usare asterischi doppi o formattazione Markdown complessa).\n"
        "Per ogni coppia indica:\n"
        "1. Scenario atteso oggi: Lateralita/Range oppure Direzionalita/Volatilita.\n"
        "2. Approccio operativo per M1, M5 e M15 nella sessione mattutina."
    )

    for modello in ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-2.0-flash"]:
        try:
            risposta = client.models.generate_content(model=modello, contents=prompt)
            if risposta and risposta.text:
                return risposta.text
        except Exception as e:
            print(f"Tentativo con {modello} fallito: {e}")

    return "Impossibile ottenere risposta da Gemini."

def invia_telegram(testo):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = "https://api." + "telegram.org" + f"/bot{token}/sendMessage"
    testo_sicuro = testo[:4000]
    res = requests.post(url, data={"chat_id": chat_id, "text": testo_sicuro}, timeout=30)
    print("Status Telegram:", res.status_code, res.text)

if __name__ == "__main__":
    dati = analizza_dati()
    print("Dati estratti:\n", dati)
    messaggio = chiedi_a_gemini(dati)
    invia_telegram(messaggio)
