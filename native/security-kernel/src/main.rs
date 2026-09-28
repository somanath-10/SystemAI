use std::io::{self, BufRead, Write};

use systemai_security_kernel::models::{ActionIntent, CapabilityDefinition};
use systemai_security_kernel::policy::canonicalize;

fn main() -> anyhow::Result<()> {
    // Development JSONL adapter. Production deployment should place this logic
    // behind authenticated Unix-domain-socket / Windows named-pipe IPC.
    let stdin = io::stdin();
    let mut stdout = io::stdout().lock();
    for line in stdin.lock().lines() {
        let line = line?;
        if line.trim().is_empty() { continue; }
        let req: serde_json::Value = serde_json::from_str(&line)?;
        let op = req.get("op").and_then(|x| x.as_str()).unwrap_or("");
        let response = match op {
            "health" => serde_json::json!({"ok": true, "version": env!("CARGO_PKG_VERSION")}),
            "canonicalize" => {
                let action: ActionIntent = serde_json::from_value(req.get("action").cloned().unwrap_or_default())?;
                let capability: CapabilityDefinition = serde_json::from_value(req.get("capability").cloned().unwrap_or_default())?;
                serde_json::to_value(canonicalize(&action, &capability))?
            }
            _ => serde_json::json!({"error": "unsupported operation"}),
        };
        writeln!(stdout, "{}", serde_json::to_string(&response)?)?;
        stdout.flush()?;
    }
    Ok(())
}
