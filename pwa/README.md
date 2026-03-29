# Jarvis PWA - Progressive Web App

Progressive Web App multi-dispositivo per Jarvis AI Assistant.

## 🎯 Caratteristiche

- ✅ **Funziona ovunque**: iOS, Android, Windows, Mac, Linux
- ✅ **Installabile**: Aggiungi alla home screen come app nativa
- ✅ **Controllo vocale**: Speech-to-text e text-to-speech integrati
- ✅ **Offline support**: Service Worker per funzionamento offline
- ✅ **Responsive**: Design mobile-first
- ✅ **Real-time**: WebSocket per comunicazione istantanea (con fallback HTTP)
- ✅ **Dark theme**: Interfaccia scura ottimizzata per batteria
- ✅ **Push notifications**: Notifiche anche quando l'app è chiusa

## 📁 Struttura

```
pwa/
├── index.html              # HTML principale
├── manifest.json           # PWA manifest
├── sw.js                   # Service Worker
├── serve.py                # Server di sviluppo
├── css/
│   └── main.css            # Stili principali
├── js/
│   ├── config.js           # Configurazione
│   ├── api.js              # Comunicazione API/WebSocket
│   ├── voice.js            # Riconoscimento/sintesi vocale
│   ├── ui.js               # Gestione interfaccia
│   └── app.js              # Entry point applicazione
├── icons/                  # Icone PWA (varie dimensioni)
└── assets/                 # Risorse statiche
```

## 🚀 Avvio rapido

### 1. Avvia il server backend (Jarvis)

```bash
cd /home/extreamboy/ai-assistant
docker compose up -d
```

### 2. Avvia il server PWA

```bash
cd pwa
python3 serve.py
```

Il server sarà disponibile su `http://localhost:3000`

### 3. Apri nel browser

- **Desktop**: http://localhost:3000
- **Mobile**: http://<tuo-ip>:3000 (assicurati di essere sulla stessa rete)

## 📱 Installazione su dispositivi

### iOS (iPhone/iPad)

1. Apri Safari
2. Vai su http://<tuo-ip>:3000
3. Tap sull'icona "Condividi" (quadrato con freccia)
4. Scorri e seleziona "Aggiungi a Home"
5. Conferma

L'app apparirà nella home screen come app nativa!

### Android

1. Apri Chrome
2. Vai su http://<tuo-ip>:3000
3. Tap sul menu (⋮)
4. Seleziona "Aggiungi a schermata Home" o "Installa app"
5. Conferma

### Desktop (Chrome/Edge)

1. Apri http://localhost:3000
2. Guarda la barra degli indirizzi per l'icona "Installa"
3. Click e conferma

Oppure: Menu → Installa Jarvis

## ⚙️ Configurazione

Tap sull'icona ⚙️ (in basso a destra) per accedere alle impostazioni:

