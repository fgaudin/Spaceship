# SimSup's password

The web server asks for a login before serving the instructor station (`simsup.html`, `simsup.js`, `simsup.css`),
from `simsup.htpasswd` here. That file is not in git: create it on each machine.

```sh
printf 'simsup:%s\n' "$(openssl passwd -apr1 'the password')" > panels/auth/simsup.htpasswd
docker compose restart panel
```

It only locks the page. The commands go over the MQTT bus, which has no accounts: anyone on the network with an
MQTT client and the topic names could still send them (accepted for a classroom on a local network).
