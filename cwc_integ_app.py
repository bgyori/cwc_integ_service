import re
import time
import json
import docker
from os import path, environ
from datetime import datetime
from flask import Flask, render_template, request
from flask_wtf import Form
from flask_pymongo import PyMongo
from flask_bootstrap import Bootstrap
from wtforms import SubmitField, StringField, validators
from wtforms.fields.html5 import EmailField

from logs.get_logs import get_logs_for_container

import logging

LOGGING_FMT = ('[%(asctime)s] %(levelname)s '
               '- %(funcName)s@%(lineno)s: %(message)s')

logger = logging.getLogger('cwc-web-service')
guni_logger = logging.getLogger('gunicorn.error')
logger.handlers.extend(guni_logger.handlers)
logging.basicConfig(level=logging.INFO, format=LOGGING_FMT)
logger.info("Logging is working!")

MAX_SESSIONS = 8
class SessionLimitExceeded(Exception):
    pass


app = Flask(__name__)
app.config["MONGO_URI"] = 'mongodb://localhost:27017/myDatabase'
app.config['SECRET_KEY'] = 'dev_key'
mongo = PyMongo(app)
Bootstrap(app)
MY_CONTAINER_LIST = 'cwc_service_containers.json'
TIME_FMT = '%Y%m%d%H%M%S'
DAY = 86400  # a day in seconds.
HOUR = 3600  # an hour in seconds.
HERE = path.abspath(path.dirname(__file__))
LOGS_LOCAL_DIR = environ.get('CWC_LOG_DIR', HERE)
if LOGS_LOCAL_DIR == HERE:
    logger.info('Environment variable "CWC_LOG_DIR" not set, using '
                'default: %s' % HERE)


def _load_id_dict():
    if not path.exists(MY_CONTAINER_LIST):
        return {}
    id_dict = {}
    with open(MY_CONTAINER_LIST, 'r') as f:
        id_dict_strs = json.load(f)
    for id_val, data in id_dict_strs.items():
        for key, val in data.items():
            if key == 'date':
                data[key] = datetime.strptime(val, TIME_FMT)
        id_dict[id_val] = data
    return id_dict


def _dump_id_dict(id_dict):
    json_dict = {}
    for id_val, data in id_dict.items():
        json_data = data.copy()
        for key, val in data.items():
            if key == 'date':
                json_data[key] = val.strftime(TIME_FMT)
        json_dict[id_val] = json_data
    with open(MY_CONTAINER_LIST, 'w') as f:
        json.dump(json_dict, f)
    return


def _add_my_container(cont_id, interface):
    """Update the json with a new container."""
    id_dict = _load_id_dict()

    if cont_id not in id_dict.keys():
        logger.info("Adding %s to list of my containers." % cont_id)
        id_dict[cont_id] = {'interface': interface, 'date': datetime.utcnow()}
        _dump_id_dict(id_dict)
        success = True
    else:
        logger.info("This container was already registered.")
        success = False

    return success


def _pop_my_container(cont_id, pop=True):
    """Update the json with the removal of a container."""
    id_dict = _load_id_dict()

    if cont_id not in id_dict.keys():
        logger.info("This container isn't mine or doesn't exist.")
        ret = None
    else:
        if pop:
            ret = id_dict.pop(cont_id)
        else:
            ret = id_dict.get(cont_id)
        logger.info("Removing %s from list of my containers which had "
                    "metadata: %s." % (cont_id, ret))
        _dump_id_dict(id_dict)

    return ret


def _check_timers():
    """Look through the containers and stop any timed-out containers."""
    # The logs are utc time, and this generally avoids any time-zone issues.
    # Won't work in python 2.
    now = datetime.utcnow()

    # This is not connected to the other dict instances deliberately. Do not
    # try to make the dict shared, because the below for-loop could then have
    # issues modifying an object while iterating over it.
    id_dict = _load_id_dict()
    logger.info("There are %d instances running." % len(id_dict))

    # Go through all the containers...
    client = docker.from_env()
    for cont_id, data in id_dict.items():
        start_date = data['date']
        logger.info("Examining %s" % cont_id)

        # Grab the date from the latest SPG log entry.
        cont = client.containers.get(cont_id)
        cont_logs = cont.logs()
        date_strings = re.findall('SPG:\s+;;\s+\[(.*?)\]',
                                  cont_logs.decode('utf-8'))
        if date_strings:
            latest_log_date = datetime.strptime(date_strings[-1],
                                                '%m/%d/%Y %H:%M:%S')
        else:
            logger.info("WARNING: Did not find any date strings in container "
                        "logs for %s." % cont_id)
            latest_log_date = start_date

        # Check both whether the logs have been silent for more than a day
        # (neglect) or whether the session has been running for more than 5
        # days (hogging).
        log_stalled = (now - latest_log_date).seconds
        total_dur = (now - start_date).seconds
        if log_stalled > 2*HOUR:
            logger.info("Container %s timed out after %ds of empty logs."
                        % (cont_id, log_stalled))
            _stop_container(cont_id)
        elif total_dur > DAY/2:
            logger.info("Container %s timed out after %d seconds of running."
                  % (cont_id, total_dur))
            _stop_container(cont_id)
    return


