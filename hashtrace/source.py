import os
import io
import re
import sys
import dis
import json
import types
#import ctypes
#import pickle # should be used only with elementary types!!!
#import dill # uses pickle; can serialize types
import shutil
import hashlib
import inspect
import binascii
import unittest
import textwrap
import importlib

import numpy as np

#import jeanny3 as j # DEFAULT STORAGE FOR HASHED OBJECTS

from .conf import collections as j
from abc import abstractmethod, ABC

# !!! PYTHON HAS FASTER BUILD-IN IMPLEMENTATION OF MD5 HASHSUMS: _MD5
# https://stackoverflow.com/questions/59955854/what-is-md5-md5-and-why-is-hashlib-md5-so-much-slower

import sqlite3

import zlib
archlib = zlib

SETTINGS = {
    'ENCODING': 'utf-8',
    'REPOSITORY_DIR': '.provenance',
    'DEBUG': False,
    'DEBUG_SUBGRAPH': False,
}

VARSPACE = {}

#VARSPACE = {
#    'DEBUG': False,
#    'DEBUG_SUBGRAPH': False,
#}

#ENCODING = 'utf-8'
#REPOSITORY_DIR = '.provenance'

def calc_hash_sha256_bin(binbuf):
    """ Hash function must return digest. Buffer must be a UTF-8 string. """
    m = hashlib.sha256()
    m.update(binbuf)
    return m.hexdigest()
calc_hash_sha256_str = lambda strbuf: calc_hash_sha256_bin(strbuf.encode(SETTINGS['ENCODING'])) 

def calc_hash_md5_bin(binbuf):
    """ Hash function must return digest. Buffer must be a UTF-8 string. """
    m = hashlib.md5()
    m.update(binbuf)
    return m.hexdigest()
calc_hash_md5_str = lambda strbuf: calc_hash_md5_bin(strbuf.encode(SETTINGS['ENCODING'])) 

#calc_hash_str = calc_hash_sha256_str
#calc_hash_bin = calc_hash_sha256_bin

calc_hash_str = calc_hash_md5_str
calc_hash_bin = calc_hash_md5_bin

def encrypt_xor(var, key): # free from the "signed" hexadecimal hash bug
    """ Encrypt order-dependent, based on implication (p=>q <-> not(p) OR q)"""
    var = binascii.unhexlify(var)
    key = binascii.unhexlify(key)
    a = np.frombuffer(var, dtype = np.uint8)
    b = np.frombuffer(key, dtype = np.uint8)
    result = (a^b).tobytes()
    return binascii.hexlify(result).decode(SETTINGS['ENCODING'])

def hashsum_list_noorder(hashlist):
    """ Calculate sum of hashes to produce an order-invariant hash.
    """
    total_hash = calc_hash_str('')
    for h in hashlist:
        total_hash = encrypt_xor(total_hash,h)
    return total_hash
    
def encrypt_impl(var, key):
    """ Encrypt order-dependent, based on implication (p=>q <-> not(p) OR q)"""
    var = binascii.unhexlify(var)
    key = binascii.unhexlify(key)
    a = np.frombuffer(var, dtype = np.uint8)
    b = np.frombuffer(key, dtype = np.uint8)
    result = (np.invert(a)|b).tobytes()
    return binascii.hexlify(result).decode(SETTINGS['ENCODING'])

def hashsum_list_order(hashlist):
    """ Calculate sum of hashes to produce an order-dependent hash.
    """
    total_hash = calc_hash_str('')
    for h in hashlist:
        total_hash = encrypt_impl(total_hash,h)
    return total_hash

def hashsum_dict(hashdict): 
    """ Calculate sum of hashes in the dict (no order dependence).
    """
    items = hashdict.items()
    HASH = calc_hash_str('')
    for key,hash_ in items:
        key_str = calc_hash_str(dump_to_string(key))
        HASH_ITEM = hashsum_list_order([HASH, key_str, hash_])
        HASH = hashsum_list_noorder([HASH, HASH_ITEM])
    return HASH

def calc_hash_dict(dct): # dict
    """ Convert dictionary to binary buffer.
        HASH IS ORDER-INDEPENDENT
        
        RECURSION FTW:
        (key1,val1, key2,val2, ..., keyN,valN)
                          | -> recursion
                          (key21,val21, key22,val22, ..., key2M,val2M)
                                  | -> recursion
                                  (key211,val21, key212,val212, ..., key21M,val21M)
    """
    items = dct.items()
    HASH = calc_hash_str('')
    for key,val in items:
        
        if type(val) is dict:
            val = calc_hash_dict(val)
        elif type(val) in [list,tuple]:
            val = calc_hash_list(val)
        
        key_hash = calc_hash_str(dump_to_string(key))
        val_hash = calc_hash_str(dump_to_string(val))
        
        HASH = hashsum_list_noorder([HASH, key_hash, val_hash])
    
    return HASH

def calc_hash_list(lst): # list, tuple
    """ Convert dictionary to binary buffer.
        HASH IS ORDER-DEPENDENT
    """
    items = lst
    HASH = calc_hash_str('')
    for val in items:
                
        if type(val) is dict:
            val = calc_hash_dict(val)
        elif type(val) in [list,tuple]:
            val = calc_hash_list(val)
        
        val_hash = calc_hash_str(dump_to_string(val))
                
        HASH = hashsum_list_order([HASH, val_hash])
    
    return HASH

def dump_to_string(obj,sort_keys=False): # FAST
    return json.dumps(obj,sort_keys=sort_keys)

def load_from_string(buf): # FAST
    return json.loads(buf)

class BackendDispatcher(ABC):
    """ Abstract class for database backend. """
    
    @abstractmethod
    def __init__(self):
        """ connect to existing database or read data from file  """
        pass
  
    #@abstractmethod
    #def connect(self):
    #    pass
        
    @abstractmethod
    def save(self,database):
        """ save/export contents to disc """
        pass
    
    @abstractmethod
    def exists(self,hashval):
        """ check if container with a given hash exists in the database """
        pass

    @abstractmethod
    def search(self,hashval):
        """ fetch the container object from the database """
        pass
        
    @abstractmethod
    def insert(self,container):
        """ insert container to the database """
        pass
        
    @abstractmethod
    def tabulate(self,limit=20,offset=0):
        """ tabulate container list """
        pass
        
    @abstractmethod
    def drop(self):
        """ drop local storage (mostly for testing purposes) """
        pass

class CSVBackend(BackendDispatcher):
    """
    Pure Collection backend - all data are situated in RAM.
    """
    def __init__(self):
        self.__collection__ = j.Collection()
    
    def connect(self,filename):
        col = j.Collection(); col.import_csv(filename,duck=False)
        dicthash = {}
        for item in col.getitems():
            container_class_name = item['container_class']
            contained_class_name = item['contained_class']
            registry_item = Container.__registry__[contained_class_name]
            container_class = registry_item['child_class']
            con = container_class()
            con.__classname__ = contained_class_name
            con.__buffer__ = item['buffer']
            con.__hashval__ = item['hashval']            
            dicthash[con.__hashval__] = {'container':con}
        self.__collection__.__dicthash__.update(dicthash)
    
    def save(self,filename):
        with open(filename,'w') as f:
            delim = ';'
            order = ['container_class','contained_class','hashval','buffer']
            header = delim.join(order)+'\n'
            f.write(header)
            for item in self.__collection__.getitems():
                container = item['container']
                hashval = container.__hashval__
                container_class_name = type(container).__name__
                contained_class_name = container.__classname__
                buffer = container.__buffer__
                line = delim.join([
                    '%s'%container_class_name,
                    '%s'%contained_class_name,
                    '%s'%hashval,
                    '%s'%buffer,
                ])+'\n'
                f.write(line)

    def exists(self,hashval):
        return hashval in self.__collection__.__dicthash__
    
    def search(self,hashval):
        item = self.__collection__.__dicthash__.get(hashval)
        if item is None:
            return None
        else:
            return item['container']       
        
    def insert(self,container):
        self.__collection__.__dicthash__[container.__hashval__] = \
            {'container':container}
            
    def drop(self):
        self.__collection__.clear()

