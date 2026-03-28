const hre = require("hardhat");

async function main() {
  const LogIntegrityV2 = await hre.ethers.getContractFactory("LogIntegrityV2");
  console.log("Deploying LogIntegrityV2...");
  const contract = await LogIntegrityV2.deploy();
  await contract.deployed();
  console.log("LogIntegrityV2 deployed to:", contract.address);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
