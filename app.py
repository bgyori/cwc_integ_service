import time
import docker
from flask import Flask, redirect
from flask_pymongo import PyMongo


app = Flask(__name__)
app.config["MONGO_URI"] = "mongodb://localhost:27017/myDatabase"
mongo = PyMongo(app)


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


@app.route('/')
def hello():
    html = '<h1 align="center">Bob with Bioagents</h1>'
    html += """
        <form action="/launch_clic" method="get">
            <button name="clic_btn" type="submit">Launch with CLiC</button>
        </form>
        <form action="/launch_sbgn" method="get">
            <button name="sbgn_btn" type="submit">Launch with SBGN</button>
        </form>
        """
    return html


@app.route('/launch_clic')
def launch_clic():
    port = get_increment_port()
    _run_container(port, 8000)
    return redirect("http://localhost:%d/clic/bio" % port)


@app.route('/launch_sbgn')
def launch_sbgn():
    port = get_increment_port()
    _run_container(port, 3000)
    return redirect("http://localhost:%d/" % port)


def _run_container(port, expose_port):
    client = docker.from_env()
    cont = client.containers.run('cwc-integ:latest',
                                 '/sw/cwc-integ/startup.sh',
                                 detach=True,
                                 ports={('%d/tcp' % expose_port): port})
    print('Launched container %s exposing port %d via port %d' %
          (cont, expose_port, port))
    print('Now waiting before redirecting...')
    time.sleep(90)


if __name__ == '__main__':
    app.run()
