import os
import re

import boto3
import docker
import tarfile
from datetime import datetime
from io import BytesIO
from indra.util.aws import get_s3_file_tree

import logging
logger = logging.getLogger('log-getter')


def c_ls(container, dirname):
    started = False
    if container.status != 'running':
        started = True
        container.start()
        container.attach()

    res = container.exec_run(['ls', dirname])
    if started:
        container.stop()

    return res.output.decode().splitlines()


def get_run_logs(cont):
    dir_conts = c_ls(cont, 'cwc-integ')
    possible_results = [p for p in dir_conts if p.startswith('20')]
    if not possible_results:
        return None
    my_result = max(possible_results)
    arch_name = '%s_%s.tar.gz' % (make_cont_name(cont), my_result)
    with open(arch_name, 'wb') as f:
        bts, meta = cont.get_archive('/sw/cwc-integ/' + my_result)
        for bit in bts:
            f.write(bit)
    return arch_name


def get_session_logs(cont):
    fname = '%s_%s.log' % (make_cont_name(cont), format_cont_date(cont))
    with open(fname, 'wb') as f:
        f.write(cont.logs())
    return fname


def get_bioagent_images(cont):
    try:
        bts, meta = cont.get_archive(
            '/sw/cwc-integ/hms/bioagents/bioagents/images'
            )
    except Exception as e:
        logger.warning("Failed to get images from the bioagents.")
        return None
    arch_name = '%s_bioagent_images.tar.gz' % make_cont_name(cont)
    with open(arch_name, 'wb') as f:
        for bit in bts:
            f.write(bit)
    return arch_name


def format_cont_date(cont):
    cont_date = ('-'.join(cont.attrs['Created'].replace(':', '-')
                 .replace('.', '-').split('-')[:-1]))
    return cont_date


def make_cont_name(cont):
    img_date = datetime.strptime(cont.image.attrs['Created'].split('.')[0],
                                 '%Y-%m-%dT%H:%M:%S')
    img_id = '%s-%s' % (cont.image.attrs['Id'].split(':')[1][:12],
                        img_date.strftime('%Y%m%d%H%M%S'))
    return '%s_%s_%s' % (img_id, cont.attrs['Id'][:12], cont.name)


def get_logs_for_container(cont, interface):
    tasks = [get_session_logs, get_run_logs, get_bioagent_images]
    fnames = []
    for task in tasks:
        # Get the logs.
        fname = task(cont)

        # Rename the log file. This is a little hacky, but it should work.
        new_fname = interface + '-' + fname
        os.rename(fname, new_fname)
        fname = new_fname

        # Add the file to s3.
        logger.info("Saved %s locally." % fname)
        fnames.append(fname)
        _dump_on_s3(fname)
    return tuple(fnames)


def _dump_on_s3(fname):
    s3 = boto3.client('s3')
    s3_bucket = 'cwc-hms'
    s3_prefix = 'bob_ec2_logs/'
    if not fname:
        return
    with open(fname, 'rb') as f:
        s3.put_object(Key=s3_prefix + fname, Body=f.read(),
                      Bucket=s3_bucket)
    logger.info("%s dumped on s3." % fname)
    return


def get_logs():
    """Get logs from local Docker instances and upload them to S3."""
    client = docker.from_env()
    cont_list = client.containers.list(True)
    master_logs = []
    log_arches = []
    img_arches = []
    for cont in cont_list:
        ses_name, run_name, img_name = get_logs_for_container(cont)
        master_logs.append(ses_name)
        log_arches.append(run_name)
        img_arches.append(img_name)
    print("Found the following logs:")
    print(master_logs)
    print(log_arches)
    print(img_arches)
    return


def get_logs_from_s3(folder=None, cached=True):
    """Download logs from S3 and save into a local folder"""
    import tqdm

    # TODO: We are going to have to page through s3 logs. We can only get at
    # most 1000 items. I wrote something to handle this here:
    # https://github.com/indralab/indra_db/blob/a32132a2a8ecb10fea07666abafbffb50dd77679/indra_db/reading/submit_reading_pipeline.py#L193-L204
    s3 = boto3.client('s3')
    tree = get_s3_file_tree(s3, 'cwc-hms', 'bob_ec2_logs')
    keys = tree.gets('key')
    # Here we only get the tar.gz files which contain the logs for the
    # facilitator
    print(len(keys))
    print(len([k for k in keys if 'image' in k]))
    keys = [key for key in keys if key.startswith('bob_ec2_logs/cwc-integ')
            and key.endswith('.tar.gz')]
    print(len(keys))
    print('Found %d keys' % len(keys))

    fname_patt = re.compile('([\w:-]+?)_(\w+?)_(\w+?_\w+?)_(.*).tar.gz')
    dir_set = set()
    for key in tqdm.tqdm(keys):
        fname = os.path.basename(key)
        m = fname_patt.match(fname)
        assert m is not None, "Failed to match %s" % fname_patt
        image_id, cont_hash, cont_name, resource_name = m.groups()
        head_dir_path = '%s_%s_%s' % (image_id.replace(':', '-'), cont_name,
                                      cont_hash)
        dir_set.add(head_dir_path)
        if folder:
            head_dir_path = os.path.join(folder, head_dir_path)
        if not os.path.exists(head_dir_path):
            os.mkdir(head_dir_path)
        if resource_name == 'bioagent_images':
            outpath = head_dir_path
        else:
            outpath = os.path.join(head_dir_path, 'log.txt')
            if cached and os.path.exists(outpath):
                continue

        res = s3.get_object(Bucket='cwc-hms', Key=key)
        byte_stream = BytesIO(res['Body'].read())
        with tarfile.open(None, 'r', fileobj=byte_stream) as tarf:
            if resource_name == 'bioagent_images':
                tarf.extractall(outpath)
            else:
                outpaths = tarf.getnames()
                facls = [n for n in outpaths if n.endswith('facilitator.log')]
                if not facls:
                    print('No facilitator.log found for %s' % key)
                    continue
                facl = facls[0]
                efo = tarf.extractfile(facl)
                log_txt = efo.read().decode('utf-8')
                with open(outpath, 'w') as fh:
                    fh.write(log_txt)
    return dir_set


if __name__ == '__main__':
    get_logs()
