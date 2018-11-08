import os
import boto3
import docker
import tarfile
from io import BytesIO


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
        print("WARNING: Failed to get images from the bioagents.")
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
    return '%s_%s_%s' % (cont.image.attrs['Config']['Image'].replace(':', '-'),
                         cont.image.attrs['Config']['Hostname'], cont.name)


def get_logs_for_container(cont):
    tasks = [get_session_logs, get_run_logs, get_bioagent_images]
    fnames = []
    for task in tasks:
        fname = task(cont)
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
    s3 = boto3.client('s3')
    contents = res = s3.list_objects(Bucket='cwc-hms',
                                     Prefix='bob_ec2_logs')['Contents']
    # Here we only get the tar.gz files which contain the logs for the
    # facilitator
    keys = [content['Key'] for content in contents if
            content['Key'].startswith('bob_ec2_logs/cwc-integ') and
            content['Key'].endswith('.tar.gz')]
    print('Found %d keys' % len(keys))

    for key in tqdm.tqdm(keys):
        # Replace a couple of things in the key to make the actual fname
        fname = key.replace('/', '_')
        fname = fname.replace('bob_ec2_logs_cwc-integ:latest_', '')
        fname = fname.replace('bob_ec2_logs_cwc-integ_', '')
        fname = fname.replace('.tar.gz', '.txt')
        if folder:
            fname = os.path.join(folder, fname)
        if cached and os.path.exists(fname):
            print('File already exists: %s' % fname)
            continue

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
            with open(fname, 'w') as fh:
                print('Writing file %s' % fname)
                fh.write(log_txt)


if __name__ == '__main__':
    get_logs()
