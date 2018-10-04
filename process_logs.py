import sys
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


if __name__ == '__main__':
    with open(sys.argv[1], 'r') as fh:
        log = fh.read()

    soup = BeautifulSoup(log, 'html.parser')
    # Find all messages received by the BA
    ba_tags = soup.find_all('s', attrs={'r': 'BA'})
    ba_msgs = [tag_to_message(tag) for tag in ba_tags]
    for msg in ba_msgs:
        if is_sys_utterance(msg):
            print('SYS: %s' % msg.content)
        elif is_user_utterance(msg):
            print('USER: %s' % msg.content)
