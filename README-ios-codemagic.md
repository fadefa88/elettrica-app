# Build iOS con Codemagic

Questa guida prepara il sito statico **Elettrica o Termica** come app iOS tramite Capacitor e Codemagic.

## File aggiunti

- `package.json` — dipendenze Capacitor e script npm.
- `capacitor.config.ts` — configurazione app iOS.
- `scripts/build-ios-web.js` — crea la cartella `www/` usata da Capacitor.
- `codemagic.yaml` — workflow iOS per Codemagic.
- `.gitignore` — esclude `node_modules`, `www`, `ios`, certificati e segreti.

## Bundle ID

Usiamo:

```text
it.elettricaotermica.app
```

Deve essere creato anche in Apple Developer / App Store Connect.

## Setup Codemagic

1. Vai su https://codemagic.io
2. Collegati con GitHub.
3. Add application.
4. Seleziona il repository `fadefa88/elettrica`.
5. Seleziona workflow YAML.
6. Codemagic deve rilevare `codemagic.yaml` nella root.

## App Store Connect API key

In App Store Connect:

1. Users and Access.
2. Integrations.
3. App Store Connect API.
4. Crea una nuova API key.
5. Ruolo consigliato: App Manager.
6. Scarica il file `.p8` una sola volta.
7. Prendi nota di Key ID e Issuer ID.

In Codemagic:

1. Team settings.
2. Integrations.
3. Developer Portal.
4. Add key.
5. Nome consigliato: `codemagic_app_store_connect`.
6. Inserisci Issuer ID, Key ID e carica il `.p8`.

Il nome `codemagic_app_store_connect` deve corrispondere a quello nel file `codemagic.yaml`:

```yaml
integrations:
  app_store_connect: codemagic_app_store_connect
```

## Code signing

Nel workflow usiamo:

```yaml
ios_signing:
  distribution_type: app_store
  bundle_identifier: it.elettricaotermica.app
```

Codemagic userà certificati/profili App Store collegati al bundle ID.

## Primo build

In Codemagic:

1. Apri l'app `elettrica`.
2. Start new build.
3. Branch: `main`.
4. Workflow: `iOS Capacitor - TestFlight`.
5. Start build.

Il primo obiettivo è ottenere un artifact `.ipa` scaricabile. La pubblicazione automatica su TestFlight è inizialmente disattivata:

```yaml
submit_to_testflight: false
submit_to_app_store: false
```

Quando il build funziona, puoi attivare TestFlight mettendo:

```yaml
submit_to_testflight: true
```

## Debug errori frequenti

### Errore signing

Controlla:

- API key App Store Connect caricata in Codemagic.
- Nome integrazione uguale a `codemagic_app_store_connect`.
- Bundle ID creato in Apple Developer.
- App record creato in App Store Connect.
- Certificato/profilo App Store disponibili.

### Errore Xcode version

Nel file `codemagic.yaml` modifica:

```yaml
xcode: 16.4
```

oppure rimuovi la riga per usare il default Codemagic.

### Errore Capacitor

Controlla che `npm install` sia andato a buon fine e che `www/index.html` venga creato dallo script:

```bash
npm run build:ios-web
```

## Test locale opzionale

Su Mac:

```bash
npm install
npm run build:ios-web
npx cap add ios
npx cap sync ios
npx cap open ios
```

