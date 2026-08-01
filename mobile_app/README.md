# MyNutriApp — mobile (Flutter)

App paziente iOS/Android. UI allineata all’identità di `style_user.css` (dark + accent `#ff9a56`, Manrope).

Al momento le feature usano **dati mock** locali. Il login API (`POST /api/v1/auth/login`) resta predisposto; per navigare senza backend usa **Entra in demo**.

## Setup

```bash
export PATH="$HOME/development/flutter/bin:$PATH"
cd mobile_app
flutter pub get
flutter run
```

## Ambiente

Vedi [`.env.example`](.env.example):

| Variabile | Default | Note |
|-----------|---------|------|
| `API_BASE_URL` | `http://127.0.0.1:5000` | Android emulator: `http://10.0.2.2:5000` |
| `USE_MOCK_DATA` | `true` | Schermate su repository mock |

Override:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:5000
```

## Navigazione

Bottom nav: Home · Dieta · Appuntamenti · Progressi · Profilo  

Da Profilo → Altro: Allenamenti · Documenti · Diario · Logout
