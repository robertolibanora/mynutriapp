echo "Ciao"

git add .
git diff --cached --quiet && echo "Nessuna modifica da committare." || git commit -m "$MSG"
git push

echo "Git Fatto!"

time sleep 1

clear

echo "Riavvio..."

sudo systemctl restart mynutriapp.service

echo "Password?"

time sleep 1

Clear

echo "Fatto!"

time sleep 1

echo "Build mobile..."

export PATH="${HOME}/development/flutter/bin:$PATH"
(
  cd "$(dirname "$0")/mobile_app"
  flutter pub get
  flutter build apk --release \
    --dart-define=API_BASE_URL=https://stage.mynutriapp.cloud \
    --dart-define=USE_MOCK_DATA=false
)

echo "Mobile build fatta!"


time sleep 1

echo "Gioenale?"

time sleep 1

clear

time sleep 1

journalctl -u mynutriapp.service -f
