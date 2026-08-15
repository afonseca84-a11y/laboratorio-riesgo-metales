"""
Descarga cierres diarios reales de Yahoo Finance y escribe precios.json,
el archivo que index.html intenta leer al cargar ("Datos en vivo").
 
Pensado para correr desde GitHub Actions una vez al dia (ver
.github/workflows/actualizar-datos.yml), pero funciona igual en local:
 
    pip install yfinance pandas --break-system-packages
    python fetch_datos.py --inicio 2019-01-01
 
Requiere salida de red hacia query1/query2.finance.yahoo.com. Si el entorno
donde lo corres la bloquea (como este sandbox), fallara: es normal aqui,
GitHub Actions si tiene salida abierta.
"""
 
from __future__ import annotations
 
import argparse
import json
import sys
from datetime import datetime, timezone
 
import pandas as pd
import yfinance as yf
 
TICKERS = {
    "Oro": "GC=F", "Plata": "SI=F", "Platino": "PL=F", "Cobre": "HG=F",
    "Petroleo": "CL=F", "GasNatural": "NG=F", "Trigo": "ZW=F", "Maiz": "ZC=F",
    "SP500": "^GSPC", "Dolar": "DX-Y.NYB",
}
 
 
def descargar(inicio: str) -> pd.DataFrame:
    crudo = yf.download(list(TICKERS.values()), start=inicio,
                        auto_adjust=False, progress=False)["Close"]
    if isinstance(crudo, pd.Series):  # un solo ticker
        crudo = crudo.to_frame(name=list(TICKERS.values())[0])
    inverso = {v: k for k, v in TICKERS.items()}
    crudo.columns = [inverso.get(c, c) for c in crudo.columns]
    crudo = crudo[[c for c in TICKERS if c in crudo.columns]]  # orden estable
    return crudo.ffill().dropna(how="all").dropna()
 
 
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", default="2019-01-01")
    ap.add_argument("--salida", default="precios.json")
    a = ap.parse_args()
 
    px = descargar(a.inicio)
    if len(px) < 60:
        print(f"Solo se obtuvieron {len(px)} observaciones validas; "
              "no se escribe el archivo para no publicar datos rotos.",
              file=sys.stderr)
        sys.exit(1)
 
    faltantes = [k for k in TICKERS if k not in px.columns]
    if faltantes:
        print(f"Aviso: no se pudieron descargar {faltantes}; "
              "se publica con el resto de activos.", file=sys.stderr)
 
    paquete = {
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "fuente": "Yahoo Finance (yfinance), cierres diarios",
        "fechas": [f"{d:%Y-%m-%d}" for d in px.index],
        "series": {c: [round(float(v), 4) for v in px[c]] for c in px.columns},
    }
    with open(a.salida, "w", encoding="utf-8") as fh:
        json.dump(paquete, fh, separators=(",", ":"))
    print(f"{a.salida}: {len(px)} observaciones, {len(px.columns)} activos, "
          f"{px.index[0]:%Y-%m-%d} a {px.index[-1]:%Y-%m-%d}")
 
 
if __name__ == "__main__":
    main()
 
