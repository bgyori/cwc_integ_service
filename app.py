import time
import docker
from flask import Flask, redirect, render_template, url_for, request, flash
from flask_wtf import Form
from flask_pymongo import PyMongo
from flask_bootstrap import Bootstrap
from wtforms import SubmitField

from get_logs import get_logs_for_container


MAX_SESSIONS = 8
class SessionLimitExceeded(Exception):
    pass


app = Flask(__name__)
app.config["MONGO_URI"] = 'mongodb://localhost:27017/myDatabase'
app.config['SECRET_KEY'] = 'dev_key'
mongo = PyMongo(app)
Bootstrap(app)


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

def reset_sessions():
    print('Resetting sessions')
    sessions_json = mongo.db.sessions.find_one()
    if sessions_json is None:
        mongo.db.sessions.insert_one({'num_sessions': 0})
    else:
        mongo.db.sessions.update_one({}, {'$set': {'num_sessions': 0}})


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


def _launch_app(interface_port_num, app_name, extension=''):
    num_sessions = get_num_sessions()
    if num_sessions >= MAX_SESSIONS:
        print('Number of sessions: %d' % num_sessions)
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
    print('Will redirect to address: %s' % host)
    cont_id = _run_container(port, interface_port_num)
    print('Start redirecting %s interface.' % app_name)
    return render_template('launch_dialogue.html', dialogue_url=host,
                           manager_url=base_host, container_id=cont_id,
                           time_out=90)


class ClicForm(Form):
    submit_button = SubmitField('Launch with CLiC')


class SbgnForm(Form):
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
    print("Request to end %s." % cont_id)
    assert cont_id, "Bad request. Need an id."
    client = docker.from_env()
    cont = client.containers.get(cont_id)
    print("Got client %s, aka %s." % (cont.id, cont.name))
    get_logs_for_container(cont)
    cont.stop()
    cont.remove()
    print("Container removed.")
    decrement_sessions()
    return 'Success!', 200 


def _run_container(port, expose_port):
    num_sessions = increment_sessions()
    print('We now have %d active sessions' % num_sessions)
    client = docker.from_env()
    cont = client.containers.run('cwc-integ:latest',
                                 '/sw/cwc-integ/startup.sh',
                                 detach=True,
                                 ports={('%d/tcp' % expose_port): port})
    print('Launched container %s exposing port %d via port %d' %
          (cont, expose_port, port))
    return cont.id


if __name__ == '__main__':
    app.run(host='0.0.0.0')
