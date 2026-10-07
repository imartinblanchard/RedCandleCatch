# Reproduction de la machine (IB Gateway + collecte auto)

Tout ce qu'il faut pour relancer le système sur un PC neuf / après un réinstall.
**Aucun secret ici** : `scripts/ibc/config.ini.template` est caviardé — tes vrais
identifiants IBKR restent uniquement sur la machine (jamais dans git).

## Les pièces

| Fichier (dans le dépôt) | Destination sur la machine | Rôle |
|---|---|---|
| `scripts/systemd/xvfb99.service` | `~/.config/systemd/user/` | écran virtuel Xvfb :99 |
| `scripts/systemd/ibgw.service` | `~/.config/systemd/user/` | lance IB Gateway (IBC) sur Xvfb au boot |
| `scripts/systemd/ibgw-watchdog.service` + `.timer` | `~/.config/systemd/user/` | surveille le port 4001, restart si figé |
| `scripts/ibc/gatewaystart.sh` | `~/ibc/` | launcher IBC (JAVA_PATH = JRE embarqué) |
| `scripts/ibc/config.ini.template` | `~/ibc/config.ini` (**+ remettre les identifiants**) | config IBC (login, AutoRestartTime 20:05) |
| `scripts/ibc/jts.ini` | `~/Jts/jts.ini` | réglages Gateway (AutoRestart, port API 4001) |
| `scripts/crontab.txt` | `crontab -e` | tâches auto (collecte 08:00, fetch 16:20) |

## Installation

```bash
# 1) dépendances Python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # yfinance >=1.7.0 requis (news)

# 2) config IBC (REMETTRE les identifiants à la main, jamais dans git)
cp scripts/ibc/config.ini.template ~/ibc/config.ini
#   -> éditer ~/ibc/config.ini : IbLoginId / IbPassword
cp scripts/ibc/gatewaystart.sh ~/ibc/
cp scripts/ibc/jts.ini ~/Jts/jts.ini

# 3) services systemd (Gateway + watchdog)
cp scripts/systemd/*.service scripts/systemd/*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
loginctl enable-linger "$USER"           # démarre sans session ouverte
systemctl --user enable --now xvfb99.service ibgw.service ibgw-watchdog.timer

# 4) tâches cron (collecte quotidienne)
crontab scripts/crontab.txt              # ⚠️ écrase le crontab existant — vérifier d'abord

# 5) vérifier
bash scripts/check_ibgw.sh               # doit afficher "CONNECTÉ sur 4001"
```

> Première connexion = **2FA** à approuver sur l'app IBKR Mobile (mort à froid).
> Notif Discord du watchdog : poser `DISCORD_WEBHOOK=https://...` dans `.env`.
> `crontab.txt` contient aussi une ligne du projet N2 (sans rapport) — à adapter.
