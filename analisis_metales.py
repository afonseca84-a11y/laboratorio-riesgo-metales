"""
Analisis cuantitativo de riesgo de commodities.
 
Replica exactamente los calculos del laboratorio HTML. Si un numero no coincide
entre las dos herramientas, uno de los dos esta mal: encontrarlo es el ejercicio.
 
Uso:
    python analisis_metales.py --csv datos_demo.csv --principal Oro --benchmark SP500
    python analisis_metales.py --descargar --principal Oro --benchmark SP500
    python analisis_metales.py --csv datos_demo.csv --frecuencia M --confianza 0.975
    python analisis_metales.py --csv datos_demo.csv --salida resultados.xlsx --json metricas.json
"""
 
from __future__ import annotations
 
import argparse
import json
 
import numpy as np
import pandas as pd
from scipy import stats
 
TICKERS = {
    "Oro": "GC=F", "Plata": "SI=F", "Platino": "PL=F", "Cobre": "HG=F",
    "Petroleo": "CL=F", "GasNatural": "NG=F", "Trigo": "ZW=F", "Maiz": "ZC=F",
    "SP500": "^GSPC", "Dolar": "DX-Y.NYB",
}
 
 
# ---------------------------------------------------------------- datos
def cargar_csv(ruta: str) -> pd.DataFrame:
    df = pd.read_csv(ruta, sep=None, engine="python")
    df.columns = [c.strip() for c in df.columns]
    df[df.columns[0]] = pd.to_datetime(df[df.columns[0]])
    df = df.set_index(df.columns[0]).sort_index()
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.ffill().dropna()
    if (df <= 0).any().any():
        raise ValueError("Hay precios menores o iguales a cero. Revisa la fuente.")
    return df
 
 
def descargar(inicio: str = "2019-01-01") -> pd.DataFrame:
    import yfinance as yf
    crudo = yf.download(list(TICKERS.values()), start=inicio,
                        auto_adjust=False, progress=False)["Close"]
    inverso = {v: k for k, v in TICKERS.items()}
    crudo.columns = [inverso.get(c, c) for c in crudo.columns]
    return crudo.ffill().dropna()
 
 
def remuestrear(px: pd.DataFrame, frecuencia: str) -> tuple[pd.DataFrame, int]:
    """D -> 252 periodos por anio; M -> 12, tomando el ultimo precio del mes."""
    if frecuencia.upper().startswith("M"):
        return px.resample("ME").last().dropna(), 12
    return px, 252
 
 
def rendimientos(px: pd.DataFrame, tipo: str = "log") -> pd.DataFrame:
    if tipo == "log":
        return np.log(px / px.shift(1)).dropna()
    return px.pct_change().dropna()
 
 
# ------------------------------------------------------------- metricas
def ewma_vol(r: pd.Series, f: int, lam: float = 0.94) -> float:
    """RiskMetrics: h_t = lam*h_{t-1} + (1-lam)*r_{t-1}^2."""
    h = float(r.iloc[0]) ** 2
    for x in r.iloc[:-1]:
        h = lam * h + (1 - lam) * x**2
    return float(np.sqrt(h * f))
 
 
def ewma_serie(r: pd.Series, f: int, lam: float = 0.94) -> pd.Series:
    h, salida = float(r.iloc[0]) ** 2, []
    for x in r:
        h = lam * h + (1 - lam) * x**2
        salida.append(np.sqrt(h * f))
    return pd.Series(salida, index=r.index, name="ewma")
 
 
def drawdown(px: pd.Series) -> dict:
    serie = px / px.cummax() - 1
    valle = serie.idxmin()
    pico = px.loc[:valle].idxmax()
    posterior = px.loc[valle:]
    recuperado = posterior[posterior >= px.loc[pico]]
    return {
        "serie": serie,
        "mdd": float(serie.min()),
        "pico": pico,
        "valle": valle,
        "recuperacion": recuperado.index[0] if len(recuperado) else None,
        "bajo_agua": float((serie < -1e-4).mean()),
    }
 
 