def get_increment_port():
    port_json = mongo.db.ports.find_one()
    if port_json is None:
        port = 8000
        mongo.db.ports.insert_one({'port': port})
    else:
        port = port_json['port']
        mongo.db.ports.update_one({'port': port}, {'$set': {'port': port + 1}})
        port += 1
    return port


def get_num_sessions():
    sessions_json = mongo.db.sessions.find_one()
    if not sessions_json:
        return 0
    num_sessions = sessions_json['num_sessions']
    return num_sessions


def increment_sessions():
    sessions_json = mongo.db.sessions.find_one()
    if sessions_json is None:
        reset_sessions()
    num_sessions = sessions_json['num_sessions']
    if num_sessions == MAX_SESSIONS:
        raise SessionLimitExceeded()
    mongo.db.sessions.update_one({'num_sessions': num_sessions},
                                 {'$set': {'num_sessions': num_sessions + 1}})
    return num_sessions + 1


def decrement_sessions():
    sessions_json = mongo.db.sessions.find_one()
    if sessions_json is None:
        reset_sessions()
    num_sessions = sessions_json['num_sessions']
    mongo.db.sessions.update_one({'num_sessions': num_sessions},
                                 {'$set': {'num_sessions': num_sessions - 1}})
    return num_sessions - 1


def add_token(token):
    mongo.db.tokens.insert_one({'token': token})


def has_token(token):
    tokens = mongo.db.tokens.find()
    if tokens is None:
        return False
    for tok in tokens:
        if tok['token'] == token:
            return True
    return False


def user_session_association(user, email, cont_id, cont_name, app_name,
                             extension, port, interface_port_number):
    mongo.db.session_users.insert_one({'user': user,
                                       'email': email,
                                       'container_id': cont_id,
                                       'container_name': cont_name,
                                       'app_name': app_name,
                                       'extension': extension,
                                       'port': port,
                                       'interface_port':
                                           interface_port_number})


def _launch_app(interface_port_num, app_name, extension=''):
    user = request.form.get('user_name', '')
    email = request.form.get('user_email', '')
    if user or email:
        logger.info('User %s with email %s launched app' %
                    (user if user else '(username not provided)',
                     email if email else '(no email)'))
    num_sessions = get_num_sessions()
    if num_sessions >= MAX_SESSIONS:
        logger.info('Number of sessions: %d' % num_sessions)
        # TODO: this should be part of the index page with buttons
        # greyed out
        return 'There are currently too many sessions, please come back later.'
    # Here we check if the same token was already used to start a session
    token = request.form['csrf_token']
    if has_token(token):
        # Flash could be nice but it gets placed on the home page instead of
        # the page with the dialogue for some reason
        # flash('You already have a session!')
        return ('', 204)
        #return 'You already have a running session, please stop it ' + \
        #    'and refresh the main page again to start another one.'
    # We add the token to make sure it can't be reused
    add_token(token)
    port = get_increment_port()
    base_host = 'http://' + str(request.host).split(':')[0]
    host = base_host + (':%d' % port + extension)
    logger.info('Will redirect to address: %s' % host)
    cont_id, cont_name = _run_container(port, interface_port_num, app_name)
    if user or email:
        logger.info('Adding user info for user %s' % user)
        user_session_association(user, email, cont_id, cont_name, app_name,
                                 extension, port, interface_port_num)
    logger.info('Start redirecting %s interface.' % app_name)
    return render_template('launch_dialogue.html', dialogue_url=host,
                           manager_url=base_host, container_id=cont_id,
                           time_out=60, container_name=cont_name,
                           interface=app_name)