- **Server URL**: Indirizzo del backend Jarvis (default: http://localhost:8000)
- **User ID**: Il tuo identificativo univoco
- **Risposte vocali automatiche**: Attiva TTS automatico
- **Modalità scura**: Toggle tema (già abilitato)

## 🎤 Funzionalità vocali

### Riconoscimento vocale

- Tap sul pulsante 🎤 (microfono rosso)
- Parla chiaramente in italiano
- Il testo apparirà man mano che parli
- Rilascia o attendi per inviare

### Sintesi vocale (TTS)

- Le risposte vengono lette automaticamente se abilitato nelle impostazioni
- Usa browser moderni (Chrome, Edge, Safari) per migliori risultati

### Supporto browser

| Feature | Chrome | Safari | Firefox | Edge |
|---------|--------|--------|---------|------|
| STT     | ✅     | ✅     | ❌      | ✅   |
| TTS     | ✅     | ✅     | ✅      | ✅   |
| PWA     | ✅     | ✅     | ⚠️      | ✅   |

## 🔧 Sviluppo

### Modificare l'interfaccia

Edita i file in `css/` e `js/`, poi ricarica la pagina.

### Testare su dispositivo mobile

1. Trova il tuo IP locale:
   ```bash
   ip addr  # Linux
   ifconfig  # Mac
   ipconfig  # Windows
   ```

2. Sul dispositivo mobile, connettiti alla stessa rete WiFi

3. Apri browser e vai su `http://<tuo-ip>:3000`

### Debug

- **Console del browser**: F12 → Console
- **Service Worker**: F12 → Application → Service Workers
- **Network**: F12 → Network (vedi richieste API)

### Aggiornare Service Worker

Dopo modifiche al codice:

```javascript
// In browser console:
navigator.serviceWorker.getRegistrations().then(registrations => {
    registrations.forEach(reg => reg.unregister());
});

// Poi ricarica la pagina (Ctrl+Shift+R)
```

## 🌐 Deploy in produzione

### Opzione 1: Nginx

```nginx
server {
    listen 80;
    server_name jarvis.tuodominio.com;

    root /path/to/ai-assistant/pwa;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API al backend
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
}
```

### Opzione 2: Vercel/Netlify

1. Crea un repo Git con la cartella `pwa/`
2. Collega a Vercel/Netlify
3. Deploy automatico!

**Nota**: Dovrai gestire il backend separatamente.

### Opzione 3: Docker

Crea `pwa/Dockerfile`:

```dockerfile
FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80
```

Poi:

```bash
docker build -t jarvis-pwa .
docker run -p 80:80 jarvis-pwa
```

## 🔐 HTTPS (obbligatorio per alcune feature)

Alcune funzionalità (fotocamera, GPS, notifiche push) richiedono HTTPS.

Usa Let's Encrypt con certbot:

```bash
sudo certbot --nginx -d jarvis.tuodominio.com
```

## 🐛 Troubleshooting

### "Server unreachable"

- Verifica che docker compose sia attivo
- Controlla che l'URL nelle impostazioni sia corretto
- Prova http://localhost:8000/health nel browser

### Voce non funziona su iOS

- Safari richiede HTTPS per STT
- Usa HTTP solo in sviluppo locale
- Deploy con HTTPS per produzione

### App non si installa

- Verifica che manifest.json sia accessibile
- Controlla che tutte le icone esistano
- Usa HTTPS (alcuni browser lo richiedono)

### Service Worker non si aggiorna

- Forza ricarica: Ctrl+Shift+R (o Cmd+Shift+R su Mac)
- Cancella cache del browser
- Disinstalla e reinstalla PWA

## 📊 Performance

- **First Load**: ~50KB (HTML+CSS+JS gzipped)
- **Cached Load**: <1KB (solo API calls)
- **Offline**: Funziona completamente (solo UI, API richiede connessione)

## 🎨 Personalizzazione

### Cambiare colori

Edita `css/main.css`:

```css
:root {
    --primary: #0f3460;      /* Blu primario */
    --secondary: #16213e;    /* Blu secondario */
    --accent: #e94560;       /* Rosso accento */
    --bg-dark: #0a0e27;      /* Sfondo scuro */
    /* ... */
}
```

### Cambiare icone

1. Crea icone personalizzate (formati: 72, 96, 128, 144, 152, 192, 384, 512px)
2. Sostituisci i file in `icons/`
3. Ricarica l'app

### Aggiungere screenshot

Metti screenshot in `screenshots/` e aggiorna `manifest.json`

## 🚧 Roadmap

- [ ] Fotocamera integrata (capture + OCR)
- [ ] GPS location tracking
- [ ] Push notifications dal backend
- [ ] Modalità offline completa (cache conversazioni)
- [ ] Supporto multi-lingua
- [ ] Temi personalizzabili
- [ ] Widget per Android/iOS
- [ ] Apple Watch companion
- [ ] Condivisione contenuti (Share API)

## 📄 Licenza

Stesso progetto Jarvis AI Assistant

## 🆘 Supporto

Problemi? Apri una issue su GitHub o contatta lo sviluppatore.
