# Copyright IBM Corp. 2017 All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from behave import *
import os
import re
import subprocess
import tempfile
import time
import sys

# set the default step matcher
use_step_matcher("re")

def before_all(context):
    # set some handy values
    context.go_path = os.environ['GOPATH']
    context.fabric_dir = os.path.join(context.go_path, 'src/github.com/hyperledger/fabric')
    context.peer_exe = os.path.join(context.fabric_dir, 'build/bin/peer')
    context.configtxgen_exe = os.path.join(context.fabric_dir, 'build/bin/configtxgen')
    if sys.platform == 'darwin':
        # on macOS, the typical value of TMPDIR is not accessible to the Docker vm.
        context.temp_dir = tempfile.mkdtemp(dir='/tmp', prefix='behave_')
    else:
        context.temp_dir = tempfile.mkdtemp()
    context.sample_chaincode_path = {
        'golang':'github.com/hyperledger/fabric/examples/chaincode/go/chaincode_example02',
        'java': os.path.join(context.fabric_dir,'examples/chaincode/java/SimpleSample'),
    }
    context.sample_chaincode_ctor_args = {
        'golang':'{"Args":["init", "a", "100", "b", "200"]}',
        'java':'{"Args": ["init", "a", "100", "b", "200"]}'
    }
    context.sample_chaincode_transfer_args = {
        'golang':'{"Args":["invoke", "a", "b", "15"]}',
        'java':'{"Args": ["transfer", "a", "b", "15"]}'
    }
    context.sample_chaincode_query_args = {
        'golang':'{"Args":["query", "a"]}',
        'java':'{"Args": ["query", "a"]}'
    }
    context.sample_chaincode_query_results = {
        'golang': {
            'after_initialize' : '100',
            'after_invoke'     : '85'
        },
        'java': {
            'after_initialize' : '{"Name":"a","Amount":100}',
            'after_invoke'     : '{"Name":"a","Amount":85}'
        }
    }

def before_scenario(context, scenario):
    if not context.config.userdata.getbool('java-cc-enabled'):
        for step in scenario.steps:
            if "java chaincode" in step.name:
                scenario.mark_skipped()
                break
    context.scenario_temp_dir = os.path.join(context.temp_dir, re.sub('\W+', '_', scenario.name).lower())
    os.mkdir(context.scenario_temp_dir)

def after_scenario(context, scenario):
    # collect logs if failure or user specified
    if context.failed or context.config.userdata.getbool('save-logs'):
        dump_container_logs(context, scenario)
    # teardown docker containers & network
    if not context.config.userdata.getbool('do-not-decompose'):
        decompose_test_environment(context, scenario)

def dump_container_logs(context, scenario):
    # wait a few seconds to let any lat minute blocks make thier way
    time.sleep(2)
    # dump peer logs
    if getattr(context, 'peer_container_id', None):
        open(re.sub('\W+', '_', scenario.name).lower() + '_peer.log', 'w').write(subprocess.check_output(['docker', 'logs', context.peer_container_id], stderr=subprocess.STDOUT))
    # dump orderer logs
    if getattr(context, 'orderer_container_id', None):
        open(re.sub('\W+', '_', scenario.name).lower() + '_orderer.log', 'w').write(subprocess.check_output(['docker', 'logs', context.orderer_container_id], stderr=subprocess.STDOUT))

def decompose_test_environment(context, scenario):
    # destroy peer container
    if getattr(context, 'peer_container_id', None):
        subprocess.check_output(['docker', 'rm', '--force', '--volumes', context.peer_container_id], stderr=subprocess.STDOUT)
    # destroy orderer container
    if getattr(context, 'orderer_container_id', None):
        subprocess.check_output(['docker', 'rm', '--force', '--volumes', context.orderer_container_id], stderr=subprocess.STDOUT)
    # destroy docker network
    if getattr(context, 'network_id', None):
        subprocess.check_output(['docker', 'network', 'rm', context.network_id], stderr=subprocess.STDOUT)
