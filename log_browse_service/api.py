import re
import logging
import os
from os import path, listdir
from datetime import datetime
from flask import Flask, render_template, request, url_for

logger = logging.getLogger('cwc log browser api')

app = Flask(__name__)


HERE = path.abspath(path.dirname(__file__))
LOGS_DIR_NAME = os.environ.get('CWC_LOG_DIR', 'logs')
LOGS = path.join(HERE, 'templates', LOGS_DIR_NAME)
if not path.isdir(LOGS):
    raise ValueError('%s is not a directory. Must either set "CWC_LOG_DIR" in '
                     'os environment or have the default log directory'
                     '"logs" available in the templates directory.' %
                     path.join('templates', LOGS_DIR_NAME))
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


@app.route('/browse')
def browse():
    # This route should render "index_template" showing the first log
    # (default) or the provided page number (zero-indexed)
    page = request.args.get('page', 0)
    return render_template('/%s/log_view.html' % LOGS_DIR_NAME,
                           transcript_json=[t[0] for t in session_list_cache],
                           page=page,
                           base_url=url_for('browse'))


@app.route('/iframe_page/<sess_id>')
def iframe_page(sess_id):
    return render_template('/%s/%s/transcript.html' %
                           (LOGS_DIR_NAME, sess_id))


@app.route('/')
@app.route('/index')
def index():
    # This route should list all the session ids with the user(s?), time
    # and date. Clicking on one of them should link to the index page and
    # set curr_idx to the corresponding
    update_session_list()
    return render_template('browse_index.html',
                           sess_id_list=session_list_cache)
