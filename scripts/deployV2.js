const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying LogIntegrityV2 with account:", deployer.address);

  const balance = await deployer.getBalance();
  console.log("Account balance:", ethers.utils.formatEther(balance), "ETH");

  const LogIntegrityV2 = await ethers.getContractFactory("LogIntegrityV2");
  const contract = await LogIntegrityV2.deploy();
  await contract.deployed();

  console.log("\n✅ LogIntegrityV2 deployed to:", contract.address);
  console.log("   Chain ID: 12345 (logchain)");

  // Save ABI
  const artifactPath = path.join(
    __dirname,
    "../artifacts/contracts/LogIntegrityV2.sol/LogIntegrityV2.json"
  );
  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
  const abiDest = path.join(__dirname, "../LogIntegrityV2_abi.json");
  fs.writeFileSync(abiDest, JSON.stringify(artifact.abi, null, 2));
  console.log("   ABI saved to LogIntegrityV2_abi.json");

  console.log("\n📋 Next step — update CONTRACT_ADDRESS_V2 in Python files:");
  console.log(`   CONTRACT_ADDRESS_V2 = "${contract.address}"`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
