import os
import re
import sys
import textwrap

import logging

logger = logging.getLogger('log_processor')

from kqml import *

THIS_DIR = os.path.abspath(os.path.dirname(__file__))



def make_html(html_parts):
    with open(os.path.join(THIS_DIR, 'page_template.html'), 'r') as fh:
        template = fh.read()

    html = template.replace('%%%CONTENT%%%', '\n'.join(html_parts))
    return html


def format_start_time(start_time):
    html = """
    <div class="row start_time">
      <div class="col-sm">Dialogue started at: {start_time}</div>
    </div>
    """.format(start_time=start_time)
    return textwrap.dedent(html)


class CwcLogEntry(object):
    """Parent class for entries in the logs."""
    possible_sems = ('sys_utterance', 'user_utterance', 'display_image',
                     'add_provenance', 'display_sbgn')

    def __init__(self, type, time, message, partner):
        self.type = type
        self.time = time
        self.message = message
        self.partner = partner
        self.content = None
        self.sem = None
        return

    def get_content(self):
        """Convert the entry to a message."""
        if not self.content:
            self.content = KQMLPerformative.from_string(self.message)
        return self.content

    def get_sem(self):
        """Get the sem (semantic) of this entry."""
        if not self.sem:
            for sem in self.possible_sems:
                if self._content_is(sem):
                    self.sem = sem
                    break
        return self.sem

    def is_sem(self, sem):
        """Check whether this entry matches the given sem."""
        if sem not in self.possible_sems:
            raise ValueError("Invalid sem: %s" % sem)
        return self.get_sem() == sem

    def make_html(self):
        if self.is_sem('sys_utterance'):
            print('SYS:', str(self.content))
            inp = self.content.get('content').gets('what')
            fmt = """
            <div class="row sys_utterance" style="margin-top: 15px">
              <div class="col-sm sys_name">
                <span style="background-color:#2E64FE; color: 
                #FFFFFF">Bob:</span>&nbsp;<a style="color: #BDBDBD">{time}</a>
              </div>
            </div>

            <div class="row sys_utterance" style="margin-bottom: 15px">
              <div class="col-sm sys_msg">{inp}</div>
            </div>
            """
        elif self.is_sem('user_utterance'):
            print('USR:', str(self.content))
            inp = self.content.get('content').gets('text')
            fmt = """
            <div class="row usr_utterance" style="margin-top: 15px">
              <div class="col-sm usr_name">
                <span style="background-color: #A5DF00; color: 
                #FFFFFF">User:</span>&nbsp;<a style="color: #BDBDBD">{time}</a>
              </div>
            </div>

            <div class="row usr_utterance" style="margin-bottom: 15px">
              <div class="col-sm usr_msg">{inp}</div>
            </div>
            """
        elif self.is_sem('add_provenance'):
            print("SYS sent provenance.")
            inp = self.content.get('content').gets('html')
            fmt = """
            <div class="row add_provenance" style="margin-top: 15px">
                <div class="col-sm sys_name">
                    <span style="background-color: #2E64FE; color: 
                    #FFFFFF">Bob (provenance):</span>&nbsp;<a style="color:
                    #BDBDBD">{time}</a>
                </div>
            </div>

            {inp}
            """
        else:
            return None
        return textwrap.dedent(fmt.format(time=self.time, inp=inp))

    def _cont_is_type(self, head, content_head):
        try:
            my_head = self.content.head()
            my_content_head = self.content.get('content').head()
            return (my_head.upper() == head.upper() and
                    my_content_head.upper() == content_head.upper())
        except Exception as e:
            return False

    def _content_is(self, msg_type):
        simple_types = ['display_image', 'display_sbgn', 'add_provenance']
        if msg_type in simple_types:
            msg_type = msg_type.replace('_', '-')
            ret = self._cont_is_type('tell', msg_type)
            return ret
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

    def __repr__(self):
        ret = '<%s ' % self.__class__.__name__
        ret += self.type
        ret += ' to ' if self.type == 'S' else ' from '
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

    def __init__(self, log_dir):
        self.log_dir = log_dir

        # Load and parse the log file.
        self.log_file = os.path.join(log_dir, 'log.txt')
        with open(self.log_file, 'r') as f:
            self.__log = f.read()
        self.start_time = None
        self.all_entries = None

        # Get familiar with the image stash, if present.
        self.img_dir = os.path.join(log_dir, 'images')
        if not os.path.exists(self.img_dir):
            # If the logs are old and there's no image directory, we'll just
            # have to live without images.
            logger.warning("No image directory \"%s\" found. This transcript "
                           "will have no images included." % self.img_dir)
            self.img_dir = None

        # This is filled later.
        self.io_entries = None
        return

    def get_start_time(self):
        if self.start_time is None:
            tp = self.time_patt.search(self.__log)
            assert tp is not None, "Failed to get time string."
            self.start_time = ' '.join(tp.groups())
        return self.start_time

    def get_all_entries(self):
        if self.all_entries is None:
            self.all_entries = []
            sec_list = self.section_patt.findall(self.__log)
            assert sec_list, "Failed to find any sections."
            for typ, dt, other_type, partner, msg in sec_list:
                entry = CwcLogEntry(typ, dt, msg, partner)
                self.all_entries.append(entry)
        return self.all_entries

    def get_io_entries(self):
        if not self.io_entries:
            self.io_entries = []
            entry_list = self.get_all_entries()
            for entry in entry_list:
                try:
                    entry.get_content()
                except KQMLException:
                    logger.debug("Failed to get content for:\n%s."
                                 % repr(entry))
                    continue
                if entry.get_sem() is not None:
                    self.io_entries.append(entry)
        return self.io_entries


def logs_to_html_file(log_dir_path, html_file=None):
    if html_file is None:
        html_file = os.path.join(log_dir_path, 'transcript.html')

    log = CwcLog(log_dir_path)

    html_parts = ['<div class="container">']

    start_time = log.get_start_time()
    html_parts.append(format_start_time(start_time))

    # Find all messages received by the BA
    for entry in log.get_io_entries():
        html_part = entry.make_html()
        if html_part is not None:
            html_parts.append(html_part)
    html_parts.append('</div>')

    with open(html_file, 'w') as fh:
        fh.write(make_html(html_parts))


if __name__ == '__main__':
    logs_to_html_file(sys.argv[1])