class ClicForm(Form):
    # validators documentation:
    # https://wtforms.readthedocs.io/en/stable/validators.html
    user_name = StringField('Name', validators=[validators.unicode_literals,
                                                validators.input_required])
    user_email = EmailField('Email', validators=[validators.Email()])
    submit_button = SubmitField('Launch with CLiC')


class SbgnForm(Form):
    user_name = StringField('Name', validators=[validators.unicode_literals,
                                                validators.input_required])
    user_email = EmailField('Email', validators=[validators.Email()])
    submit_button = SubmitField('Launch with SBGN')


@app.route('/')
def hello():
    clic_form = ClicForm()
    sbgn_form = SbgnForm()
    kwargs = {'clic_form': clic_form, 'sbgn_form': sbgn_form}
    return render_template('index.html', **kwargs)


@app.route('/launch_clic', methods=['POST'])
def launch_clic():
    return _launch_app(8000, 'CLIC', '/clic/bio')


@app.route('/launch_sbgn', methods=['POST'])
def launch_sbgn():
    return _launch_app(3000, 'SBGN')


@app.route('/end_session/<cont_id>', methods=['DELETE'])
def stop_session(cont_id):
    logger.info("Request to end %s." % cont_id)
    assert cont_id, "Bad request. Need an id."
    _stop_container(cont_id)
    return 'Success!', 200


def _stop_container(cont_id, remove_record=True):
    record = _pop_my_container(cont_id, pop=remove_record)
    if remove_record:
        assert record is not None, \
            "Could not remove container because it is not my own."
    client = docker.from_env()
    cont = client.containers.get(cont_id)
    logger.info("Got container %s, aka %s." % (cont.id, cont.name))
    get_logs_for_container(cont, record['interface'], LOGS_LOCAL_DIR)
    cont.stop()
    cont.remove()
    logger.info("Container removed.")
    decrement_sessions()
    return


def _run_container(port, expose_port, app_name):
    num_sessions = increment_sessions()
    logger.info('We now have %d active sessions' % num_sessions)
    client = docker.from_env()
    cont = client.containers.run('cwc-integ:dev',
                                 '/sw/cwc-integ/startup.sh',
                                 detach=True,
                                 ports={('%d/tcp' % expose_port): port})
    logger.info('Launched container %s exposing port %d via port %d'
                % (cont, expose_port, port))
    _add_my_container(cont.id, app_name)
    return cont.id, cont.name


def reset_sessions():
    """Reset all the db sessions."""
    logger.info('Resetting sessions')
    sessions_json = mongo.db.sessions.find_one()
    if sessions_json is None:
        mongo.db.sessions.insert_one({'num_sessions': 0})
    else:
        mongo.db.sessions.update_one({}, {'$set': {'num_sessions': 0}})


def cleanup():
    """Stop all the currently running containers and remove."""
    logger.info("Starting cleanup.")
    print("+" + "-"*78 + "+")
    print("| %-76s |" % "Grabbing logs, stopping, and removing all docker containers...")
    print("| %-76s |" % "Please wait, as this may take a while.")
    print("+" + "-"*78 + "+")
    id_dict = _load_id_dict()
    num_conts = len(id_dict)
    for i, (cont_id, start_date) in enumerate(id_dict.items()):
        try:
            print("(%d/%d) Resolving %s...." % (i+1, num_conts, cont_id))
            _stop_container(cont_id)
        except Exception as e:
            logger.error("Faild to shut down the container: %s!" % (cont_id))
            logger.error("Reasion:")
            logger.exception(e)
            logger.info("Continuing...")
    print("+" + "-"*78 + "+")
    print("| %-76s |" % "All done! Have a nice day! :)")
    print("+" + "-"*78 + "+")


def monitor():
    """Check session timers and clean up old session periodically."""
    logger.info("Monitor starting.")
    try:
        while True:
            time.sleep(60*15)  # every 15 minutes
            logger.info("Checking session in monitor...")
            _check_timers()
            logger.info("Check complete. Waiting...")
    except BaseException as e:
        logger.info("Monitor is closing with:")
        logger.exception(e)
    return


if __name__ == '__main__':
    from sys import argv
    if argv[1] == 'cleanup':
        logging.basicConfig(level=logging.INFO, format=LOGGING_FMT)
        cleanup()
    elif argv[1] == 'monitor':
        logging.basicConfig(level=logging.INFO, format=LOGGING_FMT)
        monitor()
    elif argv[1] == 'reset':
        logging.basicConfig(level=logging.INFO, format=LOGGING_FMT)
        reset_sessions()
    else:
        app.run(host='0.0.0.0')
