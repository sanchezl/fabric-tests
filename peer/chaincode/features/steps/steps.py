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
import pyaml
import collections

@step(u'a fabric peer and orderer')
def step_impl(context):

    # generate crypto materials
    secrets_dir = 'secrets'
    crypto_config_yaml = 'crypto-config.yaml'

    with open(os.path.join(context.scenario_temp_dir, crypto_config_yaml), 'w') as crypto_config_stream:
        crypto_config = {
            'OrdererOrgs':[
                {
                    'Name':'OrdererOrg',
                    'Domain':'local',
                    'CA': {'Country':'US','Province':'North Carolina','Locality':'Raleigh'},
                    'Specs': [{'Hostname':'orderer'}]
                }
            ],
            'PeerOrgs':[
                {
                    'Name':'PeerOrg',
                    'Domain':'local',
                    'CA': {'Country':'US','Province':'North Carolina','Locality':'Raleigh'},
                    'Specs': [{'Hostname':'peer'}]
                }
            ]
        }
        pyaml.dump(crypto_config, crypto_config_stream)

    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--volume', '{}:/work'.format(context.scenario_temp_dir),
            '--workdir', '/work',
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'cryptogen', 'generate',
            '--config', crypto_config_yaml,
            '--output', secrets_dir,
        ], cwd=context.scenario_temp_dir, stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # create network
    context.network_name = 'behave_' + ''.join(random.choice('0123456789') for i in xrange(7))
    context.network_id = subprocess.check_output([
        'docker', 'network', 'create', context.network_name
    ]).strip()

    orderer_org_msp_dir = '{0}/ordererOrganizations/{1}/msp'.format(secrets_dir, 'local')
    peer_org_msp_dir = '{0}/peerOrganizations/{1}/msp'.format(secrets_dir, 'local')

    # generate configuration transaction generator input file
    configtx_yaml = 'configtx.yaml'
    with open(os.path.join(context.scenario_temp_dir, configtx_yaml), 'w') as configtx_stream:
        orderer_org = {
            'Name' : 'OrdererOrg',
            'ID' : 'OrdererMSP',
            'MSPDir' : orderer_org_msp_dir,
        }
        peer_org = {
            'Name' : 'PeerOrg',
            'ID' : 'PeerMSP',
            'MSPDir' : peer_org_msp_dir,
            'AnchorPeers' : [{ 'Host':'peer', 'Port':7051 }],
        }
        configtx = {}
        configtx['Organizations'] = [orderer_org, peer_org]
        configtx['Profiles'] = {
            'OrdererSystemChannel': {
                'Orderer': {
                    'OrdererType' : 'solo',
                    'Addresses' : ['orderer:7050'],
                    'BatchTimeout' : '1s',
                    'BatchSize' : {
                        'MaxMessageCount' : '1',
                        'AbsoluteMaxBytes' : '10 MB',
                        'PreferredMaxBytes' : '512 KB'
                    },
                    'MaxChannels' : 0,
                    'Organizations' : [orderer_org],
                },
                'Consortiums' : {
                    'SampleConsortium' : {
                        'Organizations' : [peer_org],
                    }
                }
            },
            'TestChannel' : {
                'Consortium' : 'SampleConsortium',
                'Application' : {
                    'Organizations' : [peer_org],
                },
            }
        }
        pyaml.dump(configtx, configtx_stream)

    # absolute path to secrets directory
    secrets_dir = os.path.join(context.scenario_temp_dir, secrets_dir)

    orderer_msp_dir = '{0}/ordererOrganizations/{1}/orderers/{2}.{1}/msp'.format(secrets_dir, 'local', 'orderer')
    orderer_tls_dir = '{0}/ordererOrganizations/{1}/orderers/{2}.{1}/tls'.format(secrets_dir, 'local', 'orderer')
    context.orderer_org_tlsca_cert_file = '{0}/ordererOrganizations/{1}/tlsca/tlsca.{1}-cert.pem'.format(secrets_dir, 'local')
    context.peer_tls_dir = '{0}/peerOrganizations/{1}/peers/{2}.{1}/tls'.format(secrets_dir, 'local', 'peer')
    context.peer_msp_dir = '{0}/peerOrganizations/{1}/peers/{2}.{1}/msp'.format(secrets_dir, 'local', 'peer')
    context.peer_admin_tls_dir = '{0}/peerOrganizations/{1}/users/{2}@{1}/tls'.format(secrets_dir, 'local', 'Admin')
    context.peer_admin_msp_dir = '{0}/peerOrganizations/{1}/users/{2}@{1}/msp'.format(secrets_dir, 'local', 'Admin')

    # create orderer system channel bootstrap block
    orderer_genesis_block = 'genesis.block'

    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--env', 'FABRIC_CFG_PATH=/work',
            '--volume', '{}:/work'.format(context.scenario_temp_dir),
            '--workdir', '/work',
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'configtxgen',
            '--profile', 'OrdererSystemChannel',
            '--channelID', 'orderer.system.channel',
            '--outputBlock', orderer_genesis_block,
        ], cwd=context.scenario_temp_dir, stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # absolute path need from here on
    orderer_genesis_block = os.path.join(context.scenario_temp_dir, orderer_genesis_block)

    # start orderer
    context.orderer_container_id = subprocess.check_output([
        'docker', 'run',
        '--detach',
        '--publish', '7050',
        '--expose', '7050',
        '--network', context.network_name,
        '--network-alias', 'orderer',
        '--env', 'ORDERER_GENERAL_LISTENADDRESS=0.0.0.0',
        '--env', 'ORDERER_GENERAL_GENESISMETHOD=file',
        '--env', 'ORDERER_GENERAL_GENESISFILE=/run/secrets/genesis.block',
        '--env', 'ORDERER_GENERAL_LOCALMSPDIR=/run/secrets/msp',
        '--env', 'ORDERER_GENERAL_LOCALMSPID=OrdererMSP',
        '--env', 'ORDERER_GENERAL_LOGLEVEL=debug',
        '--env', 'ORDERER_GENERAL_TLS_ENABLED=true',
        '--env', 'ORDERER_GENERAL_TLS_PRIVATEKEY=/run/secrets/tls/server.key',
        '--env', 'ORDERER_GENERAL_TLS_CERTIFICATE=/run/secrets/tls/server.crt',
        '--env', 'ORDERER_GENERAL_TLS_ROOTCAS=[/run/secrets/tls/ca.crt]',
        '--volume', '{}:/run/secrets/genesis.block'.format(orderer_genesis_block),
        '--volume', '{}:/run/secrets/msp'.format(orderer_msp_dir),
        '--volume', '{}:/run/secrets/tls'.format(orderer_tls_dir),
        'hyperledger/fabric-orderer:{}'.format(context.docker_tag['orderer'])
    ], cwd=context.scenario_temp_dir).strip()

    # get exposed orderer port address
    context.orderer_address = subprocess.check_output(['docker', 'port', context.orderer_container_id, '7050']).strip()

    # start peer
    context.peer_container_id = subprocess.check_output([
        'docker', 'run',
        '--detach',
        '--publish', '7051',
        '--network', context.network_name,
        '--network-alias', 'peer',
        '--env', 'CORE_PEER_ADDRESSAUTODETECT=true',
        '--env', 'CORE_PEER_ID=peer',
        '--env', 'CORE_CHAINCODE_STARTUPTIMEOUT=300s',
        '--env', 'CORE_VM_DOCKER_ATTACHSTDOUT=true',
        '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
        '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
        '--env', 'CORE_PEER_TLS_ENABLED=true',
        '--env', 'CORE_PEER_TLS_CERT_FILE=/run/secrets/tls/server.crt',
        '--env', 'CORE_PEER_TLS_KEY_FILE=/run/secrets/tls/server.key',
        '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
        '--volume', '/var/run/docker.sock:/var/run/docker.sock',
        '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
        '--volume', '{0}:/run/secrets/msp'.format(context.peer_msp_dir),
        'hyperledger/fabric-peer:{}'.format(context.docker_tag['peer']),
        'peer', 'node', 'start', '--logging-level', 'debug', '--orderer', 'orderer:7050',
    ]).strip()
    context.peer_address = subprocess.check_output(['docker', 'port', context.peer_container_id, '7051']).strip()
    time.sleep(1)

    # create channel creation tx for test channel
    context.channel_id = 'behave' + ''.join(random.choice('0123456789') for i in xrange(7))
    channel_create_tx = context.channel_id + '.tx'

    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--env', 'FABRIC_CFG_PATH=/work',
            '--volume', '{}:/work'.format(context.scenario_temp_dir),
            '--workdir', '/work',
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'configtxgen',
            '-profile', 'TestChannel',
            '-channelID', context.channel_id,
            '-outputCreateChannelTx', channel_create_tx,
        ], cwd=context.scenario_temp_dir, stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # absolute path need from here on
    channel_create_tx = os.path.join(context.scenario_temp_dir, channel_create_tx)

    # create channel
    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:/run/secrets/tlsca-cert.pem'.format(context.orderer_org_tlsca_cert_file),
            '--volume', '{0}:/run/secrets/channel.tx'.format(channel_create_tx),
            '--volume', '{0}:/work'.format(context.scenario_temp_dir),
            '--workdir', '/work',
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'peer', 'channel', 'create', '--logging-level', 'debug',
            '--channelID', context.channel_id,
            '--file', '/run/secrets/channel.tx',
            '--tls', 'true',
            '--orderer', 'orderer:7050',
            '--cafile', '/run/secrets/tlsca-cert.pem',
        ], cwd=context.scenario_temp_dir, stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # channel genesis block was output to working directory
    channel_genesis_block = os.path.join(context.scenario_temp_dir, context.channel_id + '.block')

    # join peer to channel
    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:/run/secrets/genesis.block'.format(channel_genesis_block),
            'hyperledger/fabric-peer:{}'.format(context.docker_tag['peer']),
            'peer', 'channel', 'join', '--logging-level', 'debug', '--blockpath', '/run/secrets/genesis.block'
        ], stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # generate anchor peers update for channel
    anchorpeers_update_tx = context.channel_id + '-update.tx'
    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--env', 'FABRIC_CFG_PATH=/work',
            '--volume', '{}:/work'.format(context.scenario_temp_dir),
            '--workdir', '/work',
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'configtxgen',
            '--profile', 'TestChannel',
            '--channelID', context.channel_id,
            '--outputAnchorPeersUpdate', anchorpeers_update_tx,
            '--asOrg', 'PeerOrg'
        ], cwd=context.scenario_temp_dir, stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

    # update channel anchor peers
    anchorpeers_update_tx = os.path.join(context.scenario_temp_dir, anchorpeers_update_tx)
    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:/run/secrets/channel-update.tx'.format(anchorpeers_update_tx),
            '--volume', '{0}:/run/secrets/tlsca-cert.pem'.format(context.orderer_org_tlsca_cert_file),
            'hyperledger/fabric-peer:{}'.format(context.docker_tag['peer']),
            'peer', 'channel', 'update', '--logging-level', 'debug',
            '--channelID', context.channel_id,
            '--file', '/run/secrets/channel-update.tx',
            '--tls', 'true',
            '--orderer', 'orderer:7050',
            '--cafile', '/run/secrets/tlsca-cert.pem',
        ], stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

