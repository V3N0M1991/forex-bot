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
    risultati = {}
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
                        atr_breve = float(tr.tail(4).mean())
                        atr_lungo = float(tr.tail(48).mean())
                        cache_dati[simbolo] = round(atr_breve / atr_lungo, 2) if atr_lungo > 0 else 1.0
                except Exception:
                    continue
            if simbolo in cache_dati:
                rapporti.append(cache_dati[simbolo])

        if rapporti:
            risultati[valuta] = round(sum(rapporti) / len(rapporti), 2)
    return risultati

def chiedi_a_gemini(medie_vol, calendario, solo_alert=False):
    if not medie_vol:
        return None

    dati_testo = ""
    for valuta, media in medie_vol.items():
        dati_testo += f"- Blocco {valuta}: Indice Volatilita Attuale = {media}\n"

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    if solo_alert:
        prompt = (
            "Sei un sistema di alert Forex rapido. E' stata rilevata un'improvvisa espansione di volatilita' durante la giornata.\n"
            f"Dati attuali:\n{dati_testo}\n"
            f"Calendario oggi (UTC):\n{calendario}\n\n"
            "Scrivi un messaggio flash di massimo 5-6 righe totali segnalando SOLO quali valute tra EUR, GBP e USD hanno appena superato la soglia di alta volatilita' (> 1.25) e se dipende da una news o da un movimento tecnico. Usa emoji pulite e niente asterischi doppi."
        )
    else:
        prompt = (
            "Sei un analista Forex coerente e oggettivo. NON fare l'analisi cross per cross.\n"
            "Dividi la risposta ESCLUSIVAMENTE in 3 sezioni: EUR, GBP, USD.\n\n"
            "Dati tecnici attuali:\n"
            f"{dati_testo}\n"
            "Calendario economico oggi (orari in UTC):\n"
            f"{calendario}\n\n"
            "Regole logiche fisse da seguire sempre:\n"
            "1. Sessione Europea (mattina): se l'indice di volatilita e' inferiore a 1.05 e non ci sono news High Impact al mattino, indica LATERALITA'. Altrimenti indica VOLATILITA'.\n"
            "2. Apertura America (pomeriggio/sera, dopo le 12:30 UTC): indica VOLATILITA' SOLO SE nel calendario ci sono news High Impact USD/EUR/GBP nel pomeriggio oppure se l'indice attuale e' gia' sopra 1.15. In assenza di news pomeridiane ad alto impatto e con indice sotto 1.15, indica sempre LATERALITA' / MOVIMENTI CONTENUTI.\n"
            "3. Scrivi 2-3 righe chiare per valuta usando emoji pulite e senza asterischi doppi."
        )

    for modello in ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-2.0-flash"]:
        try:
            risposta = client.models.generate_content(
                model=modello,
                contents=prompt,
                config={"temperature": 0.1}
            )
            if risposta and risposta.text:
                return risposta.text
        except Exception as e:
            print(f"Tentativo con {modello} fallito: {e}")

    return None

def invia_telegram(testo):
    if not testo:
        return
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = "https://api." + "telegram.org" + f"/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": testo[:4000]}, timeout=30)

if __name__ == "__main__":
    ora_utc = datetime.now(timezone.utc).hour
    medie = analizza_blocchi()
    cal = scarica_calendario_oggi()
    print("Medie volatilita:", medie)

    evento_github = os.environ.get("GITHUB_EVENT_NAME", "")
    if ora_utc == 5 or evento_github == "workflow_dispatch":
        messaggio = chiedi_a_gemini(medie, cal, solo_alert=False)
        invia_telegram(messaggio)
    else:
        esplosioni = {k: v for k, v in medie.items() if v > 1.25}
        if esplosioni:
            messaggio = chiedi_a_gemini(medie, cal, solo_alert=True)
            invia_telegram("⚡ ALERT VARIAZIONE FOREX ⚡\n\n" + messaggio)
        else:
            print("Nessuna variazione rilevante: nessun messaggio inviato.")
