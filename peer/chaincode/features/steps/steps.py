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
import random
import subprocess
import tempfile
import time
import socket

@step(u'a fabric peer and orderer')
def step_impl(context):

    # create network
    context.network_name = 'behave_' + ''.join(random.choice('0123456789') for i in xrange(7))
    context.network_id = subprocess.check_output([
        'docker', 'network', 'create', context.network_name
    ]).strip()

    # create orderer system channel bootstrap block
    orderer_genesis_block = os.path.join(context.scenario_temp_dir, 'genesis.block')
    print('Orderer system channel genesis block will be written to: {0}'.format(orderer_genesis_block))
    configtxgen_env = os.environ.copy()
    configtxgen_env['CONFIGTX_ORDERER_ADDRESSES']='[orderer:7050]'
    configtxgen_env['CONFIGTX_ORDERER_BATCHSIZE_MAXMESSAGECOUNT']='1'
    configtxgen_env['CONFIGTX_ORDERER_BATCHTIMEOUT']='1s'
    try:
        print(subprocess.check_output([
            context.configtxgen_exe,
            '-profile', 'SampleDevModeSolo',
            '-outputBlock', orderer_genesis_block,
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=configtxgen_env))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # start orderer
    context.orderer_container_id = subprocess.check_output([
        'docker', 'run', '-d', '-p', '7050',
        '--expose', '7050',
        '--network', context.network_name,
        '--network-alias', 'orderer',
        '--env', 'ORDERER_GENERAL_LISTENADDRESS=0.0.0.0',
        '--env', 'ORDERER_GENERAL_GENESISMETHOD=file',
        '--env', 'ORDERER_GENERAL_GENESISFILE=/var/private/orderer/genesis.block',
        '--env', 'ORDERER_GENERAL_LOGLEVEL=debug',
        '--volume', '{0}:/var/private/orderer/genesis.block'.format(orderer_genesis_block),
        'hyperledger/fabric-orderer'
    ]).strip()
    context.orderer_address = subprocess.check_output(['docker', 'port', context.orderer_container_id, '7050']).strip()

    # start peer
    context.peer_container_id = subprocess.check_output([
        'docker', 'run', '-d', '-p', '7051',
        '--network', context.network_name,
        '--network-alias', 'vp0',
        '--env', 'CORE_PEER_ADDRESSAUTODETECT=true',
        '--env', 'CORE_PEER_ID=vp0',
        '--env', 'CORE_CHAINCODE_STARTUPTIMEOUT=300s',
        '--env', 'CORE_VM_DOCKER_ATTACHSTDOUT=true',
        '--volume', '/var/run/docker.sock:/var/run/docker.sock',
        'hyperledger/fabric-peer',
        'peer', 'node', 'start', '--logging-level', 'debug', '--orderer', 'orderer:7050',
    ]).strip()
    context.peer_address = subprocess.check_output(['docker', 'port', context.peer_container_id, '7051']).strip()
    time.sleep(1)

    # setup env for peer cli commands
    context.peer_env = os.environ.copy()
    context.peer_env['CORE_PEER_ADDRESS'] = context.peer_address
    context.peer_env['CORE_PEER_MSPCONFIGPATH'] = os.path.join(context.fabric_dir, 'sampleconfig/msp')
    context.peer_env['CORE_PEER_LOCALMSPID'] = 'DEFAULT'

    # create channel creation tx for test channel
    context.channel_id = 'behave' + ''.join(random.choice('0123456789') for i in xrange(7))
    channel_create_tx = os.path.join(context.scenario_temp_dir, context.channel_id + '.tx')
    print(channel_create_tx)
    print('The transaction to create the {0} channel will be written to: {1}'.format(context.channel_id, channel_create_tx))
    try:
        print(subprocess.check_output([
            context.configtxgen_exe,
            '-profile', 'SampleSingleMSPChannel',
            '-channelID', context.channel_id,
            '-outputCreateChannelTx', channel_create_tx,
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=configtxgen_env))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # create channel
    try:
        print(subprocess.check_output([
            context.peer_exe, 'channel', 'create',
            '--logging-level', 'debug',
            '--orderer', context.orderer_address,
            '--channelID', context.channel_id,
            '--file', channel_create_tx,
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=context.peer_env))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # move genesis block to temp dir (so it will get cleanup up when we're done)
    channel_genesis_block = os.path.join(context.scenario_temp_dir, context.channel_id + '.block')
    os.rename(os.path.join(context.fabric_dir, context.channel_id + '.block'), channel_genesis_block)

    # join peer to channel
    try:
        print(subprocess.check_output([
            context.peer_exe, 'channel', 'join',
            '--logging-level', 'debug',
            '--blockpath', channel_genesis_block,
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=context.peer_env))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

@step(r'a (?P<lang>java|go|golang|car) chaincode is installed via the CLI')
def step_impl(context, lang):
    context.chaincode_lang = 'golang' if lang == 'go' else lang
    context.chaincode_id_name = lang + '_cc_' + ''.join(random.choice('0123456789') for i in xrange(7))
    context.chaincode_id_version = '1.0.0.0'
    try:
        print(subprocess.check_output([
            context.peer_exe, 'chaincode', 'install',
            '--logging-level', 'debug',
            '--orderer', context.orderer_address,
            '--name', context.chaincode_id_name,
            '--path', context.sample_chaincode_path[context.chaincode_lang],
            '--version', context.chaincode_id_version,
            '--lang', context.chaincode_lang
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=context.peer_env))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

@step(u'the chaincode is installed on the peer')
def step_impl(context):
    print(subprocess.check_output([
        'docker', 'exec', context.peer_container_id, 'ls', '-l', '/var/hyperledger/production/chaincodes/' + context.chaincode_id_name + '.' + context.chaincode_id_version
    ]))

@step(r'version (?P<version>\S+) of a (?P<lang>java|go|golang|car) chaincode is installed via the CLI')
def step_impl(context, version, lang):
    context.chaincode_lang = 'golang' if lang == 'go' else lang
    context.chaincode_id_name = lang + '_cc_' + ''.join(random.choice('0123456789') for i in xrange(7))
    context.chaincode_id_version = version
    try:
        print(subprocess.check_output([
            context.peer_exe, 'chaincode', 'install',
            '--logging-level', 'debug',
            '--orderer', context.orderer_address,
            '--name', context.chaincode_id_name,
            '--path', context.sample_chaincode_path[context.chaincode_lang],
            '--version', context.chaincode_id_version,
            '--lang', context.chaincode_lang
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=context.peer_env))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

@step(r'installing version (?P<version>\S+) of the same chaincode via the CLI will fail')
def step_impl(context, version):
    assert getattr(context, 'chaincode_id_name', None), 'No chaincode previously installed.'
    context.chaincode_id_version = version
    try:
        print(subprocess.check_output([
            context.peer_exe, 'chaincode', 'install',
            '--logging-level', 'debug',
            '--orderer', context.orderer_address,
            '--name', context.chaincode_id_name,
            '--path', context.sample_chaincode_path[context.chaincode_lang],
            '--version', context.chaincode_id_version,
            '--lang', context.chaincode_lang
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=context.peer_env))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

@step(r'the chaincode (?:can be|is) instantiated via the CLI')
def step_impl(context):
    assert getattr(context, 'chaincode_id_name', None), 'No chaincode previously installed.'
    try:
        print(subprocess.check_output([
            context.peer_exe, 'chaincode', 'instantiate',
            '--logging-level', 'debug',
            '--orderer', context.orderer_address,
            '--channelID', context.channel_id,
            '--name', context.chaincode_id_name,
            '--version', context.chaincode_id_version,
            '--lang', context.chaincode_lang,
            '--ctor', context.sample_chaincode_ctor_args[context.chaincode_lang]
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=context.peer_env))
        context.last_function = 'initialize'
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise
    time.sleep(2)


@step(r'the chaincode is invoked successfully via the CLI')
def step_impl(context):
    assert getattr(context, 'chaincode_id_name', None), 'No chaincode previously installed.'
    time.sleep(2)
    try:
        print(subprocess.check_output([
            context.peer_exe, 'chaincode', 'invoke',
            '--logging-level', 'debug',
            '--orderer', context.orderer_address,
            '--channelID', context.channel_id,
            '--name', context.chaincode_id_name,
            # '--version', context.chaincode_id_version,
            '--ctor', context.sample_chaincode_transfer_args[context.chaincode_lang]
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=context.peer_env))
        context.last_function = 'invoke'
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

@step(r'the chaincode state is queried via the CLI')
def step_impl(context):
    assert getattr(context, 'chaincode_id_name', None), 'No chaincode previously installed.'
    time.sleep(2)
    try:
        query_commmand_output = subprocess.check_output([
            context.peer_exe, 'chaincode', 'query',
            '--logging-level', 'debug',
            '--orderer', context.orderer_address,
            '--channelID', context.channel_id,
            '--name', context.chaincode_id_name,
            '--version', context.chaincode_id_version,
            '--ctor', context.sample_chaincode_query_args[context.chaincode_lang]
        ], cwd=context.fabric_dir, stderr=subprocess.STDOUT, env=context.peer_env)
        context.query_result = get_chaincode_query_result(query_commmand_output)
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

def get_chaincode_query_result(query_commmand_output):
    return [line.split(':',1)[1].strip() for line in query_commmand_output.splitlines() if line.startswith('Query Result:')][0]


@step(r'the expected query result is returned')
def step_impl(context):
    expected_query_result = context.sample_chaincode_query_results[context.chaincode_lang]['after_' + context.last_function]
    assert context.query_result == expected_query_result, "Expected: %s, Actual: %s" % (expected_query_result, context.query_result)

@step(r'the chaincode state is updated')
def step_impl(context):
    context.execute_steps(u'''
        when the chaincode is invoked successfully via the CLI
    ''')
