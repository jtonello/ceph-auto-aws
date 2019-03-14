#
# Copyright (c) 2016, SUSE LLC
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# * Neither the name of ceph-auto-aws nor the names of its contributors may be
# used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
import logging
import os
import pwd

from yaml import safe_load
from pyaml import dump


def get_logged_user():
    user = None
    try:
        user = os.getlogin()
    except:
        pass
    if user is None:
        user = pwd.getpwuid(os.geteuid())[0]
    return user

log = logging.getLogger(__name__)

tree_stanzas = {
    'cluster-definition': {'default': [{'role': 'admin'}], 'type': list},
    'clusters': {'default': {}, 'type': dict},
    'delegates': {'default': 1, 'type': int},
    'keyname': {'default': get_logged_user(), 'type': str},
    'keypairs': {'default': {}, 'type': dict},
    'nametag': {'default': 'handson', 'type': str},
    'region': {'default': {
        'region_str': 'eu-west-1',
        'availability_zone': None
    }, 'type': dict},
    'role-definitions': {'default': {
        'admin': {'last-octet': 10},
        'defaults': {
            'ami-id': None,
            'last-octet': None,
            'node-no': None,
            'replace-from-environment': [],
            'type': 't2.small',
            'user-data': None,
            'volume': None
        },
        'master': {'last-octet': 10},
        'mon1': {'last-octet': 11},
        'mon2': {'last-octet': 12},
        'mon3': {'last-octet': 13},
        'osd': {'last-octet': 14},
        'windows': {'last-octet': 15},
    }, 'type': dict},
    'subnets': {'default': {}, 'type': dict},
    'types': {'default': ['t2.micro', 't2.small', 't2.medium'], 'type': list},
    'vpc': {'default': {}, 'type': dict}
}

role_definition_keys = list(
    tree_stanzas['role-definitions']['default']['defaults'].keys()
)

_cache = {}
_cache_populated = False
_yfn = None


def initialize_internal_buffers():
    global _cache, _cache_populated, _yfn
    _cache = {}
    _cache_populated = False
    _yfn = None


def yaml_file_name(fn=None):
    global _yfn
    if _yfn is None:
        assert fn is not None, "YAML file name not initialized"
    if fn is None:
        return _yfn
    _yfn = fn
    return _yfn


def touch(fname, times=None):
    with open(fname, 'a'):
            os.utime(fname, times)


def load():
    """
        Load yaml tree into cache from yaml file
    """
    global _cache, _cache_populated
    if _cache_populated:
        log.debug("YAML cache already populated")
        return None
    yfn = yaml_file_name()
    log.debug("Loading YAML file {!r}".format(yfn))
    touch(yfn)
    with open(yfn) as f:
        _cache = safe_load(f)
    if _cache is None:
        _cache = {}
    assert type(_cache) is dict, "YAML file is not a mapping"
    _cache_populated = True
    log.info("Loaded yaml tree from {!r}".format(yfn))
    return None


def write():  # pragma: no cover
    global _cache
    yfn = yaml_file_name()
    touch(yfn)
    with open(yfn, 'w') as outfile:
        outfile.write(dump(_cache, vspacing=[1, 0]))
    return None


def stanza_is_present(s):
    global _cache
    assert s in _cache, "No stanza {!r} in YAML file".format(s)


def apply_default(k):
    global _cache
    if k not in _cache or _cache[k] is None:
        _cache[k] = tree_stanzas[k]['default']
        write()
    return None


def check_if_malformed(k):
    global _cache
    t = tree_stanzas[k]['type']
    assert type(_cache[k]) is t, (
           "YAML stanza {!r} is malformed (should be a {!r})".format(k, t))


def stanza_is_sane(k):
    apply_default(k)
    check_if_malformed(k)


def stanza(k, new_val=None):
    global _cache
    load()
    if new_val is not None:
        assert k in tree_stanzas.keys(), (
            "YAML stanza {!r} not permitted".format(k)
        )
        _cache[k] = new_val
        write()
    stanza_is_sane(k)
    return _cache[k]


def probe_yaml():
    for key in tree_stanzas:
        log.info("Probing {!r} stanza".format(key))
        stanza(key)
        if key == 'cluster-definition':
            validate_cluster_definition()
        if key == 'role-definitions':
            validate_role_definitions()
    log.info("YAML tree is sane")


def role_def_valid(role):
    rd = stanza('role-definitions')[role]
    assert type(rd) is dict, (
           "Role definition {!r} is not a mapping".format(role))
    for key in rd:
        log.debug("Considering attribute {!r}".format(key))
        log.debug("Legal values are {!r}".format(role_definition_keys))
        assert key in role_definition_keys, (
               ("Role definition {!r} contains illegal attribute {!r}"
                .format(role, key)))
        val = rd[key]
        if key == 'type':
            assert val in stanza('types'), (
                   ("Illegal type {!r} detected in role definition {!r}"
                    .format(val, role)))
    return True


def validate_role_definitions():
    rd = stanza('role-definitions')
    roles = []
    for role in rd:
        log.debug("Detected definition stanza of role {!r}".format(role))
        roles.append(role)
        role_def = rd[role]
        if role_def is None:
            continue
        assert role_def_valid(role), (
            "Role definition {!r} is invalid".format(role))
    log.info("Detected roles {!r}".format(roles))
    return roles


def role_exists(role):
    return True if role in stanza('role-definitions') else False


def validate_cluster_definition():
    cluster_def = stanza('cluster-definition')
    assert type(cluster_def) is list, (
        "cluster-definition stanza is not a collection"
    )
    log.info("Detected cluster-definition stanza")
    roles = []
    for instance_def in cluster_def:
        log.debug("Considering instance definition {!r}"
                  .format(instance_def))
        assert type(instance_def) is dict, (
               ("Instance definition {!r} is not a mapping"
                .format(instance_def)))
        assert len(instance_def.items()) > 0, "Instance definition is empty"
        assert len(instance_def.items()) < 2, (
               ("Instance definition {!r} contains more than one attribute",
                format(instance_def)))
        log.debug("Instance definition {!r}".format(instance_def.items()))
        (key, val) = list(instance_def.items())[0]
        assert key == 'role', (
               "Instance definition key {!r} is not 'role'".format(key))
        assert type(val) is not None, "Detected missing 'role' attribute"
        assert type(val) is str, (
               "Detected non-string 'role' attribute {!r}".format(type(val)))
        assert val not in roles, (
               ("Detected duplicate role {!r} in cluster definition"
                .format(val)))
        assert val.lower() != "defaults", (
               "Detected bogus role {!r} in cluster definition".format(val))
        log.info("Detected role {!r} in cluster definition".format(val))
        roles.append(val)
        assert role_exists(val), "Role {!r} is undefined".format(val)
    return True