class SQLiteBackend(BackendDispatcher):
    """
    SQLite-based backend is splitted in two parts, both situated 
    in local repository subfolder:
        1) Header table situated in the SQLite file.
        2) Content filesystem is organized in Git-like manner (by hashes).
    Header table contain only two columns: ContainerType and Hash.
    """
    def __init__(self,database='headers.sqlite'):
        # open connection to database
        dbpath = os.path.join(SETTINGS['REPOSITORY_DIR'],database)
        os.makedirs(SETTINGS['REPOSITORY_DIR'],exist_ok=True)
        connection = sqlite3.connect(dbpath)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        self.__connection__ = connection
        self.__cursor__ = cursor
        self.__dbfile__ = database
        # create header table if not exists
        cursor.execute(
            'create table if not exists content('
                'container_class varchar, '
                'contained_class varchar, '
                'hashval varchar primary key'
            ')'
        )
    
    def save(self,filename=None):
        self.__connection__.commit() # filesystem is not transactioned

    def __load_header__(self,hashval):
        """ aux method"""
        cursor = self.__cursor__
        cursor.execute('select * from content where hashval=="%s"'%hashval)
        row = cursor.fetchone()
        return row

    def __save_header__(self,container):
        """ aux method"""
        if self.__load_header__(container.__hashval__): 
            return True
        cursor = self.__cursor__
        connection = self.__connection__
        container_class_name = container.__class__.__name__
        contained_class_name = container.__classname__
        hashval = container.__hashval__
        #print('saving',hashval)
        cursor.execute('insert into content values("%s","%s","%s")'%\
            (container_class_name,contained_class_name,hashval))
        connection.commit()
        return False

    def __load_buffer__(self,hashval):
        """ aux method"""
        subdir = hashval[:2]
        remainder = hashval[2:]
        filepath = os.path.join(SETTINGS['REPOSITORY_DIR'],'objects',subdir,remainder)
        if not os.path.isfile(filepath): return None
        with open(filepath) as f:
            return f.read()

    def __save_buffer__(self,container):
        """ aux method"""
        buf = container.__buffer__
        hashval = container.__hashval__
        subdir = hashval[:2]
        remainder = hashval[2:]
        dirpath = os.path.join(SETTINGS['REPOSITORY_DIR'],'objects',subdir)
        os.makedirs(dirpath,exist_ok=True)
        filepath = os.path.join(dirpath,remainder)
        #with open(filepath,'wb') as f:
        with open(filepath,'w') as f:
            f.write(buf)

    def exists(self,hashval):
        row = self.__load_header__(hashval)
        return row != None
    
    def search(self,hashval):
        row = self.__load_header__(hashval)
        if row is None:
            #raise Exception('cannot find container %s in local database'%hashval)
            return None
        container_class_name = row['container_class']
        contained_class_name = row['contained_class']
        registry_item = Container.__registry__[contained_class_name]
        container_class = registry_item['child_class']
        con = container_class()
        con.__classname__ = contained_class_name
        con.__buffer__ = self.__load_buffer__(hashval)
        con.__hashval__ = row['hashval']
        return con
        
    def insert(self,container):
        exists = self.__save_header__(container)
        if not exists: self.__save_buffer__(container)
            
    def tabulate(self,where=None,limit=20,offset=0): 
        if where: where = 'where '+where
        col = j.Collection()
        col.order = ['container_class','contained_class','hashval']
        cursor = self.__cursor__
        cursor.execute(
            'select * from content %s limit %d offset %d'%(where,limit,offset)
        )
        rows = cursor.fetchall()
        col.update([dict(row) for row in rows])
        col.tabulate()
        
    def select(self,fields=['container_class','contained_class','hashval'],
            where=None,group_by=None,having=None,order_by=None,limit=None,offset=None):
        col = j.Collection()
        fields_ = [s[9:] if s[:8]=='distinct' else s for s in fields]
        col.order = fields_
        sql = 'select %s from content'%(','.join(fields))
        if where: sql += ' where '+where
        if group_by: sql += ' group by '+group_by
        if having: sql += ' having '+having
        if order_by: sql += ' order by '+order_by
        if limit is not None: sql += ' limit %d'%limit
        if offset is not None: sql += ' offset %d'%offset
        #print(sql)
        cursor = self.__cursor__
        cursor.execute(sql)
        rows = cursor.fetchall()
        col.update([dict(row) for row in rows])
        return col
        
    def drop(self):
        # drop content table
        cursor = self.__cursor__
        connection = self.__connection__
        dbfile = self.__dbfile__
        print('deleting from content table')
        cursor.execute('delete from content')
        connection.commit()
        # delete the contents of the filetree
        nodes = os.listdir(SETTINGS['REPOSITORY_DIR'])
        for node in nodes:
            if node==dbfile: continue
            path = os.path.join(SETTINGS['REPOSITORY_DIR'],node)
            if os.path.isfile(path):
                print('removing file',path)
                os.remove(path)
            elif os.path.isdir(path):
                print('removing dir',path)
                shutil.rmtree(path)

db_backend = SQLiteBackend()