@step(r'a (?P<lang>java|go|golang|car) chaincode is installed via the CLI')
def step_impl(context, lang):
    context.chaincode_lang = 'golang' if lang == 'go' else lang
    context.chaincode_id_name = lang + '_cc_' + ''.join(random.choice('0123456789') for i in xrange(7))
    context.chaincode_id_version = '1.0.0.0'

    if context.chaincode_lang == 'golang':
        context.chaincode_volume_source = context.go_path
        context.chaincode_volume_target = '/run/chaincode'
        context.chaincode_path = context.sample_chaincode_path[context.chaincode_lang]
    else:
        context.chaincode_volume_source = context.sample_chaincode_path[context.chaincode_lang]
        context.chaincode_volume_target = '/run/chaincode'
        context.chaincode_path = '/run/chaincode'

    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--env', 'GOPATH={0}'.format(context.chaincode_volume_target),
            '--volume', '/var/run/docker.sock:/var/run/docker.sock',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:{1}'.format(context.chaincode_volume_source, context.chaincode_volume_target),
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'peer', 'chaincode', 'install', '--logging-level', 'debug',
            '--orderer', 'orderer:7050',
            '--name', context.chaincode_id_name,
            '--path', context.chaincode_path,
            '--version', context.chaincode_id_version,
            '--lang', context.chaincode_lang
        ], stderr=subprocess.STDOUT))
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

    if context.chaincode_lang == 'golang':
        context.chaincode_volume_source = context.go_path
        context.chaincode_volume_target = '/run/chaincode'
        context.chaincode_path = context.sample_chaincode_path[context.chaincode_lang]
    else:
        context.chaincode_volume_source = context.sample_chaincode_path[context.chaincode_lang]
        context.chaincode_volume_target = '/run/chaincode'
        context.chaincode_path = '/run/chaincode'

    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--env', 'GOPATH={0}'.format(context.chaincode_volume_target),
            '--volume', '/var/run/docker.sock:/var/run/docker.sock',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:{1}'.format(context.chaincode_volume_source, context.chaincode_volume_target),
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'peer', 'chaincode', 'install', '--logging-level', 'debug',
            '--orderer', 'orderer:7050',
            '--name', context.chaincode_id_name,
            '--path', context.chaincode_path,
            '--version', context.chaincode_id_version,
            '--lang', context.chaincode_lang
        ], stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

