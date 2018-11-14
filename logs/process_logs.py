import os
import re
import sys
import textwrap

from kqml import *

import logging
logger = logging.getLogger('log_processor')

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
IMG_DIRNAME = 'images'


def make_html(html_parts):
    with open(os.path.join(THIS_DIR, 'page_template.html'), 'r') as fh:
        template = fh.read()

    html = template.replace('%%%CONTENT%%%', '\n'.join(html_parts))
    return html


class CwcLogEntry(object):
    """Parent class for entries in the logs."""
    possible_sems = ('sys_utterance', 'user_utterance', 'display_image',
                     'add_provenance', 'display_sbgn')

    def __init__(self, type, time, message, partner, log_dir):
        self.type = type
        self.time = time
        self.message = message
        self.partner = partner
        self.log_dir = log_dir
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
        cont = self.content.get('content')
        fmt = """
        <div class="row {sem}" style="margin-top: 15px">
            <div class="col-sm {col_sm}">
                <span style="background-color:{back_clr}; color:{fore_clr}">
                    {name}:
                </span>&nbsp;<a style="color: #BDBDBD">{time}</a>
            </div>
        </div>

        <div class="row {sem}" style="margin-bottom: 15px">
          <div class="col-sm {msg_sm}">{inp}</div>
        </div>
        """
        bob_back = '#2E64FE'
        usr_back = '#A5DF00'
        fore_clr = '#FFFFFF'
        if self.is_sem('sys_utterance'):
            print('SYS:', str(self.content)[:500])
            inp = cont.gets('what')
            name = 'Bob'
            back_clr = bob_back
            col_sm = 'sys_name'
            msg_sm = 'sys_msg'
        elif self.is_sem('user_utterance'):
            print('USR:', str(self.content)[:500])
            inp = cont.gets('text')
            name = 'User'
            back_clr = usr_back
            col_sm = 'usr_name'
            msg_sm = 'usr_msg'
        elif self.is_sem('add_provenance'):
            print("SYS sent provenance.")
            inp = cont.gets('html')
            name = 'Bob (provenance)'
            back_clr = bob_back
            col_sm = 'sys_name'
            msg_sm = 'prov_html'
        elif self.is_sem('display_image'):
            print("SYS sent image: %s" % cont.gets('path'))
            img_path = cont.gets('path').split(os.path.sep)
            if IMG_DIRNAME not in img_path:
                logger.warning("Image not shown: its path lacks correct "
                               "structure: %s" % img_path)
                img_loc = ""
            else:
                img_path_seg = img_path[img_path.index(IMG_DIRNAME):]
                img_loc = os.path.sep.join(img_path_seg)
                img_loc = os.path.abspath(os.path.join(self.log_dir, img_loc))
            inp = ('<img src=\"{img}\" alt=\"Image {img} Not Available\">'
                   .format(img=img_loc))
            name = 'Bob (%s)' % cont.gets('type')
            back_clr = bob_back
            col_sm = 'sys_name'
            msg_sm = 'sys_image'
        else:
            return None
        return textwrap.dedent(fmt.format(time=self.time, inp=inp, name=name,
                                          col_sm=col_sm, msg_sm=msg_sm,
                                          back_clr=back_clr, fore_clr=fore_clr,
                                          sem=self.get_sem()))

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
    container_name_patt = re.compile('([\w-]+)_(\w+?_\w+?)_(\w+)')

    def __init__(self, log_dir):
        self.log_dir = log_dir

        # Load and parse the log file.
        self.log_file = os.path.join(log_dir, 'log.txt')
        with open(self.log_file, 'r') as f:
            self.__log = f.read()
        self.start_time = None
        self.container_name = None
        self.all_entries = None

        # Get familiar with the image stash, if present.
        self.img_dir = os.path.join(log_dir, IMG_DIRNAME)
        if not os.path.exists(self.img_dir):
            # If the logs are old and there's no image directory, we'll just
            # have to live without images.
            logger.warning("No image directory \"%s\" found. This transcript "
                           "will have no images included." % self.img_dir)
            self.img_dir = None

        # This is filled later.
        self.io_entries = None
        return

    def get_container_name(self):
        if self.container_name is None:
            m = self.container_name_patt.match(os.path.basename(self.log_dir))
            assert m is not None, "Failed to get container name."
            self.container_name = m.groups()[1]
        return self.container_name

    def get_start_time(self):
        if self.start_time is None:
            logger.info("Loading start time...")
            tp = self.time_patt.search(self.__log)
            assert tp is not None, "Failed to get time string."
            self.start_time = ' '.join(tp.groups())
        return self.start_time

    def get_all_entries(self):
        if self.all_entries is None:
            logger.info("Loading log entries...")
            self.all_entries = []
            sec_list = self.section_patt.findall(self.__log)
            assert sec_list, "Failed to find any sections."
            for typ, dt, other_type, partner, msg in sec_list:
                entry = CwcLogEntry(typ, dt, msg, partner, self.log_dir)
                self.all_entries.append(entry)
            logger.info("Found %d log entries." % len(self.all_entries))
        return self.all_entries

    def get_io_entries(self):
        if not self.io_entries:
            self.io_entries = []
            entry_list = self.get_all_entries()
            logger.info("Filtering to io entries...")
            for entry in entry_list:
                try:
                    entry.get_content()
                except KQMLException:
                    logger.debug("Failed to get content for:\n%s."
                                 % repr(entry))
                    continue
                if entry.get_sem() is not None:
                    self.io_entries.append(entry)
            logger.info("Found %d io entries." % len(self.io_entries))
        return self.io_entries

    def make_header(self):
        html = """
        <div class="row start_time">
          <div class="col-sm">
            Dialogue with {container} started at: {start_time}
          </div>
        </div>
        """.format(start_time=self.get_start_time(),
                   container=self.get_container_name())
        return textwrap.dedent(html)

    def make_html(self):
        html_parts = ['<div class="container">']
        html_parts.append(self.make_header())

        # Find all messages received by the BA
        for entry in self.get_io_entries():
            html_part = entry.make_html()
            if html_part is not None:
                html_parts.append(html_part)
        html_parts.append('</div>')
        return make_html(html_parts)


def export_logs(log_dir_path, out_file=None, file_type='html'):
    file_type = file_type.lower()
    if out_file and out_file.endswith('.pdf'):
        file_type = 'pdf'
    if file_type not in ['pdf', 'html']:
        raise ValueError("Invalid file type: %s." % file_type)

    if out_file is None:
        out_file = os.path.join(log_dir_path, 'transcript.' + file_type)

    log = CwcLog(log_dir_path)
    html = log.make_html()

    if file_type == 'html':
        with open(out_file, 'w') as fh:
            fh.write(html)
    elif file_type == 'pdf':
        try:
            import pdfkit
        except ImportError:
            logger.error("Could not import necessary module: pdfkit.")
            return
        pdfkit.from_string(html, out_file)
    logger.info("Result saved to %s." % out_file)


if __name__ == '__main__':
    export_logs(sys.argv[1])
