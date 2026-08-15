# Laboratorio de riesgo cuantitativo de metales

Material de apoyo para el punto 4 del proyecto: análisis cuantitativo de los riesgos
del mercado de metales. Tres herramientas que calculan **exactamente lo mismo** por
caminos distintos, para que el equipo pueda verificar sus propios números.

## Contenido

| Archivo | Qué es |
|---|---|
| `index.html` | Laboratorio interactivo de 9 pasos. Se abre en cualquier navegador, sin instalación ni servidor. |
| `analisis_metales.py` | Motor de verificación en Python. Reproduce cada número del laboratorio. |
| `generar_datos_demo.py` | Genera la serie sintética de práctica con semilla fija. |
| `datos_demo.csv` | Serie de práctica: 1,260 días, 6 activos. Ya incrustada en el HTML. |
| `plantilla_datos.csv` | Formato en el que se entregan las series reales. |
| `metricas.json` | Salida estructurada del análisis; alimenta el deck. |
| `generar_deck.js` | Genera el deck expositivo de 14 láminas con pptxgenjs. |
| `riesgo_metales_deck.pptx` / `.pdf` | Deck ya compilado con las cifras de la serie demo. |
| `resultados_demo.xlsx` | Libro con precios, rendimientos, VaR, backtesting, correlaciones y escenarios. |
| `inyectar_datos.py` | Vuelve a incrustar el CSV dentro del HTML si se regenera la serie. |
| `fetch_datos.py` | Descarga cierres reales de Yahoo Finance y produce `precios.json` para el sitio publicado. |
| `.github/workflows/actualizar-datos.yml` | GitHub Action que corre `fetch_datos.py` cada día hábil y publica el resultado. |

## Flujo de trabajo sugerido

1. **Explorar con la serie demo.** Abrir `index.html` y recorrer los nueve pasos.
   El objetivo es entender qué mide cada métrica antes de tocar datos reales.
2. **Descargar datos propios.** Yahoo Finance (`GC=F`, `SI=F`, `PL=F`, `HG=F`,
   `^GSPC`, `DX-Y.NYB`), LBMA, CME o FRED. Mínimo tres años de historia diaria.
3. **Cargar el CSV** en el laboratorio con el botón "Cargar mi CSV" y explorar la
   sensibilidad a la ventana, la frecuencia y el nivel de confianza.
4. **Verificar en Python.** Correr `analisis_metales.py` con los mismos datos y la
   misma configuración. Los números deben coincidir hasta el tercer decimal. Si no
   coinciden, uno de los dos cálculos está mal: encontrarlo es el ejercicio.
5. **Redactar.** La ficha que produce cualquiera de las dos herramientas es el
   insumo, no el entregable. El entregable es la interpretación.

## Verificación cruzada

```bash
pip install numpy pandas scipy openpyxl      # yfinance sólo si se usa --descargar

python analisis_metales.py --csv datos_demo.csv --principal Oro --benchmark SP500 \
       --confianza 0.99 --frecuencia D --salida resultados.xlsx --json metricas.json
```

Valores de referencia con la serie demo (oro, diaria, log, 99%, tasa libre de riesgo 4.25%):

| Métrica | Valor |
|---|---|
| CAGR | 10.44% |
| Volatilidad anualizada | 15.57% |
| Volatilidad EWMA (λ=0.94) | 24.67% |
| Máximo drawdown | −20.42% (2022-05-02 → 2023-06-13, recuperado 2024-04-16) |
| VaR histórico / paramétrico / Cornish-Fisher | 2.32% / 2.24% / 2.73% |
| CVaR | 2.91% |
| Excepciones Kupiec (hist / param / CF) | 15 / 11 / 10 de 1,009 pruebas |
| Asimetría / curtosis | 0.567 / 7.41 |
| Jarque-Bera | 1,089.4 → se rechaza la normalidad |
| Correlación con S&P 500 / dólar | 0.059 / −0.354 |

Si el laboratorio HTML muestra otra cosa con esta misma serie, hay un error que reportar.

## Datos en vivo, publicados para siempre

El laboratorio puede correr con precios reales que se actualizan solos, sin
servidor ni costo. La pieza clave es que **el navegador no puede llamar a Yahoo
Finance directamente**: Yahoo no manda cabeceras CORS para peticiones desde
JavaScript en el navegador, así que un `fetch()` desde `index.html` hacia Yahoo
falla la mayoría de las veces. Y no hace falta: VaR, drawdown, Sharpe, todo se
calcula sobre cierres diarios, no sobre el tick a tick, así que "en vivo" aquí
significa **actualizado cada día hábil**, no cada segundo.

La arquitectura, igual a la que ya usas en PRISMA:

```
GitHub Actions (cron diario)
   -> fetch_datos.py descarga cierres con yfinance (corre server-side, sin CORS)
   -> escribe precios.json y lo empuja al repo
Cloudflare Pages (o GitHub Pages)
   -> sirve index.html + precios.json como archivos estaticos
   -> el navegador de cada alumno lee precios.json con un fetch normal,
      mismo origen, sin restriccion
```

Nada de esto caduca: mientras el repo exista y Actions siga corriendo en el
plan gratuito, `precios.json` se refresca solo cada madrugada.

### Publicarlo

1. Sube esta carpeta completa (incluida `.github/workflows/`) a un repositorio
   de GitHub.
2. Conecta el repo a Cloudflare Pages (o GitHub Pages) como sitio estático,
   sin build command, raíz del sitio = raíz del repo.
