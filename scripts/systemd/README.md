# Watchdog IB Gateway — units systemd (user)

Ces 2 fichiers pilotent `scripts/ibgw_watchdog.sh` : ils vérifient le **port 4001**
toutes les 5 min et redémarrent `ibgw.service` s'il est fermé (le reset hebdo IBKR
laisse parfois le Gateway bloqué « logged out » sans tuer le process → `Restart=always`
ne suffit pas).

## Installation (après un réinstall / nouvelle machine)

```bash
cp scripts/systemd/ibgw-watchdog.service scripts/systemd/ibgw-watchdog.timer \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ibgw-watchdog.timer
```

## Vérifier / gérer

```bash
systemctl --user list-timers ibgw-watchdog.timer   # prochain passage
systemctl --user status ibgw-watchdog.service      # dernier run
tail -f data/collected_live/watchdog.log           # trace (vide = tout va bien)
```

Notif Discord optionnelle : poser `DISCORD_WEBHOOK=https://...` dans `.env`.

> ⚠️ Le service `ibgw.service` lui-même (Gateway sur Xvfb :99) n'est PAS inclus ici —
> il vit aussi dans `~/.config/systemd/user/` mais n'a pas été versionné. À ajouter si
> on veut une repro complète de la machine.
