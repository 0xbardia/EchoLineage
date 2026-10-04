/**
 * EchoLineage V1.0.1 — one real `analyze` write on Studionet.
 *
 * Runs the consensus write against a deployed contract with safe public HTTPS
 * sources, waits for FINALIZED, and prints the case id plus every read needed
 * for the deployed identity check.
 *
 * Usage:
 *   node scripts/analyze-studionet.mjs <contractAddress> "<claim>" '<urlsJson>'
 */
import fs from "node:fs";
import path from "node:path";
import { createAccount, createClient, chains } from "genlayer-js";

const KEY_FILE = process.env.EL_DEPLOYER_KEY_FILE;
const RPC_URL = process.env.GENLAYER_RPC_URL || chains.studionet.rpcUrls.default.http[0];
const POLL_SECONDS = Number(process.env.EL_POLL_SECONDS || 6);
const POLL_TIMEOUT_MS = Number(process.env.EL_POLL_TIMEOUT_MS || 20 * 60 * 1000);

const EXPLORER_API =
  process.env.GENLAYER_EXPLORER_API || "https://explorer-studio.genlayer.com/api";

/**
 * Read a transaction's status.
 *
 * Prefers the node's gen_ method, then falls back to the Studio explorer: the
 * node's gen_* surface is quota-limited (5000/day, shared) while the explorer
 * is not, and a deployment/analyze must still be confirmable when the quota is
 * exhausted.
 */
async function readStatus(txHash) {
  try {
    const tx = await rpc("gen_getTransactionByHash", [txHash]);
    if (tx) return tx;
  } catch {
    /* fall through to the explorer */
  }
  try {
    const res = await fetch(`${EXPLORER_API}/transactions/${txHash}`, {
      headers: { "User-Agent": "echolineage-analyze/1.0" },
    });
    if (!res.ok) return null;
    const body = await res.json();
    return body?.transaction ?? body ?? null;
  } catch {
    return null;
  }
}

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
  const j = await res.json();
  if (j.error) {
    const e = new Error(`${method}: ${j.error.message}`);
    e.data = j.error.data;
    throw e;
  }
  return j.result;
}

function statusName(tx) {
  if (!tx) return null;
  const s = tx.state ?? tx.status;
  if (typeof s === "string") return s;
  if (s && typeof s === "object") return s.name ?? s.type ?? JSON.stringify(s).slice(0, 120);
  return null;
}

async function waitFinal(txHash) {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let last = null;
  while (Date.now() < deadline) {
    let tx = null;
    try {
      tx = await readStatus(txHash);
    } catch (e) {
      log(`  poll error: ${e.message}`);
    }
    const name = statusName(tx);
    if (name && name !== last) {
      log(`  status: ${name}`);
      last = name;
    }
    if (name && TERMINAL.has(name)) return { status: name, tx };
    await new Promise((r) => setTimeout(r, POLL_SECONDS * 1000));
  }
  return { status: "TIMEOUT", tx: null };
}

const contractAddress = process.argv[2];
const claim = process.argv[3];
const urlsJson = process.argv[4];
if (!contractAddress || !claim || !urlsJson) {
  console.error('usage: node scripts/analyze-studionet.mjs <address> "<claim>" \'<urlsJson>\'');
  process.exit(1);
}
if (!KEY_FILE) {
  console.error("EL_DEPLOYER_KEY_FILE is not set");
  process.exit(2);
}

/** Read the deployer key: raw hex, or JSON containing privateKey. */
function readPrivateKey(file) {
  const raw = fs.readFileSync(file, "utf8").trim();
  let candidate = raw;
  if (raw.startsWith("{")) {
    const parsed = JSON.parse(raw);
    candidate = parsed.privateKey ?? parsed.key ?? "";
    if (!candidate) throw new Error(`${file} has JSON but no privateKey field`);
  }
  if (!/^(0x)?[0-9a-fA-F]{64}$/.test(candidate)) {
    if (raw.startsWith("{") && /cipher|scrypt|kdf/i.test(raw)) {
      throw new Error(
        `${file} is an ENCRYPTED keystore; an unlocked private key is required`
      );
    }
    throw new Error(`${file} does not contain a 32-byte hex private key`);
  }
  return candidate.startsWith("0x") ? candidate : "0x" + candidate;
}

const account = createAccount(readPrivateKey(KEY_FILE));
const glClient = createClient({ chain: chains.studionet, endpoint: RPC_URL, account });

log(`network  : studionet (chain ${chains.studionet.id})`);
log(`rpc      : ${RPC_URL}`);
log(`sender   : ${account.address}`);
log(`contract : ${contractAddress}`);
log(`claim    : ${claim}`);
log(`urls     : ${urlsJson}`);

const schema = await glClient.getContractSchema(contractAddress);
const contract = glClient.createContract({ address: contractAddress, abi: schema.abi });
if (!contract.methods.analyze) throw new Error("analyze not present in deployed schema");

const before = Number(await contract.methods.get_case_count());
log(`case_count_before = ${before}`);

const res = await contract.methods.analyze(claim, urlsJson);
const txHash = typeof res === "string" ? res : (res.transactionHash ?? res.hash);
log(`WRITE_TX=${txHash}`);

const { status, tx } = await waitFinal(txHash);
log(`WRITE_STATUS=${status}`);
if (status !== "FINALIZED") {
  log(`raw tx: ${JSON.stringify(tx).slice(0, 2000)}`);
  throw new Error(`analyze did not finalize (${status})`);
}

const after = Number(await contract.methods.get_case_count());
log(`case_count_after = ${after}`);
const caseId = after - 1;
log(`CASE_ID=${caseId}`);

const caseData = await contract.methods.get_case(caseId);
log(`get_case = ${JSON.stringify(caseData)}`);
const sources = await contract.methods.get_sources(caseId);
log(`get_sources = ${JSON.stringify(sources, null, 2)}`);
log(`get_diversity_bps = ${await contract.methods.get_diversity_bps(caseId)}`);
log(`get_redundancy_bps = ${await contract.methods.get_redundancy_bps(caseId)}`);
log(`get_classification = ${await contract.methods.get_classification(caseId)}`);
log(`get_root_count = ${await contract.methods.get_root_count(caseId)}`);