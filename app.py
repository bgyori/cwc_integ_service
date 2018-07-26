import time
import docker
from flask import Flask, redirect, render_template, url_for, request
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


class ClicForm(Form):
    submit_button = SubmitField('Launch with CLiC')


class SbgnForm(Form):
    submit_button = SubmitField('Launch with SBGN')


@app.route('/')
def hello():
    num_sessions = get_num_sessions()
    if num_sessions < MAX_SESSIONS:
        clic_form = ClicForm()
        sbgn_form = SbgnForm()
        kwargs = {'clic_form': clic_form, 'sbgn_form': sbgn_form}
        return render_template('index.html', **kwargs)
    else:
        print('Number of sessions: %d' % num_sessions)
        # TODO: this should be part of the index page with buttons
        # greyed out
        return 'There are currently too many sessions, please come back later.'


@app.route('/launch_clic')
def launch_clic():
    port = get_increment_port()
    host = 'http://' + str(request.host).split(':')[0] + (':%d/clic/bio' % port)
    print('Will redirect to address: %s' % host)
    cont_id = _run_container(port, 8000)
    print('Start redirecting CLIC interface.')
    return render_template('launch_dialogue.html', dialogue_url=host,
                           manager_url=request.host, container_id=cont_id,
                           time_out=90)


@app.route('/launch_sbgn')
def launch_sbgn():
    port = get_increment_port()
    host = str(request.host).split(':')[0] + (':%d' % port)
    print('Will redirect to address: %s' % host)
    cont_id = _run_container(port, 3000)
    print('Start redirecting SBGN interface.')
    return render_template('launch_dialogue.html', dialogue_url=host,
                           manager_url=request.host, container_id=cont_id,
                           time_out=90)


@app.route('/end_session')
def stop_session():
    query_dict = request.args.copy()
    cont_id = query_dict.get('id')
    assert cont_id, "Bad request. Need an id."
    client = docker.from_env()
    cont = client.containers.get(cont_id)
    cont.stop()
    get_logs_for_container(cont)
    cont.remove()
    pass


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