@step(r'installing version (?P<version>\S+) of the same chaincode via the CLI will fail')
def step_impl(context, version):
    assert getattr(context, 'chaincode_id_name', None), 'No chaincode previously installed.'
    context.chaincode_id_version = version
    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--env', 'GOPATH={0}'.format(context.chaincode_volume_target),
            '--volume', '/var/run/docker.sock:/var/run/docker.sock',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:{1}'.format(context.chaincode_volume_source, context.chaincode_volume_target),
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'peer', 'chaincode', 'install', '--logging-level', 'debug',
            '--orderer', 'orderer:7050',
            '--name', context.chaincode_id_name,
            '--path', context.chaincode_path,
            '--version', context.chaincode_id_version,
            '--lang', context.chaincode_lang
        ], stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        print(e.output)
        raise

@step(r'the chaincode (?:can be|is) instantiated via the CLI')
def step_impl(context):
    assert getattr(context, 'chaincode_id_name', None), 'No chaincode previously installed.'
    try:
        print(subprocess.check_output([
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:/run/secrets/tlsca-cert.pem'.format(context.orderer_org_tlsca_cert_file),
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'peer', 'chaincode', 'instantiate', '--logging-level', 'debug',
            '--channelID', context.channel_id,
            '--name', context.chaincode_id_name,
            '--version', context.chaincode_id_version,
            '--lang', context.chaincode_lang,
            '--ctor', context.sample_chaincode_ctor_args[context.chaincode_lang],
            '--orderer', 'orderer:7050',
            '--tls', 'true',
            '--orderer', 'orderer:7050',
            '--cafile', '/run/secrets/tlsca-cert.pem',
        ], stderr=subprocess.STDOUT))
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
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:/run/secrets/tlsca-cert.pem'.format(context.orderer_org_tlsca_cert_file),
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'peer', 'chaincode', 'invoke',
            '--logging-level', 'debug',
            '--channelID', context.channel_id,
            '--name', context.chaincode_id_name,
            '--ctor', context.sample_chaincode_transfer_args[context.chaincode_lang],
            '--orderer', 'orderer:7050',
            '--tls', 'true',
            '--orderer', 'orderer:7050',
            '--cafile', '/run/secrets/tlsca-cert.pem',
        ], stderr=subprocess.STDOUT))
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
            'docker', 'run',
            '--rm',
            '--network', context.network_name,
            '--env', 'CORE_PEER_ADDRESS=peer:7051',
            '--env', 'CORE_PEER_MSPCONFIGPATH=/run/secrets/msp',
            '--env', 'CORE_PEER_LOCALMSPID=PeerMSP',
            '--env', 'CORE_PEER_TLS_ENABLED=true',
            '--env', 'CORE_PEER_TLS_ROOTCERT_FILE=/run/secrets/tls/ca.crt',
            '--volume', '{0}:/run/secrets/tls'.format(context.peer_tls_dir),
            '--volume', '{0}:/run/secrets/msp'.format(context.peer_admin_msp_dir),
            '--volume', '{0}:/run/secrets/tlsca-cert.pem'.format(context.orderer_org_tlsca_cert_file),
            'hyperledger/fabric-tools:{}'.format(context.docker_tag['tools']),
            'peer', 'chaincode', 'query',
            '--logging-level', 'debug',
            '--channelID', context.channel_id,
            '--name', context.chaincode_id_name,
            '--ctor', context.sample_chaincode_query_args[context.chaincode_lang],
            '--orderer', 'orderer:7050',
            '--tls', 'true',
            '--orderer', 'orderer:7050',
            '--cafile', '/run/secrets/tlsca-cert.pem',
        ], stderr=subprocess.STDOUT)
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