def resumen(px: pd.Series, r: pd.Series, f: int, rf: float, tipo: str = "log") -> dict:
    n = len(r)
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    vol_anual = sd * np.sqrt(f)
    media_anual = float(np.expm1(mu * f)) if tipo == "log" else mu * f
    acumulado = float(px.iloc[-1] / px.iloc[0] - 1)
    cagr = (1 + acumulado) ** (f / n) - 1
    dd = drawdown(px)
    # JB con momentos insesgados (los mismos que devuelven SKEW y KURT de Excel),
    # para que el laboratorio HTML, Excel y este modulo den identico resultado.
    asim = float(stats.skew(r, bias=False))
    curt = float(stats.kurtosis(r, fisher=False, bias=False))
    jb = n / 6 * (asim**2 + (curt - 3) ** 2 / 4)
    jb_p = float(stats.chi2.sf(jb, 2))
    return {
        "n": n,
        "acumulado": acumulado,
        "cagr": cagr,
        "media_anual": media_anual,
        "vol_anual": vol_anual,
        "vol_ewma": ewma_vol(r, f),
        "sigma_periodo": sd,
        "sharpe": (media_anual - rf) / vol_anual,
        "maximo": float(r.max()),
        "minimo": float(r.min()),
        "pct_positivos": float((r > 0).mean()),
        "mediana": float(r.median()),
        "asimetria": asim,
        "curtosis": curt,
        "jarque_bera": float(jb),
        "jb_pvalor": float(jb_p),
        "max_drawdown": dd["mdd"],
        "dd_pico": dd["pico"],
        "dd_valle": dd["valle"],
        "dd_recuperacion": dd["recuperacion"],
        "dd_duracion": int(px.index.get_loc(dd["valle"]) - px.index.get_loc(dd["pico"])),
        "bajo_agua": dd["bajo_agua"],
        "calmar": cagr / abs(dd["mdd"]),
        "_dd_serie": dd["serie"],
    }
 
 
def var_cvar(r: pd.Series, c: float = 0.99, h: int = 1) -> dict:
    """VaR expresado como perdida positiva. Tres metodos + Expected Shortfall."""
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    z = stats.norm.ppf(1 - c)
    s = stats.skew(r, bias=False)
    k = stats.kurtosis(r, fisher=True, bias=False)          # exceso
    z_cf = (z + (z**2 - 1) * s / 6 + (z**3 - 3 * z) * k / 24
            - (2 * z**3 - 5 * z) * s**2 / 36)
    raiz = np.sqrt(h)
    corte = float(np.percentile(r, (1 - c) * 100))
    return {
        "historico": -corte * raiz,
        "parametrico": -(mu * h + z * sd * raiz),
        "cornish_fisher": -(mu * h + z_cf * sd * raiz),
        "cvar": float(-r[r <= corte].mean() * raiz),
        "z": float(z),
        "z_cf": float(z_cf),
    }
 
 
def backtest_kupiec(r: pd.Series, c: float = 0.99, ventana: int = 250) -> pd.DataFrame:
    """VaR con ventana movil, evaluado fuera de muestra.
 
    LR_POF sigue una chi2(1): se rechaza la cobertura correcta si LR > 3.841.
    """
    metodos = ("historico", "parametrico", "cornish_fisher")
    excepciones = dict.fromkeys(metodos, 0)
    total = len(r) - ventana
    if total < 20:
        raise ValueError(f"Muestra insuficiente: se requieren mas de {ventana + 20} observaciones.")
 
    for t in range(ventana, len(r)):
        v = var_cvar(r.iloc[t - ventana:t], c, 1)
        for m in metodos:
            if r.iloc[t] < -v[m]:
                excepciones[m] += 1
 
    p, filas = 1 - c, []
    for m, N in excepciones.items():
        if 0 < N < total:
            lr = (-2 * ((total - N) * np.log(1 - p) + N * np.log(p))
                  + 2 * ((total - N) * np.log(1 - N / total) + N * np.log(N / total)))
        else:
            lr = -2 * total * np.log(1 - p)
        filas.append({
            "metodo": m,
            "excepciones": N,
            "esperadas": round(total * p, 1),
            "tasa": N / total,
            "LR_kupiec": lr,
            "p_valor": float(1 - stats.chi2.cdf(lr, 1)),
            "veredicto": "no se rechaza" if lr < 3.841 else "SE RECHAZA",
        })
    return pd.DataFrame(filas)
 
 
