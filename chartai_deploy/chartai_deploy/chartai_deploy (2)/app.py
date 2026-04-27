#!/usr/bin/env python3
"""
ChartAI Pro – Flask Web App
Deploy: Railway, Render, Fly.io, oder lokal: python app.py
"""
import os, json, ssl, time, urllib.request
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='static')
PORT = int(os.environ.get('PORT', 7432))

# ── CACHE ──────────────────────────────────────────────────────────────────────
_cache = {}
_CACHE_TTL = 300  # 5 Minuten

def _cached(key, fn):
    now = time.time()
    if key in _cache and now - _cache[key][0] < _CACHE_TTL:
        return _cache[key][1]
    result = fn()
    _cache[key] = (now, result)
    return result

# ── LAZY IMPORT yfinance ───────────────────────────────────────────────────────
_yf = None
def yf():
    global _yf
    if _yf is None:
        import yfinance as _yfinance
        _yf = _yfinance
    return _yf

# ── TIMEFRAMES ─────────────────────────────────────────────────────────────────
# yfinance limitation: 1m only works for last 7 days, 2m last 60 days
# For 1d period: try 2m first (more reliable than 1m cross-market)
TF = {
    '1d':  ('1d',  ['2m','5m','15m','30m','1h','1d']),
    '5d':  ('5d',  ['5m','15m','30m','1h','1d']),
    '1mo': ('1mo', ['1h','1d']),
    '3mo': ('3mo', ['1d']),
    '6mo': ('6mo', ['1d']),
    '1y':  ('1y',  ['1d']),
    '3y':  ('3y',  ['1wk']),
    '5y':  ('5y',  ['1wk']),
}

def _parse_df(df, sym):
    if df is None or df.empty: return None
    out = []
    for ts, r in df.iterrows():
        try:
            o = float(r.get('Open', 0) or 0)
            h = float(r.get('High', 0) or 0)
            l = float(r.get('Low', 0) or 0)
            c = float(r.get('Close', 0) or 0)
            if not all([o, h, l, c]) or any(v != v for v in [o, h, l, c]): continue
            v = int(r['Volume']) if 'Volume' in r and r['Volume'] == r['Volume'] else 0
            out.append({
                't': int(ts.timestamp() * 1000),
                'o': round(o, 6), 'h': round(h, 6),
                'l': round(l, 6), 'c': round(c, 6), 'v': v
            })
        except: continue
    return {'candles': out, 'found_sym': sym} if len(out) >= 2 else None

def get_candles(sym, tf_key):
    cfg = TF.get(tf_key, ('3mo', ['1d']))
    period, intervals = cfg[0], cfg[1]
    sym_up = sym.upper().strip()

    # Candidate symbols – try exact first, then exchange suffixes
    candidates = [sym_up]
    if '.' not in sym_up and '=' not in sym_up and '^' not in sym_up:
        candidates += [
            sym_up + '.DE', sym_up + '.F', sym_up + '.L',
            sym_up + '.PA', sym_up + '.AS', sym_up + '.MI',
            sym_up + '.SW', sym_up + '.TO', sym_up + '.AX'
        ]

    for sym_try in candidates:
        for intv in intervals:
            try:
                t = yf().Ticker(sym_try)
                df = t.history(period=period, interval=intv, auto_adjust=True)
                if df is None or df.empty: continue
                out = _parse_df(df, sym_try)
                if out:
                    out['interval_used'] = intv
                    return out
            except Exception:
                continue

    return {'candles': [], 'found_sym': sym_up, 'error': f'No data for {sym_up}'}