3. En GitHub, pestaña **Actions** del repo, corre manualmente
   *"Actualizar datos de metales"* una vez (botón *Run workflow*) para generar
   el primer `precios.json`. De ahí en adelante corre solo, lunes a viernes.
4. Abre la URL publicada. `index.html` intenta leer `precios.json` al cargar;
   si lo encuentra, arranca directo con datos reales y lo dice en el aviso de
   la sección 1. Si no lo encuentra —porque aún no corrió el Action, o porque
   abriste el archivo localmente con doble clic— cae en silencio a la serie
   DEMO, sin romper nada.

### Botones relacionados en el laboratorio

- **"Datos en vivo"** — reintenta la carga de `precios.json` sin recargar la
  página. Útil si el Action acaba de correr.
- **"Cargar mi CSV"** — para cuando el equipo quiere trabajar con una fuente
  distinta (LBMA, un ticker que Yahoo no tiene, datos de otro proyecto).
- **"Volver a demo"** — regresa a la serie sintética de referencia.

### Correrlo tú mismo, fuera de GitHub Actions

```bash
pip install yfinance pandas --break-system-packages
python fetch_datos.py --inicio 2019-01-01
```

Nota: este comando necesita salida de red hacia `query1/query2.finance.yahoo.com`.
Si lo corres en un entorno con egress restringido no va a funcionar —igual que
en este sandbox, donde lo probé y confirmé el bloqueo—, pero en tu máquina o en
GitHub Actions no hay ese problema.

### Qué activos trae y cómo ampliarlos

`fetch_datos.py` descarga los mismos seis tickers que ya usa todo el paquete:
`GC=F`, `SI=F`, `PL=F`, `HG=F` (oro, plata, platino, cobre), más `^GSPC` y
`DX-Y.NYB` como benchmarks. Para agregar otro metal o instrumento, añade una
entrada al diccionario `TICKERS` en `fetch_datos.py` y en `analisis_metales.py`
— el HTML no necesita cambios, dibuja cualquier serie que venga en el JSON.



```bash
python analisis_metales.py --csv mis_datos.csv --principal Plata --benchmark SP500 \
       --json metricas.json
node generar_deck.js          # -> riesgo_metales_deck.pptx
```

El deck lee `metricas.json`: las cifras, las gráficas y las conclusiones se
actualizan solas con los datos del equipo.

## Formato de los datos

Primera columna la fecha, una columna por activo con el nombre en el encabezado.
Fechas ascendentes, sin filas de totales, sin celdas combinadas, sin separador de
miles. Si un mercado no operó un día, o se elimina la fila completa o se rellena con
el último precio, pero se documenta cuál de las dos cosas se hizo.

```csv
Fecha,Oro,Plata,Platino,Cobre,SP500,Dolar
2024-01-02,2073.40,23.31,997.20,3.8965,4742.83,101.39
2024-01-03,2042.10,22.91,975.60,3.8580,4704.81,102.49
```

## Sobre la serie demo

Es **sintética**: modelo de factores (metales preciosos, dólar, renta variable) con
choques t de Student de 5 grados de libertad y agrupamiento de volatilidad tipo
GARCH, con semilla fija para que todos los equipos vean lo mismo. Sus propiedades
estadísticas son realistas —colas gruesas, correlaciones plausibles, regímenes de
volatilidad— pero **no corresponde a precios reales** y no puede usarse en el
entregable.

## Convenciones de cálculo

Para que los tres artefactos coincidan, todos usan las mismas definiciones:

- Rendimiento logarítmico por omisión; el aritmético es opcional.
- Anualización con √252 (diaria) o √12 (mensual).
- Desviación estándar muestral (n−1).
- Asimetría y curtosis insesgadas, las mismas que devuelven `SKEW` y `KURT` de Excel.
- Jarque-Bera calculado con esos momentos insesgados.
- VaR expresado como pérdida positiva.
- CVaR: promedio de los rendimientos que quedan por debajo del corte del VaR.
- Backtesting con ventana móvil de 250 días (36 meses) y evaluación fuera de muestra.

## Qué se califica

| Criterio | Evidencia mínima |
|---|---|
| Fuente y ventana | Ticker, proveedor, fechas exactas, número de observaciones |
| Justificación de métricas | Por qué esa métrica y no otra, para este metal y este horizonte |
| Supuestos declarados | Frecuencia, tipo de rendimiento, anualización, tasa libre de riesgo |
| Prueba de normalidad | Asimetría, curtosis, Jarque-Bera y su consecuencia sobre el VaR |
| VaR con validación | Tres métodos comparados y backtesting con conteo de excepciones |
| Riesgo relativo | Matriz de correlación y correlación móvil, no sólo el promedio |
| Conclusión accionable | Ranking de metales con criterio explícito de decisión |

## Errores frecuentes

- Calcular la correlación sobre precios en lugar de rendimientos.
- Anualizar datos mensuales multiplicando por √252.
- Reportar el VaR sin ninguna validación fuera de muestra.
- Reportar la beta sin acompañarla de la R².
- Terminar el análisis en una tabla, sin ranking ni recomendación.

## Dos ejercicios para clase

**Contraste de frecuencia.** Correr el mismo metal en diaria y en mensual. El VaR
mensual no es el diario por √21: la diferencia abre la discusión sobre el supuesto de
independencia que sostiene la regla de la raíz.

**Trampa deliberada.** El control de confianza llega hasta 99.5%. Con 1,260
observaciones, el percentil 0.5% se apoya en unos seis datos. Sirve para que noten
que el VaR histórico a confianzas altas tiene un error de estimación enorme, y que la
prueba de Kupiec pierde potencia justo ahí.