def beta_ols(r_activo: pd.Series, r_bench: pd.Series) -> dict:
    res = stats.linregress(r_bench, r_activo)
    return {"beta": float(res.slope), "alfa": float(res.intercept),
            "r2": float(res.rvalue**2), "p_valor": float(res.pvalue)}
 
 
def multifactor(r_activo: pd.Series, factores: pd.DataFrame) -> dict:
    """OLS con constante, sin statsmodels, para mantener dependencias minimas."""
    X = np.column_stack([np.ones(len(factores)), factores.values])
    b, *_ = np.linalg.lstsq(X, r_activo.values, rcond=None)
    ajuste = X @ b
    ss_res = float(((r_activo.values - ajuste) ** 2).sum())
    ss_tot = float(((r_activo.values - r_activo.mean()) ** 2).sum())
    return {"alfa": float(b[0]),
            "betas": {c: float(v) for c, v in zip(factores.columns, b[1:])},
            "r2": 1 - ss_res / ss_tot}
 
 
def monte_carlo(px: pd.Series, r: pd.Series, metodo: str = "boot",
                horizonte: int = 60, nsims: int = 5000,
                conf: float = 0.99, semilla: int | None = None) -> dict:
    """Simula trayectorias futuras del precio.
 
    metodo: 'boot' remuestrea rendimientos historicos con reemplazo (conserva
    la forma exacta de la distribucion, incluidas colas y asimetria);
    't' usa una t de Student calibrada a la curtosis muestral; 'normal' usa
    un browniano geometrico estandar.
 
    Los tres metodos asumen rendimientos independientes entre si (i.i.d.): no
    reproducen el agrupamiento de volatilidad de un GARCH/EWMA ni tendencias.
    """
    rng = np.random.default_rng(semilla)
    S0 = float(px.iloc[-1])
    m, sd = float(r.mean()), float(r.std(ddof=1))
    r_arr = r.values
 
    if metodo == "boot":
        idx = rng.integers(0, len(r_arr), size=(nsims, horizonte))
        choques = r_arr[idx]
    elif metodo == "t":
        exceso = max(0.0, float(stats.kurtosis(r, fisher=True, bias=False)))
        df = max(4.5, 6 / exceso + 4) if exceso > 0.5 else 30.0
        choques = m + sd * stats.t.rvs(df, size=(nsims, horizonte), random_state=rng)
    elif metodo == "normal":
        choques = rng.normal(m, sd, size=(nsims, horizonte))
    else:
        raise ValueError("metodo debe ser 'boot', 't' o 'normal'")
 
    acumulado = np.cumsum(choques, axis=1)
    trayectorias = S0 * np.exp(acumulado)
    terminal = trayectorias[:, -1]
 
    niveles = (5, 10, 25, 50, 75, 90, 95)
    percentiles_terminal = {p: float(np.percentile(terminal, p)) for p in niveles}
    banda = {p: (S0 * np.exp(np.percentile(acumulado, p, axis=0))).tolist() for p in (5, 25, 50, 75, 95)}
 
    ret_terminal = np.log(terminal / S0)
    var_sim = float(-np.percentile(ret_terminal, (1 - conf) * 100))
 
    return {
        "metodo": metodo, "horizonte": horizonte, "nsims": nsims,
        "precio_actual": S0,
        "mediana_proyectada": percentiles_terminal[50],
        "percentiles_terminal": percentiles_terminal,
        "banda": banda,
        "prob_baja": float((terminal < S0).mean()),
        "var_simulado": var_sim,
    }
 
 
def escenarios(betas: dict, v: dict, minimo: float, mdd: float) -> pd.DataFrame:
    filas = []
    for nombre, b in betas.items():
        for shock in (-0.10, -0.20):
            filas.append({"escenario": f"{nombre} {shock:+.0%}",
                          "impacto": b * shock, "origen": "regresion"})
    filas += [
        {"escenario": "VaR historico", "impacto": -v["historico"], "origen": "modelo de cola"},
        {"escenario": "CVaR", "impacto": -v["cvar"], "origen": "modelo de cola"},
        {"escenario": "Peor periodo observado", "impacto": minimo, "origen": "dato observado"},
        {"escenario": "Maximo drawdown", "impacto": mdd, "origen": "dato observado"},
    ]
    return pd.DataFrame(filas)
 
 
