async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying with account:", deployer.address);

  const balance = await deployer.getBalance();
  console.log("Account balance:", balance.toString());

  const LogIntegrity = await ethers.getContractFactory("LogIntegrity");
  const contract = await LogIntegrity.deploy();
  await contract.deployed();

  console.log("LogIntegrity deployed to:", contract.address);

  const fs = require("fs");
  const artifact = require("../artifacts/contracts/LogIntegrity.sol/LogIntegrity.json");
  fs.writeFileSync(
    "/home/sura/logchain/LogIntegrity_abi.json",
    JSON.stringify(artifact.abi, null, 2)
  );
  console.log("ABI saved to LogIntegrity_abi.json");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