class ContainerGraph:
    """ Graph for deducing the connections between just-created containers.
        Graph nodes are identified by Python IDs of containers and contained object.
        This is done to make the container graph as lighweight as possible, and 
        to not interfere with the internal Python's garbage collector. """
        
    def __init__(self):
        connection = sqlite3.connect(':memory:')
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        self.__connection__ = connection
        self.__cursor__ = cursor
        self.__cache__ = {}
        # create container-to-object table with indexes
        cursor.execute(
            'create table container_to_object('
                'container_id integer, '
                'object_id integer, '
                'saved_flag int default 0, '
                'primary key (container_id,object_id)'
            ')'
        )
        cursor.execute('create index i1 on container_to_object(container_id)')
        cursor.execute('create index i2 on container_to_object(object_id)')
        # create object-to-object directed graph with indexes
        cursor.execute(
            'create table object_to_object('
                'object_id_from integer, '
                'object_id_to integer'
            ')'
        )
        cursor.execute('create index i3 on object_to_object(object_id_from)')
        cursor.execute('create index i4 on object_to_object(object_id_to)')
    
    def clear_cache(self):
        self.__cache__ = {}
        
    def add_node(self,con):
        cursor = self.__cursor__
        #print('INSERTING NODE: ',con)
        cursor.execute(
            'insert into container_to_object(container_id,object_id)'
            ' values(%d,%d)'%(id(con),id(con.__object__))
        )
        self.__cache__[id(con)] = con # save container in cache (otherwise garbage collection screwes everything up)
    
    def add_edge(self,obj_from,obj_to):
        cursor = self.__cursor__
        cursor.execute(
            'insert into object_to_object(object_id_from,object_id_to)'
            ' values(%d,%d)'%(id(obj_from),id(obj_to))
        )
    
    def get_object_by_container_id(self,cid):
        cursor = self.__cursor__
        cursor.execute(
            'select object_id from container_to_object'
            ' where container_id=="%d"'%cid
        )
        object_id = cursor.fetchone()[object_id]
        #obj = ctypes.cast(object_id, ctypes.py_object).value
        obj = self.__cache__[object_id]
        return obj
            
    def get_containers_by_object_ids(self,oids):
        if type(oids) is int:
            oids = [oids]
        cursor = self.__cursor__
        sql = \
            'select container_id from container_to_object'+\
            ' where object_id in (%s)'%(','.join([str(i) for i in oids]))
        #print('get_containers_by_object_ids:sql>>>',sql)
        cursor.execute(sql)
        #cursor.execute(
        #    'select container_id from container_to_object'
        #    ' where object_id in (%s)'%(','.join([str(i) for i in oids]))
        #)
        cids = [row['container_id'] for row in cursor.fetchall()]
        containers = [
            #ctypes.cast(cid, ctypes.py_object).value for cid in cids
            self.__cache__[cid] for cid in cids
        ]
        return containers
                
    def mark_nodes_as_saved(self,cids): # container ids on input
        cursor = self.__cursor__
        cursor.execute(
            'update container_to_object set saved_flag=1 '
            'where container_in in (%s)'%(','.join([str(i) for i in cids]))
        )
        
    def get_parent_containers(self,oid): # object ids on input
        """ Get all parent containers of the Referee-type subclasses """
        cursor = self.__cursor__
        cursor.execute(
            'select object_id_from from object_to_object'
            ' where object_id_to==%d'%oid
        )
        oids = [row['object_id_from'] for row in cursor.fetchall()]
        #print('parent oids>>>',oids); print('current oid>>>',oid)
        containers = self.get_containers_by_object_ids(oids)
        return containers

    def get_child_containers(self,oid):
        """ Get all child containers of the Referee-type subclasses """
        cursor = self.__cursor__
        cursor.execute(
            'select object_id_to from object_to_object'
            ' where object_id_from==%d'%oid
        )
        oids = [row['object_id_to'] for row in cursor.fetchall()]
        #print('child oids>>>',oids); print('current oid>>>',oid)
        containers = self.get_containers_by_object_ids(oids)
        return containers

    def tabulate_nodes(self,limit=20,offset=0): # tabulate graph tables
        col = j.Collection()
        col.order = ['container_id','object_id',
            'saved_flag','container','object']
        cursor = self.__cursor__
        cursor.execute(
            'select * from container_to_object limit %d offset %d'%(limit,offset)
        )
        rows = cursor.fetchall()
        #col.update([dict(row) for row in rows])
        for row in rows:
            container_id = row['container_id']
            #container = ctypes.cast(container_id, ctypes.py_object).value
            container = self.__cache__[container_id]
            #print('tabulate_nodes:container>>>',container)
            col.update({
                'container_id':container_id,
                'object_id':row['object_id'],
                'saved_flag':row['saved_flag'],
                'container':container,
                'object':container.object,
            })
        col.tabulate()

    def tabulate_edges(self,limit=20,offset=0): # tabulate graph tables
        col = j.Collection()
        col.order = ['object_id_from','object_id_to']
        cursor = self.__cursor__
        cursor.execute(
            'select * from object_to_object limit %d offset %d'%(limit,offset)
        )
        rows = cursor.fetchall()
        col.update([dict(row) for row in rows])
        col.tabulate()

graph_backend = ContainerGraph()

# simple version of save_graph, doesn't go recursive
#def save_graph(obj):
#    """ Main saving function for objects/containers """
#    
#    # save current container
#    container = Container.create(obj)
#    db_backend.insert(container)
#    
#    # save parent containers
#    #print('get_parent_containers>>>')
#    parents = graph_backend.get_parent_containers(id(obj))
#    for c in parents:
#        db_backend.insert(c)
#    
#    # save child containers
#    #print('get_child_containers>>>')
#    children = graph_backend.get_child_containers(id(obj))
#    for c in children:
#        db_backend.insert(c)

# recursive version of save_graph
def __save_subgraph_rec__(container):
    
    if SETTINGS['DEBUG']: print('__save_subgraph_rec__>>>')
 
    # get contained object
    obj = container.object
    
    # save current container
    db_backend.insert(container)
    
    # save parent containers
    parents = graph_backend.get_parent_containers(id(obj))
    if SETTINGS['DEBUG_SUBGRAPH']: print('Get',container,'parents: ',parents)
    for c in parents:
        lookup = Container.search(c.__hashval__)
        if not lookup:
            if SETTINGS['DEBUG_SUBGRAPH']: print('Recurse into',container,'parent: ',c)
            __save_subgraph_rec__(c)
        else:
            if SETTINGS['DEBUG_SUBGRAPH']: print('Succesfully found',c,'(recursion break)')
    
    # save child containers
    children = graph_backend.get_child_containers(id(obj))
    if SETTINGS['DEBUG_SUBGRAPH']: print('Get',container,'children: ',children)
    for c in children:
        lookup = Container.search(c.__hashval__)
        if not lookup:
            if SETTINGS['DEBUG_SUBGRAPH']: print('Recurse into',container,'child: ',c)
            __save_subgraph_rec__(c)
        else:
            if SETTINGS['DEBUG_SUBGRAPH']: print('Succesfully found',c,'(recursion break)')
    
def save_graph(*objs):
    """ Main saving function for objects/containers """
    if SETTINGS['DEBUG']: print('save_graph>>>')
    for obj in objs:
        container = graph_backend.get_containers_by_object_ids(id(obj))[0]
        __save_subgraph_rec__(container)

class Container(ABC):
    
    __registry__ = {}
    
    def __init__(self,obj=None):
        if SETTINGS['DEBUG']: print('Container.__init__>>>')
        if obj is None:
            return # allow empty init
        assert self.__contained_class__ is obj.__class__
        self.__classname__ = type(obj).__name__
        self.__object__ = obj # temporary link to the unpacked object
        self.__buffer__, self.__hashval__ = self.pack(obj)
        #print('add node: ',self)
        graph_backend.add_node(self) # add object to transient graph
        
    @classmethod
    def register(cls,child_class):
        contained_class = child_class.__contained_class__
        contained_class_name = contained_class.__name__
        cls.__registry__[contained_class_name] = {
            'child_class_name':child_class.__name__,
            'child_class':child_class,
            'contained_class_name':contained_class_name,
            'contained_class':contained_class
        }
        
    @classmethod
    def create(cls,obj):
        if SETTINGS['DEBUG']: print('Container.create>>>')
        obj_type = type(obj)
        if issubclass(obj_type,cls): # return unchanged, if container
            return obj 
        else: # return container, if the type is registered
            registry_item = cls.__registry__[obj_type.__name__]
            child_class = registry_item['child_class']
            if not child_class:
                raise Exception('unregistered type "%s"'%obj_type)
            return child_class(obj)
            
    @classmethod
    def search(cls,hashval,backend=db_backend):
        return backend.search(hashval)
        
    @classmethod
    def save(cls,xs,backend=db_backend):
        backend.insert(xs)
           
    @abstractmethod
    def pack(self,obj):
        """ Serialize object to string buffer.
            Return the tuple (buffer, hash). """
        raise NotImplementedError
    
    @abstractmethod
    def unpack(self):
        """ Return unpacked object """
        raise NotImplementedError
        
    def pretty_print(self):
        return self.__hashval__[:5]        
        
    @property
    def object(self):
        if SETTINGS['DEBUG']: print('Container.object>>>',
            self,self.__classname__,self.__dict__.get('__object__').__class__.__name__)
        if '__object__' not in self.__dict__:
            if SETTINGS['DEBUG']: print("'__object__' not in self.__dict__")
            self.__object__ = self.unpack()
        return self.__object__
        
    def __hash__(self):
        return int(self.__hashval__,16)
        
    def __eq__(self,other):
        return self.__hash__() == other.__hash__()
        
    def __str__(self):
        return self.__hashval__
        
    def __repr__(self):
        return self.__hashval__

