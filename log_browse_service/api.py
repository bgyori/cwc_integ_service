from os import path, listdir
import logging
from flask import Flask, render_template

from indralab_auth_tools.auth import auth, resolve_auth, config_auth

logger = logging.getLogger('cwc log browser api')

app = Flask(__name__)

HERE = path.abspath(path.dirname(__file__))
LOGS = path.join(HERE, 'templates/_logs')
GLOBAL_PRELOAD = True

# Cache of session IDs
session_list_cache = {}


def update_session_list():
    logger.info('Updating session list cache')
    before = len(session_list_cache)
    for sess_id in listdir(LOGS):
        fpath = path.join(LOGS, sess_id, 'transcript.html')
        if path.isfile(fpath) and sess_id not in session_list_cache:
            session_list_cache[sess_id] = fpath

    if len(session_list_cache) > before:
        logger.info('%d new log files added to session list cachce' %
                    (len(session_list_cache) - before))


if GLOBAL_PRELOAD:
    update_session_list()


@app.route('/browse/<sessionid>')
def browse(sessionid):
    # This route should load the log with the given sessionid
    if sessionid in session_list_cache:
        return render_template('_logs/%s/transcript.html' % sessionid)
    else:
        return '_logs/%s/transcript.html not found' % sessionid


@app.route('/')
@app.route('/browse')
def index():
    # This route should list all the session ids with the user(s?), time and
    # date. Clicking on one of them should link to the /browser/<sessionid>
    # route.
    return render_template('browse_index.html', sess_id_list=list(
        session_list_cache.keys()))
