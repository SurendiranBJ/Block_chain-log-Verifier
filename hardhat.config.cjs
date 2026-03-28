require("@nomiclabs/hardhat-ethers");

module.exports = {
  solidity: "0.8.19",
  networks: {
    logchain: {
      url: "http://10.175.65.210:8545",
      accounts: ["0x9c7bf0754e9b13d38d2b71a69da799f76545991b97918ae1e000f400437d51b2"],
      chainId: 12345
    }
  }
};