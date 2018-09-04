import re
import sys
import time
import xml.etree.ElementTree as ET

tags_replace = {
        'ekb': '[EKB]',
        'sbgn': '[SBGN]',
        'a ': '[link]',
        'i': '[italic]',
        'ul': '[list]',
        'li': '[list]',
        'h4': '[heading]',
        'table': '[table]'
        }

def read_fix_log(log):
    """Return an XML ElementTree of the log."""
    # First just simply remove some tags
    for tag in ['b', 'i', 'p']:
        log = log.replace('<%s>' % tag, '')
        log = log.replace('</%s>' % tag, '')
    # Add missing closing tag
    log += '\n</LOG>'
    # Replace invalid character
    log = log.replace('&', '&amp;')
    log = log.replace('<br>', '\n\n')
    # Replace <ekb>...</ekb>
    for tag, rep in tags_replace.items():
        log = re.sub('<%s[\s\S][^<]+/>' % tag, rep, log, flags=(re.MULTILINE | re.DOTALL))
        log = re.sub('<%s\s.*?</%s>' % (tag, tag), rep, log, flags=(re.MULTILINE | re.DOTALL))
    # TODO: generalize formatting and generalize these
    log = log.replace('<hr>', '')
    # TODO: Not sure why this is needed here again but it is, currently
    log = re.sub('<a\s.*?</a>', '[link]', log, flags=(re.MULTILINE | re.DOTALL))
    # For debugging purposes, save the log that goes
    # into the XML element tree
    with open('log_tmp.xml', 'w') as fh:
        fh.write(log)
    tree = ET.fromstring(log)
    return tree

def is_sent_by(tag, sender):
    tag_sender = tag.attrib.get('S')
    if not tag_sender:
        return False
    return tag_sender.upper() == sender.upper()

def is_received_by(tag, receiver):
    tag_receiver = tag.attrib.get('R')
    if not tag_receiver:
        return False
    return tag_receiver.upper() == receiver.upper()

def get_dialogue_datetime(tag):
    date = tag.attrib.get('DATE')
    timet = tag.attrib.get('TIME')
    simple_str = '%s %s' % (date, timet)
    time_obj = time.mktime(time.strptime(simple_str, '%m/%d/%y %I:%M %p'))
    return simple_str, time_obj

def reformat_text(txt):
    txt = txt.replace('<b>', '\\textbf{')
    txt = txt.replace('</b>', '}')
    txt = txt.replace('%', '\\%')
    txt = txt.replace('_', '\\_')
    return txt

def get_timestamp(tag, dialogue_start):
    timestamp = tag.attrib.get('T')
    time_struct = time.strptime(timestamp[:-3], '%H:%M:%S')
    time_obj = dialogue_start + 3600*time_struct.tm_hour + \
        60*time_struct.tm_min + time_struct.tm_sec
    return timestamp, time_obj

def latex_wrapper(datetime, content):
    header = '\\documentclass{article}\n'
    header += '\\usepackage{xcolor}\n'
    header += '\\usepackage{graphicx}\n'
    header += '\\usepackage[margin=1.2in]{geometry}\n'
    header += '\\begin{document}\n\n'
    header += '\\title{Exported dialogues}\n'
    header += '\\date{%s}\n' % datetime
    header += '\\maketitle\n\n'
    footer = '\\end{document}'
    latex_str = header + content + footer
    return latex_str

def latex_line(line):
    user, time, msg_type, msg = line
    if msg_type == 'txt':
        time_str = '\\textcolor{orange}{[%s]}' % time
        if user == 'Bob':
            user_str = '\\textcolor{blue}{Bob}'
        else:
            user_str = '\\textcolor{green}{User}'
        line_str = '\\noindent %s %s: %s' % (time_str, user_str, msg)
    elif msg_type == 'img':
        #line_str = '\\begin{graphical}\n'
        line_str = '\\includegraphics[width=0.6\\textwidth]{%s}\n' % msg
        #line_str += '\\end{graphical}'
    return line_str


def facilitator_to_tex_file(input_file, output_file, images_folder=None):
    with open(input_file, 'r') as fh:
        log = fh.read()
    full_latex = facilitator_to_tex_str(log, images_folder=None)
    with open(output_file, 'wb') as fh:
        fh.write(full_latex.encode('utf8'))