def get_quotes(syms):
    res = {}
    if not syms: return res
    try:
        # Batch download
        df = yf().download(
            syms, period='5d', interval='1d',
            auto_adjust=True, progress=False,
            threads=True, group_by='ticker'
        )
        if df is not None and not df.empty:
            for s in syms:
                try:
                    sc = df[s]['Close'] if len(syms) > 1 else df['Close']
                    sc = sc.dropna()
                    if len(sc) >= 2:
                        px, prev = float(sc.iloc[-1]), float(sc.iloc[-2])
                        if prev > 0:
                            res[s] = {'px': round(px, 6), 'ch': round((px - prev) / prev * 100, 2)}
                    elif len(sc) == 1:
                        res[s] = {'px': round(float(sc.iloc[-1]), 6), 'ch': 0.0}
                except: pass
            if res: return res
    except: pass
    # Fallback: individual
    for s in syms:
        try:
            df = yf().Ticker(s).history(period='5d', interval='1d', auto_adjust=True)
            if df is None or df.empty: continue
            df = df.dropna(subset=['Close'])
            if len(df) >= 2:
                px, prev = float(df['Close'].iloc[-1]), float(df['Close'].iloc[-2])
                if prev > 0: res[s] = {'px': round(px, 6), 'ch': round((px - prev) / prev * 100, 2)}
            elif len(df) == 1:
                res[s] = {'px': round(float(df['Close'].iloc[-1]), 6), 'ch': 0.0}
        except: pass
    return res

def _get_info(sym):
    try:
        info = yf().Ticker(sym).info or {}
        return {
            'name':      info.get('longName') or info.get('shortName', ''),
            'sector':    info.get('sector', ''),
            'industry':  info.get('industry', ''),
            'country':   info.get('country', ''),
            'currency':  info.get('currency', ''),
            'exchange':  info.get('exchange', ''),
            'marketCap': info.get('marketCap'),
            'pe':        info.get('trailingPE'),
            'eps':       info.get('trailingEps'),
            'divYield':  info.get('dividendYield'),
            'divAbs':    info.get('lastDividendValue'),
            'week52H':   info.get('fiftyTwoWeekHigh'),
            'week52L':   info.get('fiftyTwoWeekLow'),
            'dayHigh':   info.get('dayHigh'),
            'dayLow':    info.get('dayLow'),
            'open':      info.get('open') or info.get('regularMarketOpen'),
            'prevClose': info.get('previousClose') or info.get('regularMarketPreviousClose'),
            'avgVol':    info.get('averageVolume'),
            'employees': info.get('fullTimeEmployees'),
            'website':   info.get('website', ''),
            'beta':      info.get('beta'),
            'marketState': info.get('marketState', ''),
            'desc':      (info.get('longBusinessSummary', '')[:600] + '…')
                         if info.get('longBusinessSummary', '') else '',
        }
    except: return {'name': ''}

def get_info(sym): return _cached(f'info:{sym}', lambda: _get_info(sym))

def _get_news(sym):
    try:
        out = []
        for n in (yf().Ticker(sym).news or [])[:15]:
            ct = n.get('content') or {}
            if isinstance(ct, str): ct = {}
            title = ct.get('title', '') or n.get('title', '') or ''
            if not title: continue
            summary = ct.get('summary', '') or n.get('summary', '') or ''
            pub_date = ct.get('pubDate', '') or ct.get('displayTime', '') or n.get('providerPublishTime', '') or ''
            if isinstance(pub_date, (int, float)):
                from datetime import datetime
                pub_date = datetime.utcfromtimestamp(pub_date).isoformat()
            clinks = ct.get('canonicalUrl') or {}
            link = (clinks.get('url', '') if isinstance(clinks, dict) else '') or n.get('link', '') or n.get('url', '') or ''
            prov = ct.get('provider') or {}
            publisher = (prov.get('displayName', '') if isinstance(prov, dict) else '') or n.get('publisher', '') or ''
            out.append({
                'title': title.strip(),
                'summary': summary[:500] if summary else '',
                'link': link, 'publisher': publisher, 'date': str(pub_date)
            })
        return out
    except: return []

def get_news(sym): return _cached(f'news:{sym}', lambda: _get_news(sym))

