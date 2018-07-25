import boto3
import docker
from datetime import datetime


def c_ls(container, dirname):
    started = False
    if container.status == 'exited':
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


def format_cont_date(cont):
    cont_date = ('-'.join(cont.attrs['Created'].replace(':', '-')
                 .replace('.', '-').split('-')[:-1]))
    return cont_date


def make_cont_name(cont):
    return '%s_%s_%s' % (cont.image.attrs['Config']['Image'],
                         cont.image.attrs['Config']['Hostname'], cont.name)


def get_logs_for_container(cont):
    ses_log_fname = get_session_logs(cont)
    run_log_fname = get_run_logs(cont)
    for fname in [ses_log_fname, run_log_fname]:
        _dump_on_s3(fname)
    return


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
    client = docker.from_env()
    cont_list = client.containers.list(True)
    master_logs = []
    log_arches = []
    for cont in cont_list:
        master_logs.append(get_session_logs(cont))
        log_arches.append(get_run_logs(cont))
    print("Found the following logs:")
    print(master_logs)
    print(log_arches)
    now = datetime.now()
    for fname in log_arches + master_logs:
        _dump_on_s3(fname)
    return


if __name__ == '__main__':
    get_logs()
