/**
 * EchoLineage V1.0.1 — Studionet deployment + deployed-state certification.
 *
 * Drives genlayer-js directly against GenLayer Studionet (chain 61999).
 * The deployer key is read from a 600-mode file OUTSIDE this repository; it is
 * never written into the repo, never logged, and never shipped anywhere.
 *
 * Usage:
 *   node scripts/deploy-studionet.mjs deploy   [contractPath]
 *   node scripts/deploy-studionet.mjs certify  [contractAddress]
 *
 * Env:
 *   EL_DEPLOYER_KEY_FILE  path to the deployer private key (required)
 *   GENLAYER_NETWORK      network key (default: studionet)
 *   GENLAYER_RPC_URL      RPC override
 *   EL_POLL_SECONDS       finalization poll interval (default 6)
 *   EL_POLL_TIMEOUT_MS    overall timeout (default 15 min)
 */
import fs from "node:fs";
import path from "node:path";
import { createAccount, createClient, chains } from "genlayer-js";

const KEY_FILE = process.env.EL_DEPLOYER_KEY_FILE;
const NETWORK_KEY = process.env.GENLAYER_NETWORK || "studionet";
const CHAIN_MAP = {
  studionet: chains.studionet,
  "testnet-bradbury": chains.testnetBradbury,
  "testnet-asimov": chains.testnetAsimov,
  localnet: chains.localnet,
};
const CHAIN = CHAIN_MAP[NETWORK_KEY];
if (!CHAIN) {
  console.error(`Unknown GENLAYER_NETWORK: ${NETWORK_KEY}`);
  process.exit(1);
}
const RPC_URL = process.env.GENLAYER_RPC_URL || CHAIN.rpcUrls.default.http[0];
const EXPLORER_API =
  process.env.GENLAYER_EXPLORER_API || "https://explorer-studio.genlayer.com/api";
const POLL_SECONDS = Number(process.env.EL_POLL_SECONDS || 6);
const POLL_TIMEOUT_MS = Number(process.env.EL_POLL_TIMEOUT_MS || 15 * 60 * 1000);

const TERMINAL = new Set([
  "FINALIZED",
  "REJECTED",
  "UNDETERMINED",
  "CANCELED",
  "VALIDATORS_TIMEOUT",
  "LEADER_TIMEOUT",
  "DROP",
]);

const log = (...a) => console.log(...a);

