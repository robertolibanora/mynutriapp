# MyNutriApp — mobile (Flutter)

App paziente iOS/Android. UI allineata all’identità di `style_user.css` (dark + accent `#ff9a56`, Manrope).

Logo ufficiale: `assets/branding/logo.png` — widget `AppLogo` / `AppBrandHeader` in `lib/widgets/app_logo.dart`. Icone launcher Android/iOS/web generate dallo stesso asset.

Al momento le feature usano **dati mock** locali. Il login API (`POST /api/v1/auth/login`) resta predisposto; per navigare senza backend usa **Entra in demo**.

## Setup

```bash
export PATH="$HOME/development/flutter/bin:$PATH"
cd mobile_app
flutter pub get
cd ios && pod install && cd ..
flutter run
```

### iOS (CocoaPods only)

Le dipendenze native iOS usano **solo CocoaPods** (SPM disabilitato in `pubspec.yaml`).
Serve a evitare il crash dyld `DKImagePickerController.framework` (da `file_picker`).

Su Mac, il flusso consigliato:

```bash
./w.sh                 # da repo root o da mobile_app/
# clean → pod install → xcodebuild (DerivedData dedicata) → simctl install → launch
```

DerivedData del progetto: `mobile_app/build/ios/DerivedData` (mai la DerivedData globale di Xcode).

## Ambiente

Vedi [`.env.example`](.env.example):

| Variabile | Default | Note |
|-----------|---------|------|
| `API_BASE_URL` | `https://stage.mynutriapp.cloud` | Staging HTTPS per QA / store |
| `USE_MOCK_DATA` | `false` | `true` solo in sviluppo locale |

Build store / QA contro staging:

```bash
flutter build appbundle --dart-define=API_BASE_URL=https://stage.mynutriapp.cloud --dart-define=USE_MOCK_DATA=false
flutter build ipa --dart-define=API_BASE_URL=https://stage.mynutriapp.cloud --dart-define=USE_MOCK_DATA=false
```

Dev locale:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:5000 --dart-define=USE_MOCK_DATA=true
```

## Preview iPhone (PWA web)

Build e URL:

```bash
export PATH="$HOME/development/flutter/bin:$PATH"
cd mobile_app
flutter build web --release --base-href=/m/ \
  --dart-define=API_BASE_URL=https://stage.mynutriapp.cloud \
  --dart-define=USE_MOCK_DATA=false
```

Poi apri su iPhone (QR): https://stage.mynutriapp.cloud/static/img/mobile-qr.html  
App: https://stage.mynutriapp.cloud/m/

## Navigazione

Bottom nav: Home · Dieta · Appuntamenti · Progressi · Profilo  

Da **Profilo → Privacy e dati (GDPR)**:
- stato consenso privacy / marketing
- toggle marketing (`PATCH /api/v1/me/privacy`)
- export JSON (`GET /api/v1/me/export`)
- richiesta cancellazione (`POST /api/v1/me/erasure`)

Login con telefono ambiguo: campo email opzionale (`phone_ambiguous` → 409).
