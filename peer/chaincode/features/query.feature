Feature: Query chaincode via CLI

Scenario Outline: Query chaincode state via CLI

  Given a fabric peer and orderer
  And a <lang> chaincode is installed via the CLI
  And the chaincode is instantiated via the CLI
  When the chaincode state is queried via the CLI
  Then the expected query result is returned
  When the chaincode state is updated
  And the chaincode state is queried via the CLI
  Then the expected query result is returned

  Examples:
  | lang |
  | go   |
  | java |
