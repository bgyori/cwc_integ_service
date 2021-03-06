import os
import re
import json
import logging
from shutil import copy2
from functools import wraps
from os import path, listdir
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from flask import Flask, render_template, request, url_for,\
    send_from_directory, session, redirect, Response
from log_browse_service.util import verify_password, HASH_PASS_FPATH

# Make logging print even for just .info and .warning
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('cwc log browser api')

logger.info('Testing info logging')
logger.warning('Testing warning logging')
logger.error('Testing error logging')

HERE = path.abspath(path.dirname(__file__))
DEFAULT_STATIC = path.join(HERE, 'static')
DEFAULT_TEMPLATES = path.join(HERE, 'templates')
LOGS_DIR_NAME = os.environ.get('CWC_LOG_DIR', '')
if not LOGS_DIR_NAME:
    logger.info('Environment variable "CWC_LOG_DIR" not set, using default: '
                '%s' % HERE)
    LOGS_DIR_NAME = HERE
STATIC_DIR = path.join(LOGS_DIR_NAME, 'static')
TEMPLATS_DIR = path.join(LOGS_DIR_NAME, 'templates')
if not path.isfile(path.join(TEMPLATS_DIR, 'browse_index.html')):
    src = path.join(DEFAULT_TEMPLATES, 'browse_index.html')
    dst = path.join(TEMPLATS_DIR, 'browse_index.html')
    copy2(src=src, dst=dst)
if not path.isfile(path.join(TEMPLATS_DIR, 'login.html')):
    src = path.join(DEFAULT_TEMPLATES, 'login.html')
    dst = path.join(TEMPLATS_DIR, 'login.html')
    copy2(src=src, dst=dst)

app = Flask(__name__, static_folder=STATIC_DIR,
            template_folder=TEMPLATS_DIR)
app.config['DEBUG'] = 1
app.config['SECRET_KEY'] = os.environ.get('LOG_BROWSER_SESSION_KEY', '')
if not app.config.get('SECRET_KEY'):
    raise ValueError('Need to set a session key in os environment using '
                     'the variable LOG_BROWSER_SESSION_KEY')
# The actual stored value of the hashed password
if not path.isfile(HASH_PASS_FPATH):
    raise ValueError('Need to save password hash to %s' % HASH_PASS_FPATH)

LOGS = TEMPLATS_DIR
if not path.isdir(LOGS):
    raise ValueError('%s is not a directory. Must either set "CWC_LOG_DIR" '
                     'in os environment or have the default log directory '
                     '"logs" available in the templates directory.' %
                     TEMPLATS_DIR)
TRANSCRIPT_JSON_PATH = path.join(LOGS, 'transcripts.json')
ARCHIVES = path.join(LOGS_DIR_NAME, '_archive')
GLOBAL_PRELOAD = True
time_patt = re.compile('<LOG TIME=\"(.*?)\"\s+DATE=\"(.*?)\".*?>')
user_patt = re.compile('User is (.*?) \((.*?)\)\.')
sortable_date_format = '%Y-%m-%d-%H-%M-%S'
log_date_format = '%I:%M %p %m/%d/%y'
session_id_list = []
current_log_dir_count = 0


def update_session_id_list():
    global session_id_list, current_log_dir_count
    if len(listdir(LOGS)) > current_log_dir_count:
        new_dir_count = len(listdir(LOGS))
        # Get session id and datetime (and user name in future)
        session_id_list_cache = []
        logger.info('Updating session list cache')
        for sess_id in listdir(LOGS):
            if path.isfile(sess_id):
                continue
            html_path = path.join(LOGS, sess_id, 'transcript.html')
            raw_txt_path = path.join(LOGS, sess_id, 'log.txt')
            if path.isfile(html_path) and path.isfile(raw_txt_path):
                with open(raw_txt_path, 'r') as f:
                    dt_str = f.readline()
                m = time_patt.search(dt_str)
                file_dt = 'unknown start time' if m is None else\
                    datetime.strptime(' '.join(m.groups()),
                                      log_date_format).strftime(
                        sortable_date_format)

                with open(html_path, 'r') as htmlf:
                    html_str = htmlf.read()
                    soup = BeautifulSoup(html_str, 'html.parser')
                    user_str = soup.find('div', class_='start_time')
                    if user_str is not None and user_str.div is not None:
                        mm = user_patt.search(
                            user_str.div.text.replace('\n', '').strip())
                user = 'anonymous' if mm is None or\
                    mm is not None and not mm.groups()[0].strip() else \
                    mm.groups()[0].strip()
                if (sess_id, file_dt, user) not in session_id_list_cache:
                    session_id_list_cache.append((sess_id, file_dt, user))
            elif sess_id not in ['transcripts.json', 'login.html',
                                 'log_view.html', 'browse_index.html']:
                logger.warning('session %s does not have any html formatted '
                               'log transcript.' % sess_id)
        session_id_list_cache.sort(key=lambda t: t[1], reverse=True)
        if len(session_id_list) < len(session_id_list_cache):
            logger.info('%d new logs found!' %
                        (len(session_id_list_cache)-len(session_id_list)))
            session_id_list = session_id_list_cache
        current_log_dir_count = new_dir_count
        logger.info('Finished updating session list cache')
    else:
        logger.info('No new session to add to the list')


