use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use chrono::{DateTime, Duration, Utc};
use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use rand_core::OsRng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::models::{ActionIntent, ResourceScope};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityClaims {
    pub version: u8,
    pub key_id: String,
    pub audience: String,
    pub executor_id: String,
    pub device_id: String,
    pub session_id: String,
    pub task_id: String,
    pub node_id: Option<String>,
    pub action_id: String,
    pub action_hash: String,
    pub capability_name: String,
    pub resource_scope: Vec<ResourceScope>,
    pub parameter_hash: String,
    pub approval_id: Option<String>,
    pub issued_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub nonce: String,
    pub max_uses: u8,
}

pub struct CapabilitySigner {
    key_id: String,
    key: SigningKey,
}

impl CapabilitySigner {
    pub fn generate(key_id: impl Into<String>) -> Self {
        Self { key_id: key_id.into(), key: SigningKey::generate(&mut OsRng) }
    }

    pub fn verifying_key(&self) -> VerifyingKey { self.key.verifying_key() }

    pub fn issue(&self, action: &ActionIntent, session_id: &str, executor_id: &str, device_id: &str, approval_id: Option<String>, ttl_secs: i64) -> anyhow::Result<String> {
        let now = Utc::now();
        let action_json = serde_json::to_vec(action)?;
        let parameter_json = serde_json::to_vec(&action.parameters)?;
        let claims = CapabilityClaims {
            version: 1,
            key_id: self.key_id.clone(),
            audience: "systemai-executor".into(),
            executor_id: executor_id.into(),
            device_id: device_id.into(),
            session_id: session_id.into(),
            task_id: action.task_id.clone(),
            node_id: action.node_id.clone(),
            action_id: action.action_id.clone(),
            action_hash: hex_sha256(&action_json),
            capability_name: action.capability.clone(),
            resource_scope: action.resource_scope.clone(),
            parameter_hash: hex_sha256(&parameter_json),
            approval_id,
            issued_at: now,
            expires_at: now + Duration::seconds(ttl_secs),
            nonce: Uuid::new_v4().simple().to_string(),
            max_uses: 1,
        };
        let payload = serde_json::to_vec(&claims)?;
        let sig = self.key.sign(&payload);
        Ok(format!("cap1.{}.{}", URL_SAFE_NO_PAD.encode(payload), URL_SAFE_NO_PAD.encode(sig.to_bytes())))
    }
}

pub fn verify(token: &str, key: &VerifyingKey) -> anyhow::Result<CapabilityClaims> {
    let parts: Vec<_> = token.split('.').collect();
    anyhow::ensure!(parts.len() == 3 && parts[0] == "cap1", "bad token format");
    let payload = URL_SAFE_NO_PAD.decode(parts[1])?;
    let sig_bytes = URL_SAFE_NO_PAD.decode(parts[2])?;
    let sig = Signature::from_slice(&sig_bytes)?;
    key.verify(&payload, &sig)?;
    let claims: CapabilityClaims = serde_json::from_slice(&payload)?;
    anyhow::ensure!(claims.expires_at > Utc::now(), "token expired");
    Ok(claims)
}

fn hex_sha256(data: &[u8]) -> String {
    let digest = Sha256::digest(data);
    digest.iter().map(|b| format!("{:02x}", b)).collect()
}
