#!/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v python3 &>/dev/null; then
  echo "Python3 non trouvé"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Création de l'environnement virtuel…"
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installation des dépendances…"
pip install -q -r requirements.txt

echo ""
echo "Démarrage de l'application…"
echo "Ouvre http://localhost:8001 dans ton navigateur"
echo ""
python app.py
