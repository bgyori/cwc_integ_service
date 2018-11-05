import os
import sys
import textwrap
from collections import namedtuple
from kqml import *
from bs4 import BeautifulSoup

THIS_DIR = os.path.abspath(os.path.dirname(__file__))

Message = namedtuple('Message', ['type', 'receiver', 'time', 'content', 'sem'])


def tag_to_message(tag):
    msg_type = tag.name
    if msg_type == 's':
        receiver = tag.attrs['r']
    time = tag.attrs['t']
    content_str = ''.join([str(c) for c in tag.contents]).strip()
    #content_str = tag.text.strip()
    content = KQMLPerformative.from_string(content_str)

    # Add message semantics
    sem_map = {
            is_sys_utterance: 'sys_utterance',
            is_user_utterance: 'user_utterance',
            is_display_image: 'display_image',
            is_add_provenance: 'add_provenance',
            is_display_sbgn: 'display_sbgn'
            }
    sem = None
    for fun, sem_value in sem_map.items():
        if fun(content, receiver):
            sem = sem_value
            break
    msg = Message(type=msg_type, receiver=receiver, time=time, content=content,
                  sem=sem)

    return msg


def _is_type(msg, head, content_head):
    try:
        return (msg.head().upper() == head.upper() and
                msg.get('content').head().upper() == content_head.upper())
    except Exception as e:
        return False


def is_display_image(msg, receiver):
    return _is_type(msg, 'tell', 'display-image')


def is_display_sbgn(msg, receiver):
    return _is_type(msg, 'tell', 'display-sbgn')


def is_add_provenance(msg, receiver):
    return _is_type(msg, 'tell', 'add_provenance')


def is_sys_utterance(msg, receiver):
    if receiver and receiver.upper() == 'BA' and \
        _is_type(msg, 'tell', 'spoken'):
        return True
    return False


def is_user_utterance(msg, receiver):
    if not receiver or receiver.upper() != 'BA':
        return False
    sen = msg.gets('sender')
    if not sen:
        return False
    if sen.upper() == 'TEXTTAGGER' and  _is_type(msg, 'tell', 'utterance'):
        return True
    return False


def format_sys_utterance(msg):
    msg_text = msg.content.get('content').gets('what')
    html = """
    <div class="row sys_utterance">
      <div class="col-sm sys_name" 
           style="display:inline-block; color: #D0FA58">Bob</div>
      <div class="col-sm" style="display:inline-block;">&nbsp;</div>
      <div class="col-sm text-right msg_time"
           style="display:inline-block;">{time}</div>
    </div>

    <div class="row sys_utterance">
      <div class="col-sm sys_msg">{txt}</div>
    </div>
    """.format(time=msg.time, txt=msg_text)
    return textwrap.dedent(html)


def format_user_utterance(msg):
    msg_text = msg.content.get('content').gets('text')
    html = """
    <div class="row usr_utterance">
      <div class="col-sm usr_name" 
        style="display:inline-block; color: #2ECCFA">User</div>
      <div class="col-sm" style="display:inline-block;">&nbsp;</div>
      <div class="col-sm text-right msg_time" 
           style="display:inline-block;">{time}</div>
    </div>

    <div class="row usr_utterance">
      <div class="col-sm usr_msg">{txt}</div>
    </div>
    """.format(time=msg.time, txt=msg_text)
    return textwrap.dedent(html)


def make_html(html_parts):
    with open(os.path.join(THIS_DIR, 'page_template.html'), 'r') as fh:
        template = fh.read()

    html = template.replace('%%%CONTENT%%%', '\n'.join(html_parts))
    return html


def get_io_msgs(soup):
    io_msgs = []
    tags = soup.find_all('s')
    for tag in tags:
        try:
            msg = tag_to_message(tag)
        except Exception:
            continue
        if msg.sem is not None:
            io_msgs.append(msg)
    return io_msgs


def get_start_time(soup):
    # <LOG TIME="9:04 PM" DATE="7/26/18" FILE="facilitator.log">
    log = soup.find('log')
    start_time = log.attrs['date'] + ' ' + log.attrs['time']
    return start_time


def format_start_time(start_time):
    html= """
    <div class="row start_time">
      <div class="col-sm">Dialogue started at: {start_time}</div>
    </div>
    """.format(start_time=start_time)
    return textwrap.dedent(html)


def log_file_to_html_file(log_file, html_file=None):
    if html_file is None:
        html_file = log_file[:-4] + '.html'

    with open(log_file, 'r') as fh:
        log = fh.read()

    soup = BeautifulSoup(log, 'html.parser')
    html_parts = ['<div class="container">']

    start_time = get_start_time(soup)
    html_parts.append(format_start_time(start_time))

    # Find all messages received by the BA
    io_msgs = get_io_msgs(soup)
    for msg in io_msgs:
        if msg.sem == 'sys_utterance':
            print('SYS: %s' % msg.content)
            html_parts.append(format_sys_utterance(msg))
        elif msg.sem == 'user_utterance':
            print('USER: %s' % msg.content)
            html_parts.append(format_user_utterance(msg))
    html_parts.append('</div>')

    with open(html_file, 'w') as fh:
        fh.write(make_html(html_parts))


if __name__ == '__main__':
    log_file = sys.argv[1]
    log_file_to_html_file(log_file)
