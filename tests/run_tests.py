import os
import sys
import json

import argparse

from time import time
from jeanny3 import Collection, uuid

from hashtrace import *

from unittests import runtest 

def test_dummy():
    """ dummy test function """
    t = time()
    col = Collection()
    # do something here, fill the aux collection
    t = time()-t
    return t,col

def test_drop():
    """ simple test on droping local backend """    
    
    t = time()
    col = Collection()
    
    from random import choice
    from string import ascii_letters
    
    root = SETTINGS['REPOSITORY_DIR']
    #db_backend = SETTINGS[???] # TODO!!!
    
    def random_string(n=10):
        return ''.join([choice(ascii_letters) for _ in range(n)])
    
    def create_random_file(path):
        with open(path,'w') as f:
            f.write(random_string(n=100))
        print('  created file',path)
    
    def create_random_dir():
        dirname = random_string(n=10)
        path=os.path.join(root,dirname)
        os.mkdir(path)
        print('created dir',path)
        return dirname
    
    def fill_dir(dirname,nfiles):
        for _ in range(nfiles):
            filename = random_string(n=5)
            path = os.path.join(root,dirname,filename)
            create_random_file(path)
                
    # create random dirs
    ndirs = 3
    for _ in range(ndirs):
        dirname = create_random_dir()
        fill_dir(dirname,nfiles=5)

    print('')
    
    # drop all content
    db_backend.drop()
    
    print('\ndropped content successfuly')
    
    t = time()-t
    return t,col
        
def test_():
    """  """    

    t = time()
    col = Collection()


    t = time()-t
    return t,col


def test_sum_1():
    """ simple test on tracking, no caching, no autosave """    

    t = time()
    col = Collection()
    
    # drop the local repository
    db_backend.drop()
    
    @track(nout=1,cache=False,autosave=False)
    def plus(a,b):
        return a+b

    c = plus(1,2)
    
    save_graph(c)
    
    t = time()-t
    return t,col

def test_pass_tfunc():
    """ test on passing the other tracked as an argument """
    pass

TEST_CASES = [
    
]

def get_test_cases(func_names):
    args = func_names
    if not args:
        return TEST_CASES
    test_cases = []
    for arg in args:
        test_cases.append(eval(arg))
    return test_cases

def do_tests(test_cases,testgroup=None,session_name=None): # test all functions    
    
    if testgroup is None:
        testgroup = __file__

    session_uuid = uuid()
    
    for test_fun in test_cases:        
        runtest(test_fun,testgroup,session_name,session_uuid,save=True)
        
if __name__=='__main__':

    parser = argparse.ArgumentParser(description=\
        'Test driver for the HashTrace Python library.')

    parser.add_argument('--session', type=str, default='__not_supplied__',
        help='Session name')

    parser.add_argument('--verbose', dest='verbose',
        action='store_const', const=True, default=False,
        help='Verbose mode')

    parser.add_argument('--breakpoints', dest='breakpoints',
        action='store_const', const=True, default=False,
        help='Turn on breakpoints')

    parser.add_argument('--debug', dest='debug',
        action='store_const', const=True, default=False,
        help='Grammar debugging mode')

    parser.add_argument('--cases', nargs='*', type=str, 
        help='List of test cases (functions)')
        
    args = parser.parse_args() 

    SETTINGS['VERBOSE'] = args.verbose
    SETTINGS['DEBUG'] = args.debug
    SETTINGS['BREAKPOINTS'] = args.breakpoints    
        
    test_cases = get_test_cases(args.cases)
        
    do_tests(test_cases=test_cases,session_name=args.session)
    
