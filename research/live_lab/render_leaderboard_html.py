#!/usr/bin/env python3
"""Régénère un visuel HTML autonome du leaderboard depuis leaderboard_latest.csv.

Classé par edge/trade (pas par le « profit % » projeté, qui est un fantasme
linéaire sur n jours). Notre stratégie LIVE est épinglée en hero + surlignée.
Écrit research/live_lab/leaderboard.html — ouvrable direct dans un navigateur.
Appelé par run_leaderboard.sh après chaque run du leaderboard (cron en semaine).
"""
import os, json, html, datetime as dt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV  = os.path.join(HERE, 'leaderboard_latest.csv')
HIST = os.path.join(HERE, 'leaderboard_history.csv')
OUT  = os.path.join(HERE, 'leaderboard.html')
TOP  = 12          # nb de stratégies affichées (classées par edge/trade)
OURS = 'LIVE'      # une stratégie dont le label contient ceci = la nôtre


def _fr(v, dec=2):
    """+1,23 % à la française (virgule, signe moins typographique)."""
    s = f"{abs(v):.{dec}f}".replace('.', ',')
    return ('+' if v >= 0 else '−') + s + ' %'


def build():
    df = pd.read_csv(CSV)
    # On classe par PROFIT (rendement composé réel du portefeuille sur les jours live,
    # sizing par le risque, slippage ON). Il intègre la fréquence et écrase les flukes
    # à petit n — contrairement à l'edge/trade brut qui remonterait du bruit en tête.
    # 1 ligne/stratégie = celle au meilleur profit (sizing de référence, risque 2%).
    g = (df.sort_values('profit', ascending=False)
           .drop_duplicates('strategie', keep='first')
           .reset_index(drop=True))

    live = df[df.strategie.str.contains(OURS, case=False, regex=False)]
    live_n = int(live.n.iloc[0]) if len(live) else int(df.n.max())
    live_row = g[g.strategie.str.contains(OURS, case=False, regex=False)]
    # rang de notre stratégie dans le classement profit (1-indexé)
    ours_rank = int(live_row.index[0]) + 1 if len(live_row) else None
    lr = live_row.iloc[0] if len(live_row) else None

    # méta (dates, run) depuis l'historique
    n_days, couvre, run = '?', '?', ''
    if os.path.exists(HIST):
        h = pd.read_csv(HIST).iloc[-1]
        n_days, couvre = h.get('n_days', '?'), h.get('couvre', '?')
        run = str(h.get('run', ''))[:10]
    try:
        run_fr = dt.datetime.fromisoformat(run).strftime('%d/%m/%Y') if run else ''
    except ValueError:
        run_fr = run

    # row = [nom, profit%, exp/tr%, OOS(profit_oos)%, ours] — barre=profit, chip=OOS
    rows = []
    for _, x in g.head(TOP).iterrows():
        ours = OURS.lower() in str(x.strategie).lower()
        rows.append([html.escape(str(x.strategie)), round(float(x.profit), 2),
                     round(float(x.exp_tr), 2), round(float(x.profit_oos), 2), ours])
    max_bar = max(1.0, max(r[1] for r in rows)) * 1.06

    # chiffres du hero (notre stratégie LIVE)
    if lr is not None:
        h_prof = _fr(lr.profit, 1)
        h_edge = _fr(lr.exp_tr)
        h_oos  = _fr(lr.profit_oos, 1)
        h_edge_cls = 'good' if lr.exp_tr >= 0 else 'bad'
        h_oos_cls  = 'good' if lr.profit_oos >= 0 else 'bad'
        h_trday = f"{lr.tr_day:.1f}".replace('.', ',')
    else:
        h_prof = h_edge = h_oos = h_trday = '—'
        h_edge_cls = h_oos_cls = 'good'

    sub = (f"{live_n} trades · {n_days} séances live · OOS = jours de test · "
           f"run du {run_fr} · couvre {couvre}")
    rank_txt = f"n°{ours_rank} sur {len(g)} au classement profit" if ours_rank else ''

    page = TEMPLATE
    repl = {
        '__SUB__': html.escape(sub),
        '__RANK__': html.escape(rank_txt),
        '__H_PROF__': h_prof,
        '__H_EDGE__': h_edge, '__H_EDGE_CLS__': h_edge_cls,
        '__H_OOS__': h_oos, '__H_OOS_CLS__': h_oos_cls,
        '__H_TRDAY__': h_trday,
        '__DATA__': json.dumps(rows, ensure_ascii=False),
        '__MAX__': repr(round(max_bar, 3)),
    }
    for k, v in repl.items():
        page = page.replace(k, str(v))

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(page)
    print(f"[render] {OUT} écrit — {len(rows)} stratégies, notre LIVE {rank_txt}")


TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RedCandleCatch — Leaderboard v3</title>
<style>
  :root{color-scheme:light;--plane:#f7f7f4;--surface:#fcfcfb;--ink:#141311;--ink-2:#52514e;
    --muted:#898781;--hair:#e4e3dc;--ours:#2a78d6;--ours-soft:rgba(42,120,214,.10);
    --bar-rest:#bfbeb6;--bar-rest-track:#ededea;--good:#0a8f24;--bad:#c73434;
    --good-bg:rgba(10,143,36,.12);--bad-bg:rgba(199,52,52,.12);--radius:10px;}
  @media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
    --plane:#0d0d0c;--surface:#191917;--ink:#f4f3ee;--ink-2:#c3c2b7;--muted:#8f8e86;--hair:#2c2c2a;
    --ours:#4d94ec;--ours-soft:rgba(77,148,236,.14);--bar-rest:#56554f;--bar-rest-track:#232321;
    --good:#39c45a;--bad:#ef6a6a;--good-bg:rgba(57,196,90,.16);--bad-bg:rgba(239,106,106,.16);}}
  :root[data-theme="dark"]{color-scheme:dark;--plane:#0d0d0c;--surface:#191917;--ink:#f4f3ee;
    --ink-2:#c3c2b7;--muted:#8f8e86;--hair:#2c2c2a;--ours:#4d94ec;--ours-soft:rgba(77,148,236,.14);
    --bar-rest:#56554f;--bar-rest-track:#232321;--good:#39c45a;--bad:#ef6a6a;
    --good-bg:rgba(57,196,90,.16);--bad-bg:rgba(239,106,106,.16);}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--plane);color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.45;-webkit-font-smoothing:antialiased;}
  .wrap{max-width:860px;margin:0 auto;padding:32px 20px 56px;}
  .eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600;margin:0 0 6px;}
  h1{font-size:26px;line-height:1.15;margin:0 0 4px;text-wrap:balance;}
  .sub{color:var(--ink-2);font-size:14px;margin:0;}
  .hero{margin:26px 0 30px;background:var(--surface);border:1px solid var(--hair);
    border-left:4px solid var(--ours);border-radius:var(--radius);padding:20px 22px;box-shadow:0 1px 2px rgba(0,0,0,.04);}
  .hero-top{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:16px;}
  .tag-ours{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#fff;
    background:var(--ours);padding:3px 8px;border-radius:999px;}
  .hero-name{font-size:17px;font-weight:650;}
  .hero-rank{margin-left:auto;font-size:13px;color:var(--muted);}
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;}
  .stat{display:flex;flex-direction:column;gap:2px;}
  .stat .k{font-size:12px;color:var(--muted);font-weight:500;}
  .stat .v{font-size:22px;font-weight:680;font-variant-numeric:tabular-nums;letter-spacing:-.01em;}
  .stat .v.good{color:var(--good);} .stat .v.bad{color:var(--bad);}
  .hero-note{margin:16px 0 0;font-size:13px;color:var(--ink-2);border-top:1px solid var(--hair);padding-top:12px;}
  .section-label{font-size:12px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:600;margin:0 0 4px;}
  .legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);margin:6px 0 16px;}
  .legend .sw{display:inline-flex;align-items:center;gap:6px;}
  .legend .chip{width:11px;height:11px;border-radius:3px;}
  .rows{display:flex;flex-direction:column;gap:3px;}
  .row{display:grid;grid-template-columns:22px minmax(0,1fr) 150px;align-items:center;gap:12px;padding:9px 12px;border-radius:8px;}
  .row.ours{background:var(--ours-soft);}
  .rank{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;text-align:right;}
  .row.ours .rank{color:var(--ours);font-weight:700;}
  .lab{min-width:0;}
  .lab .nm{font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .row.ours .lab .nm{font-weight:650;}
  .bar-track{margin-top:5px;height:9px;border-radius:5px;background:var(--bar-rest-track);overflow:hidden;}
  .bar-fill{height:100%;border-radius:5px;background:var(--bar-rest);}
  .row.ours .bar-fill{background:var(--ours);}
  .metrics{display:flex;align-items:center;justify-content:flex-end;gap:10px;}
  .exptr{font-size:14px;font-weight:650;font-variant-numeric:tabular-nums;min-width:52px;text-align:right;}
  .oos{font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;padding:2px 7px;border-radius:999px;min-width:62px;text-align:center;}
  .oos.good{color:var(--good);background:var(--good-bg);} .oos.bad{color:var(--bad);background:var(--bad-bg);}
  .foot{margin-top:26px;padding-top:16px;border-top:1px solid var(--hair);font-size:12.5px;color:var(--ink-2);line-height:1.55;}
  .foot b{color:var(--ink);font-weight:650;}
  @media (max-width:560px){.stats{grid-template-columns:repeat(2,1fr);row-gap:16px;}
    .row{grid-template-columns:20px minmax(0,1fr) 128px;gap:8px;}
    .hero-rank{width:100%;margin:4px 0 0;order:3;}}
</style>
</head>
<body>
<div class="wrap">
  <p class="eyebrow">RedCandleCatch · live_lab</p>
  <h1>Leaderboard des stratégies — v3</h1>
  <p class="sub">__SUB__</p>

  <div class="hero">
    <div class="hero-top">
      <span class="tag-ours">Notre stratégie LIVE</span>
      <span class="hero-name">repli 8 % · capitulation · gap 5-10 % · hold-to-EOD</span>
      <span class="hero-rank">__RANK__</span>
    </div>
    <div class="stats">
      <div class="stat"><span class="k">Profit (15 j)</span><span class="v">__H_PROF__</span></div>
      <div class="stat"><span class="k">Edge / trade</span><span class="v __H_EDGE_CLS__">__H_EDGE__</span></div>
      <div class="stat"><span class="k">OOS (test)</span><span class="v __H_OOS_CLS__">__H_OOS__</span></div>
      <div class="stat"><span class="k">Trades / jour</span><span class="v">__H_TRDAY__</span></div>
    </div>
    <p class="hero-note">Classé par <b>profit</b> : rendement composé sur les jours live (sizing 2 %, slippage ON) — intègre la fréquence, écrase les variantes à petit <i>n</i>. <b>Edge/trade</b> = gain moyen par trade ; <b>OOS</b> = profit sur les jours de test (hors échantillon).</p>
  </div>

  <p class="section-label">Classement par profit</p>
  <div class="legend">
    <span class="sw"><span class="chip" style="background:var(--ours)"></span>Notre stratégie</span>
    <span class="sw"><span class="chip" style="background:var(--bar-rest)"></span>Autres variantes testées</span>
    <span class="sw">barre = profit · chiffre = edge/trade · pastille = OOS</span>
  </div>
  <div class="rows" id="rows"></div>

  <div class="foot"><b>⚠️ Borne supérieure</b> — biais du survivant, fills optimistes, P&amp;L brut (hors commissions). Peu de séances live = bruit. Seuls crédibles : l'edge/trade et l'OOS, à confirmer sur le forward live.</div>
</div>
<script>
  const data = __DATA__;
  const max = __MAX__;
  const fmt = v => (v>=0?"+":"−") + Math.abs(v).toFixed(2).replace(".",",") + " %";
  const rows = document.getElementById("rows");
  data.forEach((d,i)=>{
    const [nm,prof,ex,oos,ours]=d;
    const w=Math.max(3,(prof/max)*100);
    const sign=oos>=0?"good":"bad";
    const el=document.createElement("div");
    el.className="row"+(ours?" ours":"");
    el.innerHTML='<div class="rank">'+(i+1)+'</div>'+
      '<div class="lab"><div class="nm">'+nm+'</div>'+
        '<div class="bar-track"><div class="bar-fill" style="width:'+w+'%"></div></div></div>'+
      '<div class="metrics"><span class="exptr">'+fmt(ex)+'</span>'+
        '<span class="oos '+sign+'">'+fmt(oos)+'</span></div>';
    rows.appendChild(el);
  });
</script>
</body>
</html>
"""


if __name__ == '__main__':
    build()