async function rpc(method, params = []) {
  const res = await fetch(RPC_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const json = await res.json();
  if (json.error) {
    const err = new Error(`${method}: ${json.error.message}`);
    err.data = json.error.data;
    throw err;
  }
  return json.result;
}

/**
 * Read a deployer key from KEY_FILE.
 *
 * Accepts either a raw hex private key or a JSON object containing one, so a
 * plain 600-mode key file works without being wrapped first.
 */
function readPrivateKey(file) {
  const raw = fs.readFileSync(file, "utf8").trim();
  let candidate = raw;
  if (raw.startsWith("{")) {
    const parsed = JSON.parse(raw);
    candidate = parsed.privateKey ?? parsed.key ?? "";
    if (!candidate) throw new Error(`${file} has JSON but no privateKey field`);
  }
  if (!/^(0x)?[0-9a-fA-F]{64}$/.test(candidate)) {
    // Encrypted Web3 keystores are not usable without a password; say so plainly.
    if (raw.startsWith("{") && /cipher|scrypt|kdf/i.test(raw)) {
      throw new Error(
        `${file} is an ENCRYPTED keystore; an unlocked private key is required`
      );
    }
    throw new Error(`${file} does not contain a 32-byte hex private key`);
  }
  return candidate.startsWith("0x") ? candidate : "0x" + candidate;
}

function makeClients(withSigner) {
  if (withSigner && !KEY_FILE) {
    console.error(
      "EL_DEPLOYER_KEY_FILE is not set. Point it at the deployer key outside this repository."
    );
    process.exit(2);
  }
  let account = null;
  if (withSigner) {
    account = createAccount(readPrivateKey(KEY_FILE));
  }
  const glClient = createClient({
    chain: CHAIN,
    endpoint: RPC_URL,
    ...(account ? { account } : {}),
  });
  return { glClient, address: account?.address ?? null };
}

async function txStatus(txHash) {
  try {
    const tx = await rpc("gen_getTransactionByHash", [txHash]);
    const state = tx?.state ?? tx?.status ?? tx?.finality;
    return typeof state === "object" && state !== null ? state : tx;
  } catch {
    return null;
  }
}

function statusName(tx) {
  if (!tx) return null;
  const s = tx.state ?? tx.status;
  if (typeof s === "string") return s;
  if (s && typeof s === "object") {
    return s.name ?? s.type ?? s.status ?? JSON.stringify(s).slice(0, 80);
  }
  return null;
}

async function waitFinal(txHash) {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let last = null;
  while (Date.now() < deadline) {
    const tx = await txStatus(txHash);
    const name = statusName(tx);
    if (name && name !== last) {
      log(`  status: ${name}`);
      last = name;
    }
    if (name && TERMINAL.has(name)) return name;
    await new Promise((r) => setTimeout(r, POLL_SECONDS * 1000));
  }
  return "TIMEOUT";
}

async function deploymentAddress(txHash) {
  try {
    const r = await rpc("gen_getTransactionReceipt", [txHash]);
    const addr = r?.contractAddress ?? r?.contract_address;
    if (addr) return { address: addr, source: "gen_getTransactionReceipt" };
  } catch {
    /* fall through to the explorer */
  }
  const url = `${EXPLORER_API}/transactions/${txHash}`;
  const res = await fetch(url, { headers: { "User-Agent": "echolineage-deploy/1.0" } });
  if (!res.ok) throw new Error(`explorer returned HTTP ${res.status} for ${txHash}`);
  const body = await res.json();
  const tx = body?.transaction ?? body;
  const addr = tx?.to_address;
  if (!addr) throw new Error("explorer response contained no contract address");
  return { address: addr, source: "studio explorer" };
}

async function cmdDeploy() {
  const contractFile = process.argv[3] || "contracts/EchoLineage.py";
  const code = fs.readFileSync(path.resolve(process.cwd(), contractFile), "utf8");
  const { glClient, address } = makeClients(true);

  log(`network  : ${NETWORK_KEY} (chain ${CHAIN.id})`);
  log(`rpc      : ${RPC_URL}`);
  log(`deployer : ${address}`);
  log(`contract : ${contractFile} (${code.length} bytes)`);

  const res = await glClient.deployContract({ code });
  const txHash = typeof res === "string" ? res : (res.transactionHash ?? res.hash);
  log(`DEPLOY_TX=${txHash}`);

  const status = await waitFinal(txHash);
  log(`FINAL_STATUS=${status}`);
  if (status !== "FINALIZED") throw new Error(`deployment did not finalize (${status})`);

  const { address: contractAddress, source } = await deploymentAddress(txHash);
  const schema = await glClient.getContractSchema(contractAddress);
  const methodCount = Object.keys(schema?.methods ?? {}).length;
  if (methodCount === 0) {
    throw new Error(`address ${contractAddress} reports no methods; refusing to report it`);
  }
  log(`ADDRESS_SOURCE=${source}`);
  log(`SCHEMA_METHODS=${methodCount}`);
  log(`CONTRACT_ADDRESS=${contractAddress}`);
  return contractAddress;
}

async function readRaw(glClient, address, method, args = []) {
  const schema = await glClient.getContractSchema(address);
  const contract = glClient.createContract({ address, abi: schema.abi });
  const fn = contract.methods[method];
  if (!fn) throw new Error(`method ${method} not present in schema`);
  return await fn(...args);
}

async function cmdCertify(target) {
  const address = target || process.env.EL_CONTRACT_ADDRESS;
  if (!address) throw new Error("no contract address given");
  const { glClient } = makeClients(false);
  log(`certifying reads on ${address} @ ${NETWORK_KEY}\n`);

  const version = await readRaw(glClient, address, "get_version");
  log(`get_version        = ${JSON.stringify(version)}`);
  if (version !== "1.0.1") throw new Error(`expected version 1.0.1, got ${version}`);

  const caseCount = await readRaw(glClient, address, "get_case_count");
  log(`get_case_count     = ${caseCount}`);

  if (Number(caseCount) === 0) {
    log("\nno cases on chain yet; view methods needing a case id were not exercised");
    return;
  }
  const first = 0;
  const record = (k, v) => log(`${k.padEnd(21)}= ${JSON.stringify(v)}`);

  record("get_case", await readRaw(glClient, address, "get_case", [first]));
  const caseData = await readRaw(glClient, address, "get_case", [first]);
  const sources = await readRaw(glClient, address, "get_sources", [first]);
  record("get_sources", sources);
  for (let i = 0; i < (caseData.source_count ?? sources.length); i++) {
    record(`get_source[${i}]`, await readRaw(glClient, address, "get_source", [first, i]));
  }
  record("get_relation", await readRaw(glClient, address, "get_relation", [first, 0, 1]));
  record("get_root_count", await readRaw(glClient, address, "get_root_count", [first]));
  record("get_root_group", await readRaw(glClient, address, "get_root_group", [first, 0]));
  record(
    "get_dependency_matrix",
    await readRaw(glClient, address, "get_dependency_matrix", [first])
  );
  record("get_diversity_bps", await readRaw(glClient, address, "get_diversity_bps", [first]));
  record("get_redundancy_bps", await readRaw(glClient, address, "get_redundancy_bps", [first]));
  record(
    "get_classification",
    await readRaw(glClient, address, "get_classification", [first])
  );
}

const cmd = process.argv[2];
if (cmd === "deploy") await cmdDeploy();
else if (cmd === "certify") await cmdCertify(process.argv[3]);
else {
  console.error("usage: node scripts/deploy-studionet.mjs deploy | certify [address]");
  process.exit(1);
}