def tabla_comparativa(px: pd.DataFrame, r: pd.DataFrame, f: int, rf: float,
                      tipo: str, c: float, h: int) -> pd.DataFrame:
    filas = []
    for col in px.columns:
        s = resumen(px[col], r[col], f, rf, tipo)
        v = var_cvar(r[col], c, h)
        filas.append({
            "activo": col, "cagr": s["cagr"], "vol_anual": s["vol_anual"],
            "sharpe": s["sharpe"], "max_drawdown": s["max_drawdown"],
            "var_historico": v["historico"], "var_parametrico": v["parametrico"],
            "cvar": v["cvar"], "asimetria": s["asimetria"], "curtosis": s["curtosis"],
        })
    return pd.DataFrame(filas).set_index("activo")
 
 
# -------------------------------------------------------------- reporte
def ficha(nombre: str, s: dict, v: dict, bt: pd.DataFrame, corr: pd.DataFrame,
          beta: dict | None, esc: pd.DataFrame, cfg: dict, mc: dict | None = None) -> str:
    p = lambda x, d=2: f"{x * 100:.{d}f}%"
    recup = (f"{s['dd_recuperacion']:%Y-%m-%d}" if s["dd_recuperacion"] is not None
             else "sin recuperar")
    lineas = [
        f"FICHA DE RIESGO - {nombre.upper()}",
        f"Fuente: {cfg['fuente']}",
        f"Ventana: {cfg['inicio']} a {cfg['fin']} | Frecuencia: {cfg['frecuencia']} | n = {s['n']}",
        f"Rendimiento: {cfg['tipo']} | Tasa libre de riesgo: {p(cfg['rf'])}",
        "",
        "RENDIMIENTO",
        f"  Acumulado           : {p(s['acumulado'])}",
        f"  CAGR                : {p(s['cagr'])}",
        f"  Media anualizada    : {p(s['media_anual'])}",
        f"  Sharpe              : {s['sharpe']:.2f}",
        f"  Periodos positivos  : {p(s['pct_positivos'], 1)}",
        "",
        "VOLATILIDAD",
        f"  Anualizada          : {p(s['vol_anual'])}",
        f"  EWMA (lambda 0.94)  : {p(s['vol_ewma'])}",
        f"  Maximo / minimo     : {p(s['maximo'])} / {p(s['minimo'])}",
        "",
        "DRAWDOWN",
        f"  Maximo drawdown     : {p(s['max_drawdown'])}",
        f"  Pico -> valle       : {s['dd_pico']:%Y-%m-%d} -> {s['dd_valle']:%Y-%m-%d}"
        f"  ({s['dd_duracion']} periodos)",
        f"  Recuperacion        : {recup}",
        f"  Tiempo bajo el agua : {p(s['bajo_agua'], 1)}",
        f"  Calmar              : {s['calmar']:.2f}",
        "",
        f"VaR Y CVaR (confianza {cfg['confianza']:.1%}, horizonte {cfg['horizonte']})",
        f"  Historico           : {p(v['historico'])}",
        f"  Parametrico         : {p(v['parametrico'])}",
        f"  Cornish-Fisher      : {p(v['cornish_fisher'])}   (z ajustado {v['z_cf']:.3f} vs z {v['z']:.3f})",
        f"  CVaR                : {p(v['cvar'])}",
        f"  Razon CVaR / VaR    : {v['cvar'] / v['historico']:.2f}",
        f"  Sobre 100,000 USD   : {v['historico'] * 100000:,.0f} USD",
        "",
        f"BACKTESTING KUPIEC (ventana {cfg['ventana']}, critico 3.841)",
        bt.to_string(index=False, float_format=lambda x: f"{x:.4f}"),
        "",
        "DISTRIBUCION",
        f"  Asimetria           : {s['asimetria']:.3f}",
        f"  Curtosis            : {s['curtosis']:.2f} (exceso {s['curtosis'] - 3:.2f})",
        f"  Jarque-Bera         : {s['jarque_bera']:.1f} (p = {s['jb_pvalor']:.4f}) -> "
        + ("se rechaza la normalidad" if s["jb_pvalor"] < 0.05 else "no se rechaza la normalidad"),
        "",
        "CORRELACION DE RENDIMIENTOS",
        corr.round(3).to_string(),
        "",
    ]
    if beta:
        aviso = "   <- R2 muy baja: la beta es poco informativa" if beta["r2"] < 0.15 else ""
        lineas += [
            f"BETA CONTRA {cfg['benchmark'].upper()}",
            f"  Beta                : {beta['beta']:.3f}",
            f"  Alfa anualizada     : {p(beta['alfa'] * cfg['f'])}",
            f"  R2                  : {beta['r2']:.3f}{aviso}",
            "",
        ]
    lineas += ["ESCENARIOS",
               esc.to_string(index=False, float_format=lambda x: f"{x:.4f}")]
    if mc:
        nombres_metodo = {"boot": "bootstrap historico", "t": "t-Student calibrada",
                          "normal": "normal (browniano geometrico)"}
        var_analitico_h = v["historico"] * (mc["horizonte"] / cfg["horizonte"]) ** 0.5
        pt = mc["percentiles_terminal"]
        lineas += [
            "",
            f"SIMULACION MONTECARLO ({nombres_metodo[mc['metodo']]}, "
            f"{mc['nsims']} trayectorias, {mc['horizonte']} periodos)",
            f"  Precio actual        : {mc['precio_actual']:.2f}",
            f"  Mediana proyectada   : {mc['mediana_proyectada']:.2f} "
            f"({mc['mediana_proyectada'] / mc['precio_actual'] - 1:+.2%})",
            f"  Rango 90% (P5-P95)   : {pt[5]:.2f} a {pt[95]:.2f}",
            f"  Prob. de terminar bajo el precio actual: {p(mc['prob_baja'], 1)}",
            f"  VaR simulado vs analitico escalado ({cfg['confianza']:.1%}): "
            f"{p(mc['var_simulado'])} vs {p(var_analitico_h)}",
            "  Nota: los tres metodos asumen rendimientos i.i.d.; ninguno reproduce",
            "  agrupamiento de volatilidad (GARCH/EWMA) ni tendencias.",
        ]
    return "\n".join(lineas)
 
 