def _get_analyst(sym):
    try:
        t = yf().Ticker(sym)
        info = t.info
        out = {
            'targetHigh':     info.get('targetHighPrice'),
            'targetLow':      info.get('targetLowPrice'),
            'targetMean':     info.get('targetMeanPrice'),
            'targetMedian':   info.get('targetMedianPrice'),
            'recommendation': info.get('recommendationKey', ''),
            'numAnalysts':    info.get('numberOfAnalystOpinions'),
            'currentPrice':   info.get('currentPrice') or info.get('regularMarketPrice'),
            'ratings': [], 'summary': {}
        }
        try:
            recs = t.recommendations
            if recs is not None and not recs.empty:
                cols = [c.lower().replace(' ', '') for c in recs.columns]
                def gcol(row, *names):
                    for n in names:
                        for orig, low in zip(recs.columns, cols):
                            if low == n.lower().replace(' ', ''):
                                v = row.get(orig, '')
                                return str(v).strip() if v and str(v) != 'nan' else ''
                    return ''
                for idx, row in recs.tail(20).iterrows():
                    firm   = gcol(row, 'Firm', 'firm', 'Company')
                    action = gcol(row, 'Action', 'action', 'GradeAction')
                    fr     = gcol(row, 'From Grade', 'fromGrade', 'From')
                    to     = gcol(row, 'To Grade', 'toGrade', 'To', 'Grade')
                    date   = str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10]
                    if firm or to:
                        out['ratings'].append({'firm': firm, 'action': action, 'from': fr, 'to': to, 'date': date})
        except: pass
        try:
            rs = t.recommendations_summary
            if rs is not None and not rs.empty:
                row = rs.iloc[-1]
                out['summary'] = {
                    'strongBuy':  int(row.get('strongBuy', 0) or 0),
                    'buy':        int(row.get('buy', 0) or 0),
                    'hold':       int(row.get('hold', 0) or 0),
                    'sell':       int(row.get('sell', 0) or 0),
                    'strongSell': int(row.get('strongSell', 0) or 0),
                }
        except: pass
        return out
    except Exception as e: return {'error': str(e)}

def get_analyst(sym): return _cached(f'analyst:{sym}', lambda: _get_analyst(sym))

