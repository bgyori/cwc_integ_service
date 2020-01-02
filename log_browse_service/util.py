import os
import sys
import scrypt
import pathlib
from os import path
from time import sleep
from base64 import b64encode


HOME = str(pathlib.Path.home())
HASH_PASS_FNAME = '.hp_cwc_log_browser'
HASH_PASS_FPATH = path.join(HOME, HASH_PASS_FNAME)


def hash_password(password, maxtime=0.5, datalength=64):
    hp = scrypt.encrypt(b64encode(os.urandom(datalength)), password,
                        maxtime=maxtime)
    return hp


def verify_password(hashed_password, guessed_password, maxtime=0.5):
    try:
        scrypt.decrypt(hashed_password, guessed_password, maxtime)
        return True
    except scrypt.error:
        sleep(1)
        return False


if __name__ == '__main__':
    pwd = sys.argv[1]
    hashed_pass = hash_password(pwd)
    with open(HASH_PASS_FPATH, 'wb') as bf:
        bf.write(hashed_pass)

    # Verify that the hashed password has been saved correctly
    with open(HASH_PASS_FPATH, 'rb') as f:
        hp = f.read()
    if verify_password(hashed_password=hp,
                       guessed_password=pwd):
        print('hashed password correctly saved to file %s' % HASH_PASS_FPATH)
    else:
        print('hashed password not saved properly')
