# Bascule IB Gateway → Xvfb + systemd (stabilité, fini le 2FA récurrent)

Objectif : le Gateway ne meurt plus (isolé du bureau :0 qui sature, supervisé par systemd,
survit au reboot). Il ne fera QUE des soft-restarts → **plus de 2FA** (sauf ce 1er cold start).

## Déjà en place (fait le 27/09, non destructif)
- `~/.config/systemd/user/xvfb99.service`  (écran virtuel :99, Restart=always)
- `~/.config/systemd/user/ibgw.service`    (Gateway via IBC sur :99, Restart=always, prism=sw)
- linger activé (`loginctl show-user martin` → Linger=yes) → survit reboot/logout

## Reste (optionnel, pour VOIR/cliquer le Gateway — utile au 1er 2FA)
    sudo apt install -y x11vnc
    # puis, pour voir l'écran :99 depuis un client VNC :
    x11vnc -display :99 -localhost -nopw -once &

## LA BASCULE (quand tu es dispo avec ton téléphone — ~2 min, 1 SEUL 2FA)
Tout dans un terminal :

    # 1. Couper le Gateway actuel (lancé à la main sur :0) + son IBC
    pkill -f gatewaystart.sh ; pkill -f ibcstart.sh ; pkill -f ibcalpha.ibc.IbcGateway
    sleep 3

    # 2. Démarrer les services (Xvfb puis Gateway) et les activer au boot
    export XDG_RUNTIME_DIR=/run/user/1000
    systemctl --user enable --now xvfb99.service
    systemctl --user enable --now ibgw.service

    # 3. Approuver le 2FA sur le téléphone (push IB Key) — le SEUL de la bascule
    #    Pour voir l'écran de login si besoin : x11vnc -display :99 -localhost -nopw -once &

    # 4. Vérifier
    systemctl --user status ibgw.service --no-pager
    bash /home/martin/dev/stock-journal-long/scripts/check_ibgw.sh   # → CONNECTÉ 4001

## Ensuite (au quotidien)
- État : `systemctl --user status ibgw.service`
- Logs : `journalctl --user -u ibgw.service -f`
- Redémarrer manuellement : `systemctl --user restart ibgw.service`
- Le Gateway se relance seul s'il meurt (systemd) ; auto-restart quotidien 20:05 (IBC) sans 2FA.

## Rollback (revenir à l'ancienne méthode)
    systemctl --user disable --now ibgw.service xvfb99.service
    start_ibgw   # (l'alias sur :0, comme avant)
