import re
import logging
from os import path, listdir
from datetime import datetime
from flask import Flask, render_template, request, url_for

logger = logging.getLogger('cwc log browser api')

app = Flask(__name__)

HERE = path.abspath(path.dirname(__file__))
LOGS_DIR_NAME = 'logs_20191216'
LOGS = path.join(HERE, 'templates', LOGS_DIR_NAME)
TRANSCRIPT_JSON_PATH = path.join(LOGS, 'transcripts.json')
GLOBAL_PRELOAD = True
time_patt = re.compile('<LOG TIME=\"(.*?)\"\s+DATE=\"(.*?)\".*?>')
sortable_date_format = '%Y-%m-%d-%H-%M-%S'
log_date_format = '%I:%M %p %m/%d/%y'

# Cache of session IDs
session_list_cache = []


def update_session_list():
    # Get session id and datetime (and user name in future)
    logger.info('Updating session list cache')
    before = len(session_list_cache)
    for sess_id in listdir(LOGS):
        if path.isfile(sess_id):
            continue
        html_path = path.join(LOGS, sess_id, 'transcript.html')
        raw_txt_path = path.join(LOGS, sess_id, 'log.txt')
        if path.isfile(html_path) and path.isfile(raw_txt_path):
            with open(raw_txt_path, 'r') as f:
                dt_str = f.readline()
            m = time_patt.search(dt_str)

            # ToDo find user info for future implementation
            # user = user_patt.search()
            user = ''
            file_dt = 'unknown start time' if m is None else\
                datetime.strptime(' '.join(m.groups()),
                                  log_date_format).strftime(
                    sortable_date_format)
            if (sess_id, file_dt, user) not in session_list_cache:
                session_list_cache.append((sess_id, file_dt, user))
        else:
            logger.warning('session %s does not have any html formatted '
                           'log transcript.' % sess_id)
    session_list_cache.sort(key=lambda t: t[1])

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
