#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Installer Python 3.10 ou plus récent pour lancer cette application'
    read -r answer
    exit 1
fi
python3 -B ./python/server.py "$@"
status=$?
if [ "$status" -ne 0 ]; then
    printf '%s\n' 'Le lancement a échoué. Le message ci-dessus indique la cause'
    read -r answer
fi
exit "$status"
