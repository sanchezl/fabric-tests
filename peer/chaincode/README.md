# Peer Chaincode Command Tests

## Before You Begin

* `GOPATH` must be defined.
* Fabric source code must be located at `${GOPATH}/src/github.com/hyperledger/fabric` in order to provide:
  * Native executables (see below).
  * Example chaincode:
    * `fabric/examples/chaincode/go/chaincode_example02`
    * `fabric/examples/chaincode/java/SimpleSample`

  * Sample configuration (`fabric/sampleconfig`).
* The fabric `make native docker` targets must be built in order to create the following:
  * Native `peer` executable.
  * Native `configtxgen` executable.
  * Docker image tagged `hyperledger/fabric-orderer:latest`.
  * Docker image tagged `hyperledger/fabric-peer:latest`.

## Run tests

```
behave
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