def page_wrapper(f):
    logger.info('Calling outer wrapper')

    @wraps(f)
    def decorator(*args, **kwargs):
        # Check if logged in in session:
        #   if not: redirect to /login
        #   if logged in: continue to page

        # Not logged in
        if not session.get('logged_in', False):
            if 'iframe' in request.path:
                logger.info('Unauthorized iframe request, letting user know '
                            'they need to log in')
                return 'Must log in to continue browsing log pages'
            logger.info('User is not logged in, redirecting to login')
            return redirect(url_for('login'))

        # Logged in: proceed
        logger.info('User is logged in, proceeding')
        return f(*args, **kwargs)
    return decorator


@app.before_first_request
def session_set_up():
    update_session_id_list()


# Deletes session after the specified time
@app.before_request
def session_expiration_check():
    session.permanent = True
    session.modified = True
    app.permanent_session_lifetime = timedelta(minutes=90)


@app.route('/browse')
@page_wrapper
def browse():
    # This route should render "index_template" showing the first log
    # (default) or the log associated with the provided session id
    global session_id_list
    update_session_id_list()
    tjson = [t[0] for t in session_id_list]
    sess_id = request.args.get('sess_id') if request.args.get('sess_id')\
        else tjson[0]
    try:
        page = tjson.index(sess_id) if sess_id else 0
        msg = ''
    except ValueError:
        # session id was not in list
        page = 0
        msg = 'Session id %s was not found' % sess_id

    session['last_page'] = '/browse?=%s' % page
    return render_template('log_view.html',
                           transcript_json=tjson,
                           page=page,
                           sess_id=sess_id,
                           base_url=url_for('browse'),
                           msg=msg)


@app.route('/iframe_page/<sess_id>')
@page_wrapper
def iframe_page(sess_id):
    logger.info('Rendering iframe html')
    return render_template('%s/transcript.html' % sess_id)


@app.route('/files/<sess_id>')
@page_wrapper
def download_file(sess_id):
    logger.info('File download request received')
    archive_fname = sess_id + '_archive.tar.gz'
    return send_from_directory(directory=ARCHIVES,
                               filename=archive_fname,
                               as_attachment=True)


@app.route('/')
@app.route('/index')
@page_wrapper
def index():
    # This route should list all the session ids with the user (if
    # available), time and date. Clicking on one of them should link to
    # the index page and set curr_idx to the corresponding page
    global session_id_list
    update_session_id_list()
    session['last_page'] = '/index'
    return render_template('browse_index.html', sess_id_list=session_id_list)


@app.route('/login')
def login():
    # This should be the route were user's are redirected if they're not
    # logged in. login.html should be a template that gathers
    return render_template('login.html')


@app.route('/login/submit', methods=['POST'])
def check_login():
    query = request.json.copy()
    logger.info('Got query from user %s with json containing the keys: %s' %
                (query.get('username'), ', '.join(query.keys())))
    # Compare submitted (username and) hashed password with stored
    # hash(password)
    session['username'] = query.get('username')
    pwd = query.get('password')
    with open(HASH_PASS_FPATH, 'rb') as bf:
        logger.info('Getting cached hashed password')
        hp = bf.read()

    if verify_password(hashed_password=hp,
                       guessed_password=pwd,
                       # Seems to need very high maxtime when running locally
                       maxtime=6.0):
        logger.info('Password correct, redirecting to last page')
        session['logged_in'] = True
        response_json = {'authorized': True,
                         'redirect': session.get('last_page', '/index')}
        code = 200
    else:
        logger.info('Password incorrect, redirecting back to login')
        response_json = {'authorized': False,
                         'redirect': '/login'}
        code = 401
    return Response(json.dumps(response_json), status=code,
                    mimetype='application/json')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port='8888')