def main() -> None:
    ap = argparse.ArgumentParser(description="Analisis de riesgo de metales")
    ap.add_argument("--csv", help="archivo de precios; primera columna la fecha")
    ap.add_argument("--descargar", action="store_true", help="bajar series de Yahoo Finance")
    ap.add_argument("--principal", help="activo bajo analisis")
    ap.add_argument("--benchmark", help="serie de referencia para beta")
    ap.add_argument("--frecuencia", default="D", choices=list("DMdm"))
    ap.add_argument("--tipo", default="log", choices=["log", "simple"])
    ap.add_argument("--confianza", type=float, default=0.99)
    ap.add_argument("--horizonte", type=int, default=1)
    ap.add_argument("--rf", type=float, default=0.0425)
    ap.add_argument("--salida", help="ruta .xlsx opcional")
    ap.add_argument("--json", help="ruta .json opcional para alimentar el deck")
    ap.add_argument("--mc-metodo", default="boot", choices=["boot", "t", "normal"],
                    help="metodo de la simulacion Montecarlo")
    ap.add_argument("--mc-horizonte", type=int, default=60,
                    help="periodos a proyectar hacia adelante")
    ap.add_argument("--mc-sims", type=int, default=5000, help="numero de trayectorias")
    ap.add_argument("--mc-semilla", type=int, default=None,
                    help="semilla para reproducir la misma simulacion")
    a = ap.parse_args()
 
    if not a.csv and not a.descargar:
        ap.error("indica --csv o --descargar")
 
    px_bruto = descargar() if a.descargar else cargar_csv(a.csv)
    px, f = remuestrear(px_bruto, a.frecuencia)
    r = rendimientos(px, a.tipo)
 
    principal = a.principal or px.columns[0]
    if principal not in px.columns:
        raise SystemExit(f"'{principal}' no esta en los datos: {list(px.columns)}")
    benchmark = a.benchmark if a.benchmark in px.columns else None
    ventana = 250 if f == 252 else 36
 
    cfg = {
        "fuente": "Yahoo Finance" if a.descargar else a.csv,
        "inicio": f"{px.index[0]:%Y-%m-%d}", "fin": f"{px.index[-1]:%Y-%m-%d}",
        "frecuencia": "diaria (252)" if f == 252 else "mensual (12)",
        "tipo": a.tipo, "rf": a.rf, "confianza": a.confianza,
        "horizonte": a.horizonte, "ventana": ventana, "f": f,
        "benchmark": benchmark or "sin benchmark", "principal": principal,
    }
 
    s = resumen(px[principal], r[principal], f, a.rf, a.tipo)
    v = var_cvar(r[principal], a.confianza, a.horizonte)
    bt = backtest_kupiec(r[principal], a.confianza, ventana)
    corr = r.corr()
    beta = beta_ols(r[principal], r[benchmark]) if benchmark else None
 
    columnas = [c for c in (benchmark, "Dolar") if c and c in r.columns and c != principal]
    mf = multifactor(r[principal], r[columnas]) if columnas else {"betas": {}, "r2": np.nan}
    esc = escenarios(mf["betas"], v, s["minimo"], s["max_drawdown"])
    comp = tabla_comparativa(px, r, f, a.rf, a.tipo, a.confianza, a.horizonte)
    mc = monte_carlo(px[principal], r[principal], a.mc_metodo, a.mc_horizonte,
                     a.mc_sims, a.confianza, a.mc_semilla)
 
    print(ficha(principal, s, v, bt, corr, beta, esc, cfg, mc))
    print("\nCOMPARATIVO ENTRE ACTIVOS")
    print(comp.round(4).to_string())
 
    if a.salida:
        with pd.ExcelWriter(a.salida) as w:
            px.to_excel(w, sheet_name="precios")
            r.to_excel(w, sheet_name="rendimientos")
            pd.Series({k: x for k, x in s.items() if not k.startswith("_")}).to_excel(
                w, sheet_name="resumen")
            pd.Series(v).to_excel(w, sheet_name="var")
            bt.to_excel(w, sheet_name="backtest", index=False)
            corr.to_excel(w, sheet_name="correlacion")
            esc.to_excel(w, sheet_name="escenarios", index=False)
            comp.to_excel(w, sheet_name="comparativo")
            s["_dd_serie"].to_excel(w, sheet_name="drawdown")
        print(f"\nLibro guardado en {a.salida}")
 
    if a.json:
        mensual = px.resample("ME").last().dropna()
        borde = np.histogram_bin_edges(r[principal], bins=40)
        frec, _ = np.histogram(r[principal], bins=borde)
        centros = (borde[:-1] + borde[1:]) / 2
        ancho = borde[1] - borde[0]
        normal = stats.norm.pdf(centros, r[principal].mean(),
                                r[principal].std(ddof=1)) * len(r) * ancho
        paso = max(1, len(r) // 300)
        grafico = {
            "fechas": [f"{d:%Y-%m}" for d in mensual.index],
            "normalizado": {c: (mensual[c] / mensual[c].iloc[0] * 100).round(2).tolist()
                            for c in mensual.columns},
            "drawdown": (mensual[principal] / mensual[principal].cummax() - 1).round(4).tolist(),
            "histograma": {"centros": centros.round(5).tolist(),
                           "frecuencia": frec.tolist(),
                           "normal": normal.round(2).tolist()},
            "dispersion": {"x": r[benchmark].iloc[::paso].round(5).tolist(),
                           "y": r[principal].iloc[::paso].round(5).tolist()} if benchmark else None,
        }
        limpio = {k: x for k, x in s.items() if not k.startswith("_")}
        for k in ("dd_pico", "dd_valle", "dd_recuperacion"):
            limpio[k] = None if limpio[k] is None else f"{limpio[k]:%Y-%m-%d}"
        paquete = {
            "config": cfg, "resumen": limpio, "var": v,
            "backtest": bt.to_dict("records"),
            "correlacion": corr.round(4).to_dict(),
            "beta": beta, "multifactor": mf,
            "escenarios": esc.to_dict("records"),
            "comparativo": comp.round(6).reset_index().to_dict("records"),
            "grafico": grafico,
            "montecarlo": mc,
        }
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(paquete, fh, ensure_ascii=False, indent=1)
        print(f"Metricas guardadas en {a.json}")
 
 
if __name__ == "__main__":
    main()
 