class Decorator:
    """ Parser for decorators  """
    def __init__(self,decor_string):
        if SETTINGS['DEBUG']: print('Decorator.__init__>>>')
        regex = '@([a-zA-Z][a-zA-Z0-9]*)(\(.+\))*'
        # get name and argstring
        name,argstring = re.search(regex,decor_string).groups()
        self.name = name
        # get args and kwargs
        args = []
        kwargs = []
        if argstring is not None:
            argstring = re.search('\((.+)\)',argstring).group(1)
            argbufs = argstring.split(',')
            for argbuf in argbufs:
                argbuf = argbuf.strip()
                vv = [v.strip() for v in argbuf.split('=')]
                if len(vv)==1:
                    args.append(argbuf)
                elif len(vv)==2:
                    kwargs.append(argbuf)
                else:
                    raise Exception('parse error')
        self.args = args
        self.kwargs = kwargs

def strip_decorators(source):
    if SETTINGS['DEBUG']: print('strip_decorators>>>')
    index = source.find("def ")
    decors = [
        line.strip().split()[0]
        for line in source[:index].strip().splitlines()
        if line.strip()[0] == "@"
    ]
    body = source[index:]
    decorators = []
    for decor_string in decors:
        decorators.append(Decorator(decor_string))
    return decorators,body

def create_module(name,code=''):
    if SETTINGS['DEBUG']: print('create_module>>>')
    module = types.ModuleType(name)
    exec(code, module.__dict__)
    return module

