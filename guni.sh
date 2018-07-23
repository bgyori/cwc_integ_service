python -c 'import app; app.reset_sessions()'
gunicorn -w 4 -t 600 -b 0.0.0.0:8080 app:app
