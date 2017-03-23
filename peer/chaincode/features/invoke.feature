Feature: Invoke chaincode via CLI

Scenario Outline: Invoke a chaincode via CLI

  Given a fabric peer and orderer
  And a <lang> chaincode is installed via the CLI
  And the chaincode is instantiated via the CLI
  Then the chaincode is invoked successfully via the CLI

  Examples:
  | lang |
  | go   |
  | java |