def get_scanner():
    scan_syms = [
        'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'GOOGL', 'META', 'NFLX', 'AMD', 'INTC',
        'JPM', 'BAC', 'GS', 'V', 'MA', 'XOM', 'CVX', 'PFE', 'JNJ', 'WMT',
        'SAP.DE', 'SIE.DE', 'BMW.DE', 'ALV.DE', 'VOW3.DE', 'BAS.DE', 'BAYN.DE',
        'DBK.DE', 'DTE.DE', 'MBG.DE', 'MUV2.DE', 'RWE.DE',
        'ASML.AS', 'LVMH.PA', 'TTE.PA', 'OR.PA', 'NESN.SW', 'NOVN.SW',
        'SHEL.L', 'AZN.L', 'BP.L', 'HSBA.L',
        '7203.T', '6758.T', '9984.T', '005930.KS', '9988.HK', '0700.HK',
        '^GSPC', '^NDX', '^DAX', '^FTSE', '^N225',
    ]
    results = []
    for sym in scan_syms:
        try:
            t = yf().Ticker(sym)
            df = t.history(period='5d', interval='1d', auto_adjust=True)
            if df is None or df.empty or len(df) < 2: continue
            df = df.dropna(subset=['Close'])
            if len(df) < 2: continue
            c   = float(df['Close'].iloc[-1])
            p   = float(df['Close'].iloc[-2])
            v   = int(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
            va  = float(df['Volume'].iloc[:-1].mean()) if len(df) > 1 else 0
            if c <= 0 or p <= 0: continue
            chg = (c - p) / p * 100
            vr  = round(v / va, 1) if va > 0 else 1.0
            if abs(chg) < 2.5 and vr < 2.0: continue
            name = sym
            try: name = (t.info.get('shortName') or t.info.get('longName') or sym)[:25]
            except: pass
            results.append({
                'sym': sym, 'name': name, 'price': round(c, 4),
                'chg': round(chg, 2), 'vol': v, 'volAvg': int(va),
                'volRatio': vr,
                'signal': 'big_move' if abs(chg) >= 2.5 else 'high_vol',
            })
        except: continue
    results.sort(key=lambda x: abs(x['chg']), reverse=True)
    return results[:30]

def search_symbol(query):
    try:
        out = []
        for q in (yf().Search(query, max_results=10).quotes or []):
            sym = q.get('symbol', '')
            if sym:
                out.append({
                    'sym':  sym,
                    'name': q.get('longname') or q.get('shortname', ''),
                    'type': q.get('quoteType', ''),
                    'exch': q.get('exchDisp', '') or q.get('exchange', ''),
                })
        return out
    except: return []

def call_ai_provider(provider, key, model, messages, system):
    ctx = ssl.create_default_context()
    if provider == 'anthropic':
        body = json.dumps({'model': model, 'max_tokens': 800, 'system': system, 'messages': messages}).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages', data=body, method='POST',
            headers={'Content-Type': 'application/json', 'x-api-key': key, 'anthropic-version': '2023-06-01'}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            return json.loads(r.read()).get('content', [{}])[0].get('text', '')
    elif provider == 'openai':
        body = json.dumps({'model': model, 'max_tokens': 800, 'messages': [{'role': 'system', 'content': system}] + messages}).encode()
        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions', data=body, method='POST',
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            return json.loads(r.read())['choices'][0]['message']['content']
    elif provider == 'gemini':
        contents = [{'role': 'user', 'parts': [{'text': system + '\n\n' + messages[0]['content']}]}] if messages else []
        for m in messages[1:]:
            contents.append({'role': 'user' if m['role'] == 'user' else 'model', 'parts': [{'text': m['content']}]})
        body = json.dumps({'contents': contents, 'generationConfig': {'maxOutputTokens': 800}}).encode()
        req = urllib.request.Request(
            f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}',
            data=body, method='POST', headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            return json.loads(r.read())['candidates'][0]['content']['parts'][0]['text']
    raise ValueError(f'Unknown provider: {provider}')

def get_trade_ideas(sym, provider, key, model, lang='de'):
    try:
        info = yf().Ticker(sym).info
        p = float(info.get('currentPrice') or info.get('regularMarketPrice') or 100)
        name = info.get('longName') or sym
        w52h = float(info.get('fiftyTwoWeekHigh') or 0)
        w52l = float(info.get('fiftyTwoWeekLow') or 0)
        rec = info.get('recommendationKey', '')
        tgt = float(info.get('targetMeanPrice') or 0)
        pe = info.get('trailingPE', 'N/A')
        beta = info.get('beta', 'N/A')
        if lang == 'de':
            prompt = f'Analysiere {name} ({sym}). Preis={p:.2f}|52W={w52h:.2f}/{w52l:.2f}|Konsens={rec}|Ziel={tgt:.2f}|KGV={pe}|Beta={beta}\nNUR JSON: {{"long":{{"setup":"Setup","entry":{p:.2f},"stopLoss":{round(p*.95,2)},"target1":{round(p*1.08,2)},"target2":{round(p*1.15,2)},"confidence":"hoch","rationale":"Begründung"}},"short":{{"setup":"Setup","entry":{p:.2f},"stopLoss":{round(p*1.05,2)},"target1":{round(p*.92,2)},"target2":{round(p*.85,2)},"confidence":"mittel","rationale":"Begründung"}},"call":{{"basispreis":{round(p*1.05,2)},"laufzeit":"3 Monate","rationale":"Grund","risiko":"mittel"}},"put":{{"basispreis":{round(p*.95,2)},"laufzeit":"3 Monate","rationale":"Grund","risiko":"mittel"}}}}'
        else:
            prompt = f'Analyze {name} ({sym}). price={p:.2f}|52W={w52h:.2f}/{w52l:.2f}|consensus={rec}|target={tgt:.2f}|PE={pe}|beta={beta}\nONLY JSON: {{"long":{{"setup":"Setup","entry":{p:.2f},"stopLoss":{round(p*.95,2)},"target1":{round(p*1.08,2)},"target2":{round(p*1.15,2)},"confidence":"high","rationale":"Reason"}},"short":{{"setup":"Setup","entry":{p:.2f},"stopLoss":{round(p*1.05,2)},"target1":{round(p*.92,2)},"target2":{round(p*.85,2)},"confidence":"medium","rationale":"Reason"}},"call":{{"strike":{round(p*1.05,2)},"expiry":"3 months","rationale":"Reason","risk":"medium"}},"put":{{"strike":{round(p*.95,2)},"expiry":"3 months","rationale":"Reason","risk":"medium"}}}}'
        text = call_ai_provider(provider, key, model, [{'role': 'user', 'content': prompt}], '')
        text = text.strip()
        if '```' in text: text = text.split('```')[1].lstrip('json').strip()
        return json.loads(text)
    except Exception as e: return {'error': str(e)}

def get_options_ideas(sym, provider, key, model, analyst_data, lang='de'):
    try:
        info = yf().Ticker(sym).info
        price = float(info.get('currentPrice') or info.get('regularMarketPrice') or 0)
        name = info.get('longName') or sym
        w52h = float(info.get('fiftyTwoWeekHigh') or 0)
        w52l = float(info.get('fiftyTwoWeekLow') or 0)
        beta = info.get('beta', 'N/A')
        rec = analyst_data.get('recommendation', '')
        target = analyst_data.get('targetMean', 0) or 0
        tgt_hi = analyst_data.get('targetHigh', 0) or 0
        tgt_lo = analyst_data.get('targetLow', 0) or 0
        n_anl = analyst_data.get('numAnalysts', 0) or 0
        upside = ((float(target) - price) / price * 100) if price > 0 and target else 0
        if lang == 'de':
            prompt = f'Optionsschein-Analyst. Analysiere {name} ({sym}): Kurs={price:.2f}, 52W={w52h:.2f}/{w52l:.2f}, Konsens={rec} ({n_anl} Analysten), Ziel=Ø{target:.2f} (H:{tgt_hi:.2f}/T:{tgt_lo:.2f}), Upside={upside:.1f}%, Beta={beta}\nNUR JSON: {{"summary":"2 Sätze","bias":"bullish/bearish/neutral","call":{{"empfehlung":"Kauf/Kein Kauf","basispreis":{round(price*1.05,2)},"laufzeit":"3-6 Monate","einstieg":{price:.2f},"stoppLoss":{round(price*0.9,2)},"kursziel":{round(float(target) if target else price*1.1,2)},"rationale":"Begründung","risiko":"hoch/mittel/niedrig"}},"put":{{"empfehlung":"Kauf/Kein Kauf","basispreis":{round(price*0.95,2)},"laufzeit":"3-6 Monate","einstieg":{price:.2f},"stoppLoss":{round(price*1.1,2)},"kursziel":{round(float(tgt_lo) if tgt_lo else price*0.9,2)},"rationale":"Begründung","risiko":"hoch/mittel/niedrig"}},"strategie":"2 Sätze"}}'
        else:
            prompt = f'Warrant analyst. Analyze {name} ({sym}): price={price:.2f}, 52W={w52h:.2f}/{w52l:.2f}, consensus={rec} ({n_anl} analysts), target=avg{target:.2f} (H:{tgt_hi:.2f}/L:{tgt_lo:.2f}), upside={upside:.1f}%, beta={beta}\nONLY JSON: {{"summary":"2 sentences","bias":"bullish/bearish/neutral","call":{{"recommendation":"Buy/No Buy","strike":{round(price*1.05,2)},"expiry":"3-6 months","entry":{price:.2f},"stopLoss":{round(price*0.9,2)},"target":{round(float(target) if target else price*1.1,2)},"rationale":"Rationale","risk":"high/medium/low"}},"put":{{"recommendation":"Buy/No Buy","strike":{round(price*0.95,2)},"expiry":"3-6 months","entry":{price:.2f},"stopLoss":{round(price*1.1,2)},"target":{round(float(tgt_lo) if tgt_lo else price*0.9,2)},"rationale":"Rationale","risk":"high/medium/low"}},"strategy":"2 sentences"}}'
        text = call_ai_provider(provider, key, model, [{'role': 'user', 'content': prompt}], '')
        text = text.strip()
        if '```' in text: text = text.split('```')[1].lstrip('json').strip()
        return json.loads(text)
    except Exception as e: return {'error': str(e)}

# ── FLASK ROUTES ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/chart')
def api_chart():
    sym = request.args.get('symbol', 'AAPL').upper()
    tf  = request.args.get('tf', '1mo')
    try:
        result = get_candles(sym, tf)
        print(f'  ↗ {sym}[{tf}] → {len(result["candles"])} candles ({result.get("interval_used","?")})')
        return jsonify(result)
    except Exception as e:
        return jsonify({'candles': [], 'found_sym': sym, 'error': str(e)})

@app.route('/api/quotes')
def api_quotes():
    syms = [s.strip() for s in request.args.get('symbols', '').split(',') if s.strip()]
    return jsonify({'quotes': get_quotes(syms)})

@app.route('/api/info')
def api_info():
    sym = request.args.get('symbol', 'AAPL')
    return jsonify(get_info(sym))

@app.route('/api/news')
def api_news():
    sym = request.args.get('symbol', 'AAPL')
    return jsonify({'news': get_news(sym)})

@app.route('/api/analyst')
def api_analyst():
    sym = request.args.get('symbol', 'AAPL')
    return jsonify(get_analyst(sym))

@app.route('/api/search')
def api_search():
    q = request.args.get('q', '')
    return jsonify({'results': search_symbol(q)})

@app.route('/api/scanner')
def api_scanner():
    try:
        results = get_scanner()
        print(f'  🔍 Scanner → {len(results)} results')
        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'results': [], 'error': str(e)})

