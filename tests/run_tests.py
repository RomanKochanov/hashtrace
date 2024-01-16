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

def test_sum_1():
    """ simple test on tracking, no caching, no autosave """    

    t = time()
    col = Collection()
    
    @track(nout=1,cache=False,autosave=False)
    def plus(a,b):
        return a+b

    c = plus(1,2)
    
    save_graph(c)
    
    t = time()-t
    return t,col

TEST_CASES = [
    test_sum_1,
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

    VARSPACE['VERBOSE'] = args.verbose
    VARSPACE['DEBUG'] = args.debug
    VARSPACE['BREAKPOINTS'] = args.breakpoints    
        
    test_cases = get_test_cases(args.cases)
        
    do_tests(test_cases=test_cases,session_name=args.session)
    