def facilitator_to_tex_str(log, images_folder=None):
    tree = read_fix_log(log)
    datetime, datetime_obj = get_dialogue_datetime(tree)

    # Process the input first
    dialogues = [[]]
    for tag in tree:
        # Get message text
        msg = tag.text
        if not msg:
            continue
        msg = msg.strip()
        ts, ts_obj = get_timestamp(tag, datetime_obj)
        # Look for start conversation
        if msg.upper() == \
            '(BROADCAST :CONTENT (TELL :CONTENT (START-CONVERSATION)))' or \
            msg.upper() == '(TELL :CONTENT (START-CONVERSATION))':
            dialogues.append([])
        # Look for user utterance
        if is_received_by(tag, 'texttagger'):
            match = re.match(r'\(REQUEST :CONTENT \(TAG :TEXT "(.*)" .*\)', msg)
            if match:
                txt = match.groups()[0]
                txt = reformat_text(txt)
                dialogues[-1].append(('User', ts, 'txt', txt))
        elif is_sent_by(tag, 'SBGNVIZ-INTERFACE-AGENT'):
            match = re.match(r'\(tell :content \(word "(.*)" .*\)', msg,
                             flags=(re.MULTILINE | re.DOTALL))
            if match:
                txt = match.groups()[0]
                txt = reformat_text(txt)
                dialogues[-1].append(('User', ts, 'txt', txt))
        elif is_received_by(tag, 'SBGNVIZ-INTERFACE-AGENT'):
            for img_type in ('reactionnetwork', 'simulation'):
                p = r'\(tell :content \(display-image :type %s :path "(.*)"\)' % img_type
                match = re.match(p, msg, flags=(re.MULTILINE | re.DOTALL))
                if match:
                    img_path = match.groups()[0]
                    img_name = img_path.split('/')[-1]
                    if images_folder:
                        img_name = images_folder + img_name
                    dialogues[-1].append(('Bob', ts, 'img', img_name))
        # Look for system utterance
        if is_received_by(tag, 'keyboard'):
            match = re.match(r'\(TELL :CONTENT \(SPOKEN :WHAT "(.*)"\)', msg,
                             flags=(re.MULTILINE | re.DOTALL))
            if match:
                txt = match.groups()[0]
                txt = reformat_text(txt)
                dialogues[-1].append(('Bob', ts, 'txt', txt))


    # Assemble the output
    latex_str = ''
    for dialogue in dialogues:
        for line in dialogue:
            latex_str += latex_line(line)
            latex_str += '\n\n'
        latex_str += '\n\n'
        latex_str += '\\noindent\\rule{\\textwidth}{1pt}\n\n'
    full_latex = latex_wrapper(datetime, latex_str)
    return full_latex


def process_logs_from_s3():
    """Download logs from S3, extract dialogues, and save as PDF"""
    import os
    import boto3
    import tarfile
    import subprocess
    from io import BytesIO
    s3 = boto3.client('s3')
    contents = res = s3.list_objects(Bucket='cwc-hms',
                                     Prefix='bob_ec2_logs')['Contents']
    # Here we only get the tar.gz files which contain the logs for the
    # facilitator
    keys = [content['Key'] for content in contents if
            content['Key'].startswith('bob_ec2_logs/cwc-integ') and
            content['Key'].endswith('.tar.gz')]
    print('Found %d keys' % len(keys))

    for key in keys:
        basename = os.path.basename(key)
        res = s3.get_object(Bucket='cwc-hms', Key=key)
        byte_stream = BytesIO(res['Body'].read())
        with tarfile.open(None, 'r', fileobj=byte_stream) as tarf:
            fnames = tarf.getnames()
            facls = [n for n in fnames if n.endswith('facilitator.log')]
            if not facls:
                print('No facilitator.log found for %s' % key)
                continue
            facl = facls[0]
            efo = tarf.extractfile(facl)
            log_txt = efo.read().decode('utf-8')
            full_latex = facilitator_to_tex_str(log_txt)
            print('Writing tex to %s.tex' % basename)
            with open('logs/%s.tex' % basename, 'w') as fh:
                fh.write(full_latex)
            subprocess.run(['pdflatex', 'logs/%s.tex' % basename])


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python process_logs.py <input_file> <output_file>')
        print(' <input_file>: a facilitator log file')
        print(' <output_file>: a latex (.tex) file')
        print(' [<images_folder>]: optional, folder with time stamped images')
        sys.exit()
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    if len(sys.argv) >= 4:
        images_folder = sys.argv[3]
    else:
        images_folder = None
    facilitator_to_tex_file(input_file, output_file, images_folder)