@app.route('/api/ai', methods=['POST'])
def api_ai():
    body = request.json or {}
    key = body.get('key', '')
    if not key: return jsonify({'error': 'No API key'})
    try:
        text = call_ai_provider(body.get('provider', 'anthropic'), key, body.get('model', 'claude-sonnet-4-20250514'), body.get('messages', []), body.get('system', ''))
        return jsonify({'text': text})
    except Exception as e: return jsonify({'error': str(e)})

@app.route('/api/tradeideas', methods=['POST'])
def api_tradeideas():
    body = request.json or {}
    key = body.get('key', '')
    if not key: return jsonify({'error': 'No API key'})
    try:
        r = get_trade_ideas(body.get('symbol', 'AAPL'), body.get('provider', 'anthropic'), key, body.get('model', 'claude-sonnet-4-20250514'), body.get('lang', 'de'))
        return jsonify(r)
    except Exception as e: return jsonify({'error': str(e)})

@app.route('/api/optionsideas', methods=['POST'])
def api_optionsideas():
    body = request.json or {}
    key = body.get('key', '')
    if not key: return jsonify({'error': 'No API key'})
    try:
        r = get_options_ideas(body.get('symbol', 'AAPL'), body.get('provider', 'anthropic'), key, body.get('model', 'claude-sonnet-4-20250514'), body.get('analyst', {}), body.get('lang', 'de'))
        return jsonify(r)
    except Exception as e: return jsonify({'error': str(e)})

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '11.0'})

if __name__ == '__main__':
    print(f'\n  ChartAI Pro  →  http://localhost:{PORT}\n')
    app.run(host='0.0.0.0', port=PORT, debug=False)