def import_module_by_path(module_name,module_path):
    if SETTINGS['DEBUG']: print('import_module_by_path>>>')
    # https://www.geeksforgeeks.org/how-to-import-a-python-module-given-the-full-path/
    # https://stackoverflow.com/questions/67631/how-do-i-import-a-module-given-the-full-path
    #print(module_name,module_path)
    #print(os.path.isfile(os.path.join(module_path,module_name)))
    #import importlib.util
    spec=importlib.util.spec_from_file_location(module_name,module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module # dill/pickle doesn't work without this line
    spec.loader.exec_module(module)
    # ALTERNATIVE:
    #import importlib.machinery, importlib.util
    #loader = importlib.machinery.SourceFileLoader(module_name, file_path)
    #spec = importlib.util.spec_from_file_location(module_name, loader=loader)
    #module = importlib.util.module_from_spec(spec)
    #spec.loader.exec_module(module)
    return module

class EncapsulatedFunction_BAK:
    """
    Class for converting normal Python functions
    to the "encapsulated" ones to try and avoid hidden side-effects.
    """

    def __init__(self,func=None):
        
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.__init__>>>')
    
        if func is not None:
            
            src = inspect.getsource(func)
            src_ = textwrap.dedent(src)
            
            msg = 'currenlty only one decorator '+\
                'is allowed: track'
            
            decorators,body = strip_decorators(src_)
            if len(decorators)==0:
                pass
            elif len(decorators)==1:
                decorator = decorators[0]
                decor_value = eval(decorator.name)
                if decor_value is not track:
                    raise Exception(msg)
            elif len(decorators)>1:
                raise Exception(msg)

            _tracking = getattr(func,'_tracking',
                {'tracking_args':[],'tracking_kwargs':{}})
            self.tracked = '_tracking' in func.__dict__              
            self.tracking_args = _tracking['tracking_args']
            self.tracking_kwargs = _tracking['tracking_kwargs']

            module_name = self.generate_module_name()
            self.__module_name__ = module_name
            self.__module__ = create_module(module_name,body)
            self.__name__ = func.__name__
            self.__body__ = body
            self.__func__ = self.apply_decorator()
        else:
            self.tracked = None
            self.tracking_args = []
            self.tracking_kwargs = {}
            self.__module_name__ = None
            self.__module__ = None
            self.__name__ = None
            self.__body__ = None
            self.__func__ = None
                     
    """ # OBSOLETE
    @classmethod
    def load(cls,buffer):
        funcdict = load_from_string(buffer)
        body = funcdict['source']
        name = funcdict['name']
        obj = cls()
        obj.tracked = funcdict['tracked']
        obj.tracking_args = funcdict.get('tracking_args',[])
        obj.tracking_kwargs = funcdict.get('tracking_kwargs',[])
        module_name = obj.generate_module_name()
        obj.__module_name__ = module_name
        obj.__module__ = create_module(module_name,body)
        obj.__name__ = name
        obj.__body__ = body
        obj.__func__ = obj.apply_decorator()
        return obj
    """
        
    #@classmethod
    #def load_to_module(cls,hashval,buffer):
    #    pass
    
    @classmethod    
    def check_globals(cls,func):   
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.check_globals>>>')    
        if SETTINGS['DEBUG']: dis.dis(func) # show disassembly
        fname = func.__name__
        instructions = dis.get_instructions(func)
        for i in instructions:
            opname = i.opname.upper()
            argval = i.argval
            #print(opname)
            if opname in {'LOAD_GLOBAL','LOAD_DEREF','LOAD_CLOSURE'}:
                if argval==fname: continue
                raise Exception(
                    'EncapsulatedFunction "%s" is using '
                    'global variable "%s" (%s)'%(fname,argval,opname))
        
    @classmethod
    def load_from_hash(cls,hashval,buffer,apply_decorator=True):
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.load_from_hash>>>')
        # get pathes for module
        subdir = hashval[:2]
        remainder = hashval[2:]
        module_path = os.path.join(SETTINGS['REPOSITORY_DIR'],'objects',subdir)
        module_name = 'mod_'+remainder
        # fill the object's fields
        funcdict = load_from_string(buffer)
        body = funcdict['source']
        name = funcdict['name']
        obj = cls()
        obj.tracked = funcdict['tracked']
        obj.tracking_args = funcdict.get('tracking_args',[])
        obj.tracking_kwargs = funcdict.get('tracking_kwargs',[])
        obj.__module_name__ = module_name
        obj.__name__ = name
        obj.__body__ = body
        # create module path if not existing                    
        if not os.path.exists(module_path):
            os.makedirs(module_path)
        # create module if not existing                    
        filepath = os.path.join(module_path,module_name)+'.py'
        if not os.path.exists(filepath):
            with open(filepath,'w') as f:
                f.write(body)
        # load module and apply decorator
        obj.__module__ = import_module_by_path(module_name,filepath)
        if apply_decorator:
            func = obj.apply_decorator()
        else:
            func = getattr(obj.__module__,name)
        obj.__func__ = func
        return obj

    """
    @classmethod
    def load_from_hash(cls,hashval,buffer):
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.load_from_hash>>>')
        # get pathes for module
        subdir = hashval[:2]
        remainder = hashval[2:]
        module_path = os.path.join(SETTINGS['REPOSITORY_DIR'],'objects',subdir)
        module_name = 'mod_'+remainder
        # fill the object's fields
        funcdict = load_from_string(buffer)
        body = funcdict['source']
        name = funcdict['name']
        obj = cls()
        obj.tracked = funcdict['tracked']
        obj.tracking_args = funcdict.get('tracking_args',[])
        obj.tracking_kwargs = funcdict.get('tracking_kwargs',[])
        obj.__module_name__ = module_name
        obj.__name__ = name
        obj.__body__ = body
        # create module path if not existing                    
        if not os.path.exists(module_path):
            os.makedirs(module_path)
        # create module if not existing                    
        filepath = os.path.join(module_path,module_name)+'.py'
        if not os.path.exists(filepath):
            with open(filepath,'w') as f:
                f.write(body)
        # load module and apply decorator
        obj.__module__ = import_module_by_path(module_name,filepath)
        obj.__func__ = obj.apply_decorator()
        return obj
    """

    def dump(self):
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.dump>>>')
        funcdict = {
            'source': self.__body__,
            'name': self.__name__,
            'tracked': self.tracked,
        }
        if self.tracked:
            funcdict['tracking_args'] = self.tracking_args
            funcdict['tracking_kwargs'] = self.tracking_kwargs
        buffer = dump_to_string(funcdict,sort_keys=True)
        return buffer
        
    def generate_module_name(self):
        return 'tmpmodule'
        
    def apply_decorator(self):
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.apply_decorator>>>')
        funcname = self.__name__
        module = self.__module__
        function = getattr(module,funcname)
        if self.tracked:
            args = self.tracking_args
            kwargs = self.tracking_kwargs
            function = track(*args,**kwargs)(function)
        return function
        
    def __call__(self,*args,**kwargs):
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.__call__>>>')
        return self.__func__(*args,**kwargs)

class EncapsulatedFunction:
    """
    Class for converting normal Python functions
    to the "encapsulated" ones to try and avoid hidden side-effects.
    """

    def __init__(self,func=None):
        
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.__init__>>>')
    
        if func is not None:
            
            src = inspect.getsource(func)
            src_ = textwrap.dedent(src)
            
            msg = 'currenlty no decorators are allowed '+\
                'for both tracked and untracked functions'
            
            decorators,body = strip_decorators(src_)
            if len(decorators)==0:
                pass
            elif len(decorators)==1:
                decorator = decorators[0]
                decor_value = eval(decorator.name)
                if decor_value is not track:
                    raise Exception(msg)
            elif len(decorators)>1:
                raise Exception(msg)
                
            module_name = self.generate_module_name()
            self.__module_name__ = module_name
            self.__module__ = create_module(module_name,body)
            self.__name__ = func.__name__
            self.__body__ = body
            self.__func__ = self.invoke()
        else:
            self.__module_name__ = None
            self.__module__ = None
            self.__name__ = None
            self.__body__ = None
            self.__func__ = None
        self.__funcdict__ = None # to be reused by child classes

    @classmethod    
    def check_globals(cls,func):   
        if SETTINGS['DEBUG']: print('%s.check_globals>>>'%cls.__name__)    
        if SETTINGS['DEBUG']: dis.dis(func) # show disassembly
        fname = func.__name__
        instructions = dis.get_instructions(func)
        for i in instructions:
            opname = i.opname.upper()
            argval = i.argval
            #print(opname)
            if opname in {'LOAD_GLOBAL','LOAD_DEREF','LOAD_CLOSURE'}:
                if argval==fname: continue
                raise Exception(
                    'EncapsulatedFunction "%s" is using '
                    'global variable "%s" (%s)'%(fname,argval,opname))
        
    @classmethod
    def load_from_hash(cls,hashval,buffer):
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.load_from_hash>>>')
        # get pathes for module
        subdir = hashval[:2]
        remainder = hashval[2:]
        module_path = os.path.join(SETTINGS['REPOSITORY_DIR'],'objects',subdir)
        module_name = 'mod_'+remainder
        # fill the object's fields
        funcdict = load_from_string(buffer)
        body = funcdict['source']
        name = funcdict['name']
        obj = cls()
        obj.__funcdict__ = funcdict
        obj.__module_name__ = module_name
        obj.__name__ = name
        obj.__body__ = body
        # create module path if not existing                    
        if not os.path.exists(module_path):
            os.makedirs(module_path)
        # create module if not existing                    
        filepath = os.path.join(module_path,module_name)+'.py'
        if not os.path.exists(filepath):
            with open(filepath,'w') as f:
                f.write(body)
        # load module and apply decorator
        obj.__module__ = import_module_by_path(module_name,filepath)
        obj.__func__ = getattr(obj.__module__,name)
        return obj

    def dump(self):
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.dump>>>')
        funcdict = {
            'source': self.__body__,
            'name': self.__name__,
        }
        buffer = dump_to_string(funcdict,sort_keys=True)
        return buffer
        
    def generate_module_name(self):
        return 'tmpmodule'
    
    def invoke(self): # former apply_decorator
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.invoke>>>')
        funcname = self.__name__
        module = self.__module__
        function = getattr(module,funcname)
        return function
    
    def __call__(self,*args,**kwargs):
        if SETTINGS['DEBUG']: print('EncapsulatedFunction.__call__>>>')
        return self.__func__(*args,**kwargs)        

class Container_function_BAK3(Container):
#class Container_function(Container):
    
    __contained_class__ = (lambda:None).__class__

    def pack(self,obj):
        if SETTINGS['DEBUG']: print('Container_function.pack>>>')
        encfunc = EncapsulatedFunction(obj)
        buffer = encfunc.dump()
        hashval = calc_hash_str(buffer)
        return buffer, hashval
    
    def unpack(self):
        if SETTINGS['DEBUG']: print('Container_function.unpack>>>')
        hashval = self.__hashval__
        buffer = self.__buffer__
        #encfunc = EncapsulatedFunction.load(self.__buffer__)
        encfunc = EncapsulatedFunction.load_from_hash(hashval,buffer)
        return encfunc.__func__
        
    def pretty_print(self):
        dct = json.loads(self.__buffer__)
        return 'function(%s)'%dct['name']

#class Container_function_BAK2(Container):
class Container_function(Container):
    
    __contained_class__ = (lambda:None).__class__

    def pack(self,obj):
        if SETTINGS['DEBUG']: print('Container_function.pack>>>')
        EncapsulatedFunction.check_globals(obj)
        encfunc = EncapsulatedFunction(obj)
        buffer = encfunc.dump()
        hashval = calc_hash_str(buffer)
        self.__object__ = EncapsulatedFunction.load_from_hash(
            hashval,buffer) # strip off all context
        return buffer, hashval
    
    def unpack(self):
        if SETTINGS['DEBUG']: print('Container_function.unpack>>>')
        hashval = self.__hashval__
        buffer = self.__buffer__
        #encfunc = EncapsulatedFunction.load(self.__buffer__)
        encfunc = EncapsulatedFunction.load_from_hash(hashval,buffer)
        return encfunc.__func__
        
    def pretty_print(self):
        dct = json.loads(self.__buffer__)
        return 'function(%s)'%dct['name']

class Container_function_BAK(Container):
    
    __contained_class__ = (lambda:None).__class__

    def pack(self,obj):
        src = inspect.getsource(obj)
        #src = dill.source.getsource(obj)
        src_ = textwrap.dedent(src)
        funcdict = {
            'source': src_,
            'name': obj.__name__
        }
        buffer = dump_to_string(funcdict,sort_keys=True)
        hashval = calc_hash_str(buffer)
        return buffer, hashval
    
    def unpack(self):
        __funcdict__235237645 = load_from_string(self.__buffer__)
        exec(__funcdict__235237645['source'])
        loc = locals()
        return loc[__funcdict__235237645['name']]
        
    def pretty_print(self):
        dct = json.loads(self.__buffer__)
        return 'function(%s)'%dct['name']

Container.register(Container_function)

class TrackedFunction(EncapsulatedFunction):
    
    def __init__(self,func=None,nout=None,tracking_options=None):
        super().__init__(func)
        if SETTINGS['DEBUG']: print('TrackedFunction.__init__>>>')        
        if tracking_options is None: tracking_options = {}
        self.__tracking_nout__ = nout
        self.__tracking_options__ = tracking_options
    
    def get_tracking_option(self,argname,default_value):
        argval = self.__tracking_options__.get(argname,default_value)
        return argval
    
    def dump(self):
        if SETTINGS['DEBUG']: print('TrackedFunction.dump>>>')
        funcdict = {
            'source': self.__body__,
            'name': self.__name__,
            'tracking_nout': self.__tracking_nout__,
            'tracking_options': self.__tracking_options__,
        }
        buffer = dump_to_string(funcdict,sort_keys=True)
        return buffer
    
    @classmethod
    def load_from_hash(cls,hashval,buffer):
        obj = super(TrackedFunction,cls).load_from_hash(hashval,buffer)
        obj.__tracking_nout__ = obj.__funcdict__['tracking_nout']
        obj.__tracking_options__ = obj.__funcdict__['tracking_options']
        return obj
    
    """
    def __call__(self,*args,**kwargs):
        if SETTINGS['DEBUG']: print('TrackedFunction.__call__>>>')
        nout = self.__tracking_nout__
        autosave = self.get_tracking_option('autosave',False)
        cache = self.get_tracking_option('cache',False)
        w = Workflow(self,args=args,kwargs=kwargs,nout=nout)
        cw = Container.create(w)
        #graph_backend.__cache__[id(w)] = w # save workflow in cache
        res = [output.object for output in w.outputs]
        if len(res)==1: res = res[0]
        if autosave: save_graph(w)
    """
    
    def __call__(self,*args,**kwargs):
        
        # heavy-weighted version of call like in previous Workflow implementation
        
        # ATTENTION: args and kwargs should not be changed within
        # this function, otherwise the all algrythm of creating workflow will break!
        # In other words, the __call__ method should be side effect-free.
        
        if SETTINGS['DEBUG']: print('TrackedFunction.__call__>>>')
        
        # Get tracking options.
        nout = self.__tracking_nout__
        autosave = self.get_tracking_option('autosave',False)
        cache = self.get_tracking_option('cache',False)        
                
        # Create the FunctionCall object and containerize it.
        fcall = FunctionCall(self,args,kwargs)
        cfcall = Container.create(fcall)
        
        # Check if caching is enabled.
        if cache:
            
            # how to cache properly?            
            raise NotImplementedError            
        
        else:            
            
            # run the function from scratch and create a workflow            
            outs = self.__func__(
                *args,
                **kwargs,
            )
            
            if nout==1: 
                outputs = [outs,]
            else:
                outputs = outs
            
            # containerize the outputs
            coutputs = [Container.create(out) for out in outputs]
            
            # create the new Workflow object and containerize it.
            w = Workflow()
            w.add_reference(Reference(container=cfcall),reftype='fcall',meta=None)
            for i,cout in enumerate(coutputs):
                w.add_reference(Reference(container=cout),reftype='output',meta=i)
            cw = Container.create(w)
            
            # Save the new graph if needed.
            if autosave: save_graph(w)
            
        # Return the original output.
        return outs

class Container_TrackedFunction(Container):
    
    __contained_class__ = TrackedFunction

    def pack(self,obj):
        if SETTINGS['DEBUG']: print('Container_TrackedFunction.pack>>>')
        TrackedFunction.check_globals(obj)
        buffer = obj.dump()
        hashval = calc_hash_str(buffer)
        return buffer, hashval
    
    def unpack(self):
        if SETTINGS['DEBUG']: print('Container_TrackedFunction.unpack>>>')
        hashval = self.__hashval__
        buffer = self.__buffer__
        #encfunc = TrackedFunction.load(self.__buffer__)
        encfunc = TrackedFunction.load_from_hash(hashval,buffer)
        return encfunc
        
    def pretty_print(self):
        dct = json.loads(self.__buffer__)
        return 'function(%s)'%dct['name']

Container.register(Container_TrackedFunction)

#class Workflow: # OLD VERSION, INITIALIZED WITH CONTAINERS
#    """
#    --------------------------------------------------
#    LIGHTWEIGHT VERSION OF THE WORKFLOW ("RUN") HEADER
#    --------------------------------------------------
#    """
#    def __init__(self,confunc,conkwargs,conoutput):
#        """
#        confunc - container for function
#        conkwargs - dict of containers for the function inputs
#        conoutput - container for function output
#        """
#        rundict = {}
#        if confunc: rundict['funchash'] = confunc.__hashval__
#        if conkwargs: rundict['kwarghashes'] = \
#            {key:conkwargs[key].__hashval__ for key in conkwargs}
#        if conoutput: rundict['outputhash'] = conoutput.__hashval__
#        self.__rundict__ = rundict
#        
#    def __str__(self):
#        return json.dumps(self.__rundict__,indent=2)
#        
#    def __repr__(self):
#        return json.dumps(self.__rundict__,indent=2)

class Reference:
    """ 
    Class for referencing the container and seamless search for it 
    in the backend database.
    """
    def __init__(self,hashval=None,container=None,db_backend=db_backend):
        if hashval is not None and container is not None:
            assert container.__hashval__==hashval
        self.__db_backend__ = db_backend
        self.__container__ = container
        if container is not None:            
            self.__hashval__ = container.__hashval__
        else:
            self.__hashval__ = hashval
        
    @property
    def container(self):
        hashval = self.__hashval__
        if self.__container__ is None:
            self.__container__ = self.__db_backend__.search(hashval)
        return self.__container__
        
    def __repr__(self):
        #return 'Ref<%s>'%self.__hashval__
        return self.__hashval__
        
class Referee:
    """ 
    Parent class for unifying the referecnes to containers. 
    Needed for quick assembly of the graph networks.
    """
    
    def add_reference(self,ref,reftype=None,meta=None):
        if '__references__' not in self.__dict__:
            self.__references__ = j.Collection()
        refs = self.__references__
        refs.order = ['reference','reftype','meta']
        refs.update({
            'reference': ref,
            'reftype': reftype,
            'meta': meta,
        })
        self.__reftype_index__ = refs.group(lambda v:v['reftype'])
        # add objects to transient graph
        #print('REFEREE: obj_from',self,'obj_to',ref.__container__.__object__)
        graph_backend.add_edge(
            obj_from=self,obj_to=ref.__container__.__object__) 
        
    def get_references(self,reftype=None,filter='True'):
        """ Return a Reference objects """
        refs = self.__references__
        if '__reftype_index__' not in self.__dict__:
            self.__reftype_index__ = refs.group(lambda v:v['reftype'])
        reftype_idx = self.__reftype_index__
        if reftype is None:
            ids = refs.ids(filter)
        else:
            ids = refs.subset(IDs=reftype_idx.get(reftype,[])).ids(filter)
        return refs.subset(ids)
        
    @classmethod
    def refs_to_dict(cls,refs):
        dct = {}
        for id_ in refs.__dicthash__:
            ref = refs.__dicthash__[id_]
            dct[id_] = {
                'reference':ref['reference'].__hashval__,
                'reftype':ref['reftype'],
                'meta':ref['meta'],
            }
        return dct
        
    @classmethod
    def refs_from_dict(cls,dct):
        refs = j.Collection()
        refs.order = ['reference','reftype','meta']
        dicthash = refs.__dicthash__
        for id_ in dct:
            item = dct[id_]
            hashval = item['reference']
            dicthash[id_] = {
                'reference':Reference(hashval=hashval),
                'reftype':item['reftype'],
                'meta':item['meta'],
            }
        return refs

    @property
    def references(self):
        return self.__references__
        
    def __repr__(self):
        tab = self.references.tabulate(raw=True)
        return '<<<< %s >>>>:\n%s'%(self.__class__.__name__,tab)

class FunctionCall(Referee):
    
    def __init__(self,func=None,args=[],kwargs={}):

        if SETTINGS['DEBUG']: print('FunctionCall.__init__>>>')
        
        # Convert input arguments to containers
        func = Container.create(func) if func else None
        args = [Container.create(arg) for arg in args]
        kwargs = {kwarg:Container.create(kwargs[kwarg]) \
            for kwarg in kwargs}
        
        # setup ref for function
        if func: self.add_reference(Reference(container=func),reftype='function',meta=None)
        
        # setup refs for args
        for i,arg in enumerate(args):
            self.add_reference(Reference(container=arg),reftype='arg',meta=i)
        
        # setup refs for kwargs
        for key in kwargs:
            kwarg = kwargs[key]
            self.add_reference(Reference(container=kwarg),reftype='kwarg',meta=key)
                
    @property
    def function(self):
        return self.get_references('function').getcol('reference')[0].container
        
    @property
    def args(self):    
        refs = self.get_references('arg') 
        return [ref.container for ref in refs.getcol('reference',IDs=refs.sort('meta'))]

    @property
    def kwargs(self):
        refs = self.get_references('kwarg')
        dct = {}
        for key,ref in zip(*refs.getcols(['meta','reference'])):
            dct[key] = ref.container
        return dct

# this can be merged with Container_Workflow in the next refactor since they do the same thing
class Container_FunctionCall(Container):
    
    __contained_class__ = FunctionCall
    
    def pack(self,obj):
        if SETTINGS['DEBUG']: print('Container_FunctionCall.pack>>>')
        refs = obj.references
        dct = {'refs':Referee.refs_to_dict(refs)}
        buffer = dump_to_string(dct)
        hashval = calc_hash_dict(dct)
        return buffer, hashval
    
    def unpack(self):
        if SETTINGS['DEBUG']: print('Container_FunctionCall.unpack>>>')
        dct = load_from_string(self.__buffer__)
        w = FunctionCall()
        w.__references__ = Referee.refs_from_dict(dct['refs'])
        return w

Container.register(Container_FunctionCall)

class Workflow(Referee):
    
    def __init__(self,fcall=None,outputs=[]):
        
        # Convert input arguments to containers
        fcall = Container.create(fcall) if fcall else None
        outputs = [Container.create(out) for out in outputs]
        
        # setup ref for function call
        if fcall: self.add_reference(Reference(container=fcall),reftype='fcall',meta=None)
        
        # setup refs for outputs
        for i,out in enumerate(outputs):
            self.add_reference(Reference(container=out),reftype='output',meta=i)

    @property
    def fcall(self):    
        return self.get_references('fcall').getcol('reference')[0].container
            
    @property
    def outputs(self):    
        refs = self.get_references('output')
        return [ref.container for ref in refs.getcol('reference',IDs=refs.sort('meta'))]
        
    @property
    def function(self):
        return self.fcall.object.function
        
    @property
    def args(self):    
        return self.fcall.object.args

    @property
    def kwargs(self):
        return self.fcall.object.kwargs

class Container_Workflow(Container):
    
    __contained_class__ = Workflow
    
    def pack(self,obj):
        if SETTINGS['DEBUG']: print('Container_Workflow.pack>>>')
        refs = obj.references
        dct = {'refs':Referee.refs_to_dict(refs)}
        buffer = dump_to_string(dct)
        hashval = calc_hash_dict(dct)
        return buffer, hashval
    
    def unpack(self):
        if SETTINGS['DEBUG']: print('Container_Workflow.unpack>>>')
        dct = load_from_string(self.__buffer__)
        w = Workflow()
        w.__references__ = Referee.refs_from_dict(dct['refs'])
        return w

Container.register(Container_Workflow)

class Workflow_BAK(Referee):
    """
    --------------------------------------------------
    HEAVYWEIGHT VERSION OF THE WORKFLOW ("RUN") HEADER
    --------------------------------------------------
    """
    def __init__(self,func=None,args=[],kwargs={},nout=1,cache=True):
        """
        func - function object OR container
        args - positional arguments OR containers
        kwargs - keyword arguments OR container
        nout - number of outputs
        cache - caching flag
        """        
        
        if SETTINGS['DEBUG']: print('Workflow.__init__>>>')
        
        # Convert input arguments to containers
        func = Container.create(func) if func else None
        args = [Container.create(arg) for arg in args]
        kwargs = {kwarg:Container.create(kwargs[kwarg]) \
            for kwarg in kwargs}
        
        # calculate and containerize outputs
        #if func:
        #    argspec = inspect.getfullargspec(func.object)
        #    argnames = argspec.args
        #else:
        #    argnames = []
                                        
        if func:                        
            
            outs = func.object(
                *[arg.object for arg in args],
                **{kwarg:kwargs[kwarg].object for kwarg in kwargs},
            )
            outputs = []
            if nout==1: outs = [outs,]
            for out in outs:
                outputs.append(Container.create(out))        
        else:
            outputs = []
                       
        # setup refs for function
        if func: self.add_reference(Reference(container=func),reftype='function',meta=None)
        
        # setup refs for args
        for i,arg in enumerate(args):
            self.add_reference(Reference(container=arg),reftype='arg',meta=i)
        
        # setup refs for kwargs
        for key in kwargs:
            kwarg = kwargs[key]
            self.add_reference(Reference(container=kwarg),reftype='kwarg',meta=key)
        
        # setup refs for outputs
        for i,out in enumerate(outputs):
            self.add_reference(Reference(container=out),reftype='output',meta=i)
        
    @property
    def function(self):
        return self.get_references('function').getcol('reference')[0].container
        
    @property
    def args(self):    
        refs = self.get_references('arg') 
        return [ref.container for ref in refs.getcol('reference',IDs=refs.sort('meta'))]

    @property
    def kwargs(self):
        refs = self.get_references('kwarg')
        dct = {}
        for key,ref in zip(*refs.getcols(['meta','reference'])):
            dct[key] = ref.container
        return dct

    @property
    def outputs(self):    
        refs = self.get_references('output') 
        return [ref.container for ref in refs.getcol('reference',IDs=refs.sort('meta'))]

class Container_Workflow_BAK(Container):
    
    __contained_class__ = Workflow
    
    def pack(self,obj):
        if SETTINGS['DEBUG']: print('Container_Workflow.pack>>>')
        refs = obj.references
        dct = {'refs':Referee.refs_to_dict(refs)}
        buffer = dump_to_string(dct)
        hashval = calc_hash_dict(dct)
        return buffer, hashval
    
    def unpack(self):
        if SETTINGS['DEBUG']: print('Container_Workflow.unpack>>>')
        dct = load_from_string(self.__buffer__)
        w = Workflow()
        w.__references__ = Referee.refs_from_dict(dct['refs'])
        return w

Container.register(Container_Workflow)

class Tag(Referee):
    """
    Class for tagging arbitrary containers
    """
    
    def __init__(self,obj=None,name=None,meta=None):
        """
        obj - containerizable object / container
        name - tag name
        meta - text/json description
        """
        self.__name__ = name
        if obj is not None:
            obj = Container.create(obj)
            self.add_reference(container=obj,reftype='target',meta=meta)
       
    @property
    def target(self):
        return self.get_references('target').getcol('reference')[0].container
        
    def __repr__(self):
        name = self.__name__
        return name if name != None else ''
    
class Container_Tag(Container):
    
    __contained_class__ = Tag
    
    def pack(self,obj):
        refs = obj.references
        name = obj.__name__
        dct = {'refs':Referee.refs_to_dict(refs),'name':name}
        buffer = dump_to_string(dct)
        hashval = calc_hash_dict(dct)
        return buffer, hashval
    
    def unpack(self):
        dct = load_from_string(self.__buffer__)
        t = Tag()
        t.__name__ = dct['name']
        t.__references__ = Referee.refs_from_dict(dct['refs'])
        return t

Container.register(Container_Tag)

class Container_Number(Container):

    def pack(self,obj):
        buffer = dump_to_string(obj)
        hashval = calc_hash_str(buffer)
        return buffer, hashval
    
    def unpack(self):
        return load_from_string(self.__buffer__)

class Container_int(Container_Number):
    __contained_class__ = int
Container.register(Container_int)

class Container_int32(Container_Number):
    __contained_class__ = np.int32
Container.register(Container_int32)

class Container_float(Container_Number):
    __contained_class__ = float
Container.register(Container_float)

class Container_float64(Container_Number):   
    __contained_class__ = np.float64
Container.register(Container_float64)

class Container_NoneType(Container_Number):   
    __contained_class__ = type(None)
Container.register(Container_NoneType)

class Container_str(Container):
    
    __contained_class__ = str

    def pack(self,obj):
        buffer = obj
        hashval = calc_hash_str(buffer)
        return buffer, hashval
    
    def unpack(self):
        return self.__buffer__

Container.register(Container_str)

def pack_ndarray(obj):
    """ Pack Numpy ndarray object and return buffer and hash. """
    f = io.BytesIO()
    np.save(f,obj)
    #binbuf = archlib.compress(f.getvalue())
    binbuf = f.getvalue() # no compression, faster + no space overhead
    buffer = binascii.hexlify(binbuf).decode(SETTINGS['ENCODING']) # slow
    #buffer = binbuf
    hashval = calc_hash_bin(binbuf)
    return buffer, hashval

def unpack_ndarray(buffer):
    """ Extract Numpy ndarray from string buffer. """
    binbuf = binascii.unhexlify(buffer) # slow
    #binbuf = self.__buffer__
    #return np.load(io.BytesIO(archlib.decompress(binbuf)))
    return np.load(io.BytesIO(binbuf)) # no compression, faster + no space overhead

class Container_ndarray(Container):
    
    __contained_class__ = np.ndarray
    
    def pack(self,obj):
        return pack_ndarray(obj)
    
    def unpack(self):        
        return unpack_ndarray(self.__buffer__)
        
    def pretty_print(self):
        ar = self.object
        return 'ndarray(%d elements)'%np.mul(ar.shape)

Container.register(Container_ndarray)

class Container_list(Container):
    
    __contained_class__ = list

    def pack(self,obj):
        buffer = dump_to_string(obj)
        hashval = calc_hash_list(obj)
        return buffer, hashval
    
    def unpack(self):
        return load_from_string(self.__buffer__)
        
    def pretty_print(self):
        lst = self.object
        return 'list(%d elements)'%len(lst)

Container.register(Container_list)

class Container_tuple(Container):
    
    __contained_class__ = tuple

    def pack(self,obj):
        buffer = dump_to_string(obj)
        hashval = calc_hash_list(obj)
        return buffer, hashval
    
    def unpack(self):
        return tuple(load_from_string(self.__buffer__))

    def pretty_print(self):
        tup = self.object
        return 'tuple(%d elements)'%len(tup)

Container.register(Container_tuple)

class Container_dict(Container):
    
    __contained_class__ = dict

    def pack(self,obj):
        buffer = dump_to_string(obj)
        hashval = calc_hash_dict(obj)
        return buffer, hashval
    
    def unpack(self):
        return load_from_string(self.__buffer__)

    def pretty_print(self):
        dct = self.object
        return 'dict(%d elements)'%len(dct)

Container.register(Container_dict)

#class Container_list_flat(Container):
#    __contained_class__ = list
#Container.register(Container_list_flat)

#class Container_tuple_flat(Container):
#    __contained_class__ = tuple
#Container.register(Container_tuple_flat)

#class Container_dict_flat(Container):
#    __contained_class__ = dict
#Container.register(Container_dict_flat)

class Container_Collection(Container):
    
    __contained_class__ = j.Collection

    def pack(self,obj):
        buffer = dump_to_string(obj.__dicthash__,sort_keys=True)
        #hashval = calc_hash_dict(obj.__dicthash__) # slow, but always works
        hashval = calc_hash_str(buffer) # fast, but doesn't work if keys are not comparable
        return buffer, hashval
    
    def unpack(self):
        col = j.Collection()
        col.__dicthash__ = load_from_string(self.__buffer__)
        return col
        
    def pretty_print(self):
        col = self.object
        return str(col)

Container.register(Container_Collection)

class Container_module(Container):
    
    __contained_class__ = type(io)
    
    def pack(self,obj):
        buffer = obj.__name__
        hashval = calc_hash_str(buffer)
        return buffer, hashval
    
    def unpack(self):
        return __import__(self.__buffer__)
        
    def pretty_print(self):
        return 'module(%s)'%self.__buffer__

Container.register(Container_module)
        
# Classes for snapshotting the filesystem (a la Git).

class Container_bytes(Container):
    
    __contained_class__ = bytes
    
    def pack(self,obj):
        raise NotImplementedError
    
    def unpack(self):
        raise NotImplementedError

Container.register(Container_bytes)

class Tree:
    pass

class Container_Tree(Container):
    
    __contained_class__ = Tree
    
    def pack(self,obj):
        raise NotImplementedError
    
    def unpack(self):
        raise NotImplementedError

Container.register(Container_Tree)

def track_BAK(*tracking_args,**tracking_kwargs):
    if SETTINGS['DEBUG']: print('track>>>')
    nout = tracking_kwargs.get('nout')
    if nout is None:
        nout = tracking_args[0]
    autosave = tracking_kwargs.get('autosave',False)
    cache = tracking_kwargs.get('cache',True)
    def inner(foo):
        if SETTINGS['DEBUG']: print('inner>>>')
        def wrapper(*args,**kwargs):
            if SETTINGS['DEBUG']: print('wrapper>>>')
            foo._tracking = {
                'tracking_args':tracking_args,
                'tracking_kwargs':tracking_kwargs
            }
            w = Workflow(foo,args=args,kwargs=kwargs,nout=nout)
            cw = Container.create(w)
            #graph_backend.__cache__[id(w)] = w # save workflow in cache
            res = [output.object for output in w.outputs]
            if len(res)==1: res = res[0]
            if autosave: save_graph(w)
            return res
        return wrapper
    return inner

# provenance decorator
def track(nout,**tracking_options):
    if SETTINGS['DEBUG']: print('track>>>')
    def inner(foo):
        if SETTINGS['DEBUG']: print('inner>>>')
        tfun = TrackedFunction(foo,nout=nout,
            tracking_options=tracking_options,
        )
        return tfun
    return inner

