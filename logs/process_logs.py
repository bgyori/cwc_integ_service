import os
import re
import sys
import textwrap

import logging

logger = logging.getLogger('log_processor')

from kqml import *

THIS_DIR = os.path.abspath(os.path.dirname(__file__))


class Message(object):
    possible_sems = ('sys_utterance', 'user_utterance', 'display_image',
                     'add_provenance', 'display_sbgn')

    def __init__(self, type, partner, time, content):
        self.type = type
        self.partner = partner
        self.time = time
        self.content = content
        self.sem = None
        for sem in self.possible_sems:
            if self.content_is(sem):
                self.sem = sem
                break
        return

    def _cont_is_type(self, head, content_head):
        try:
            return (self.content.head().upper() == head.upper() and
                    self.content.get('content').head().upper() == content_head.upper())
        except Exception as e:
            return False

    def content_is(self, msg_type):
        simple_types = ['display_image', 'display_sbgn', 'add_provenance']
        if msg_type in simple_types:
            if msg_type != 'add_provenance':
                msg_type = msg_type.replace('_', '-')
            return self._cont_is_type('tell', msg_type)
        elif msg_type == 'sys_utterance':
            return (self.partner and self.partner.upper() == 'BA' and
                    self._cont_is_type('tell', 'spoken'))
        elif msg_type == 'user_utterance':
            if not self.partner or self.partner.upper() != 'BA':
                return False
            sen = self.content.gets('sender')
            if not sen:
                return False
            if sen.upper() == 'TEXTTAGGER' \
                    and self._cont_is_type('tell', 'utterance'):
                return True
            return False
        logger.warning("Unrecognized message type: %s" % msg_type)
        return False


def format_sys_utterance(msg):
    msg_text = msg.content.get('content').gets('what')
    html = """
    <div class="row sys_utterance" style="margin-top: 15px">
      <div class="col-sm sys_name">
        <span style="background-color:#2E64FE; color: 
        #FFFFFF">Bob:</span>&nbsp;<a style="color: #BDBDBD">{time}</a>
      </div>
    </div>

    <div class="row sys_utterance" style="margin-bottom: 15px">
      <div class="col-sm sys_msg">{txt}</div>
    </div>
    """.format(time=msg.time, txt=msg_text)
    return textwrap.dedent(html)


def format_user_utterance(msg):
    msg_text = msg.content.get('content').gets('text')
    html = """
    <div class="row usr_utterance" style="margin-top: 15px">
      <div class="col-sm usr_name">
        <span style="background-color: #A5DF00; color: 
        #FFFFFF">User:</span>&nbsp;<a style="color: #BDBDBD">{time}</a>
      </div>
    </div>

    <div class="row usr_utterance" style="margin-bottom: 15px">
      <div class="col-sm usr_msg">{txt}</div>
    </div>
    """.format(time=msg.time, txt=msg_text)
    return textwrap.dedent(html)


def make_html(html_parts):
    with open(os.path.join(THIS_DIR, 'page_template.html'), 'r') as fh:
        template = fh.read()

    html = template.replace('%%%CONTENT%%%', '\n'.join(html_parts))
    return html


def get_io_msgs(log):
    io_msgs = []
    entry_list = log.sent
    for entry in entry_list:
        try:
            msg = entry.to_message()
        except Exception:
            continue
        if msg.sem is not None:
            io_msgs.append(msg)
    return io_msgs


def format_start_time(start_time):
    html= """
    <div class="row start_time">
      <div class="col-sm">Dialogue started at: {start_time}</div>
    </div>
    """.format(start_time=start_time)
    return textwrap.dedent(html)


class CwcLogEntry(object):
    """Parent class for entries in the logs."""

    def __init__(self, type, time, message, partner):
        self.type = type
        self.time = time
        self.message = message
        self.partner = partner
        self.content = None
        return

    def to_message(self):
        """Convert the entry to a message."""
        if not self.content:
            self.content = KQMLPerformative.from_string(self.message)

        # Add message semantics
        msg = Message(self.type, self.partner, self.time, self.content)
        return msg

    def __repr__(self):
        ret = '<%s ' % self.__class__.__name__
        ret += self.type + ' to ' if self.type == 'S' else ' from '
        nmax = 50
        if len(self.message) <= nmax:
            msg_str = self.message
        else:
            msg_str = self.message[:(nmax-3)] + '...'
        ret += self.partner + ": \"%s\"" % msg_str
        ret += '>'
        return ret


class CwcLog(object):
    """Object to organize the logs retrieved from cwc facilitator.log."""
    section_patt = re.compile('<(?P<type>S|R)\s+T=\"(?P<time>[\d.:]+)\"\s+'
                              '(?P<other_type>S|R)=\"(?P<sender>\w+)\">'
                              '\s+(?P<msg>.*?)\s+</(?P=type)>', re.DOTALL)
    time_patt = re.compile('<LOG TIME=\"(.*?)\"\s+DATE=\"(.*?)\".*?>')

    def __init__(self, log_file):
        with open(log_file, 'r') as f:
            self.__log = f.read()
        tp = self.time_patt.search(self.__log)
        assert tp is not None, "Failed to get time string."
        self.start_time = ' '.join(tp.groups())
        sec_list = self.section_patt.findall(self.__log)
        assert sec_list, "Failed to find any sections."
        self.sent = []
        self.received = []
        self.all = []
        for typ, dt, other_type, partner, msg in sec_list:
            entry = CwcLogEntry(typ, dt, msg, partner)
            if typ == 'S':
                self.sent.append(entry)
            else:
                self.received.append(entry)
            self.all.append(entry)
        return


def log_file_to_html_file(log_file, html_file=None):
    if html_file is None:
        html_file = log_file[:-4] + '.html'

    log = CwcLog(log_file)

    html_parts = ['<div class="container">']

    start_time = log.start_time
    html_parts.append(format_start_time(start_time))

    # Find all messages received by the BA
    io_msgs = get_io_msgs(log)
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
