int_trap() {
    echo "Ctrl-C pressed, server stopped, now cleaning up."
    python3 shutdown.py
}

trap int_trap INT

python3 -c 'import app; app.reset_sessions()'
gunicorn -w 4 -t 600 -b 0.0.0.0:8080 app:app

