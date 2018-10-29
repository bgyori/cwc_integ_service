import sys
import textwrap
from collections import namedtuple
from kqml import *
from bs4 import BeautifulSoup


Message = namedtuple('Message', ['type', 'receiver', 'time', 'content'])


def tag_to_message(tag):
    msg_type = tag.name
    if msg_type == 's':
        receiver = tag.attrs['r']
    time = tag.attrs['t']
    content_str = tag.text.strip()
    content = KQMLPerformative.from_string(content_str)
    msg = Message(type=msg_type, receiver=receiver, time=time, content=content)
    return msg


def is_sys_utterance(msg):
    try:
        return (msg.content.head().upper() == 'TELL' and
                msg.content.get('content').head().upper() == 'SPOKEN')
    except Exception as e:
        return False


def is_user_utterance(msg):
    try:
        content = msg.content.get('content')
        return (msg.content.head().upper() == 'TELL' and
                content.head().upper() == 'UTTERANCE' and
                msg.content.gets('sender').upper() == 'TEXTTAGGER')
    except Exception as e:
        return False


def format_sys_utterance(msg):
    msg_text = msg.content.get('content').gets('what')
    html = """
    <div class="row sys_utterance">
      <div class="col-sm sys_name">Bob</div>
      <div class="col-sm">&nbsp;</div>
      <div class="col-sm text-right msg_time">{time}</div>
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
      <div class="col-sm usr_name">User</div>
      <div class="col-sm">&nbsp;</div>
      <div class="col-sm text-right msg_time">{time}</div>
    </div>

    <div class="row usr_utterance">
      <div class="col-sm usr_msg">{txt}</div>
    </div>
    """.format(time=msg.time, txt=msg_text)
    return textwrap.dedent(html)


def make_html(html_parts):
    with open('page_template.html', 'r') as fh:
        template = fh.read()

    html = template.replace('%%%CONTENT%%%', '\n'.join(html_parts))
    return html


def get_ba_msgs(soup):
    ba_tags = soup.find_all('s', attrs={'r': 'BA'})
    ba_msgs = [tag_to_message(tag) for tag in ba_tags]
    return ba_msgs


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


if __name__ == '__main__':
    with open(sys.argv[1], 'r') as fh:
        log = fh.read()

    soup = BeautifulSoup(log, 'html.parser')
    html_parts = ['<div class="container">']

    start_time = get_start_time(soup)
    html_parts.append(format_start_time(start_time))

    # Find all messages received by the BA
    ba_msgs = get_ba_msgs(soup)
    for msg in ba_msgs:
        if is_sys_utterance(msg):
            print('SYS: %s' % msg.content)
            html_parts.append(format_sys_utterance(msg))
        elif is_user_utterance(msg):
            print('USER: %s' % msg.content)
            html_parts.append(format_user_utterance(msg))
    html_parts.append('</div>')
    with open('test.html', 'w') as fh:
        fh.write(make_html(html_parts))
