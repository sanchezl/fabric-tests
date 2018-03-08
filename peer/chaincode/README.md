# Peer Chaincode Command Tests

## Before You Begin

* `GOPATH` must be defined.
* Fabric source code must be located at `${GOPATH}/src/github.com/hyperledger/fabric` in order to provide the example chaincode used in the tests, specifically:
    * `fabric/examples/chaincode/go/chaincode_example02`
    * `fabric/examples/chaincode/java/SimpleSample`

* By default, the tests attempt to use docker images tagged as `latest`, which
  can be built using `make docker`. The default images used are:
  * Docker image tagged `hyperledger/fabric-tools:latest`.
  * Docker image tagged `hyperledger/fabric-orderer:latest`.
  * Docker image tagged `hyperledger/fabric-peer:latest`.

## Run tests

```
behave
```

### Specify Docker Images

Usually the tests will run with Fabric docker images tagged as `latest`. This is
great for testing a locally built Fabric. If for whatever reason, you need to
run against a specific docker tag, define the `fabric-docker-tag` property on
the behave command line when running the tests.

For example:

```
behave --define fabric-docker-tag=x86_64-1.1.0'
```

### Enable Java Chaincode Tests
If the experimental Java chaincode support is enabled, define the `java-cc-enabled` flag to run tests using Java chaincode in addition to the Golang chaincode.

```
behave --define java-cc-enabled
```

### Save logs
```
behave --define save-logs
```

### Save docker containers

```
behave --define do-not-decompose
```
