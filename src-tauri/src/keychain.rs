//! API key storage via the OS keychain (Keychain on macOS, Credential
//! Manager on Windows, Secret Service on Linux) using the `keyring` crate.
//!
//! This replaces the originally-planned "encrypted at rest" custom scheme
//! flagged during the build-plan review — rolling your own encryption for
//! secrets is exactly the kind of thing that quietly becomes a
//! vulnerability. The OS keychain is battle-tested and free.

use keyring::Entry;

const SERVICE_NAME: &str = "com.agentforge.app";

fn entry_for(provider: &str) -> Result<Entry, String> {
    Entry::new(SERVICE_NAME, provider).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn save_api_key(provider: String, key: String) -> Result<(), String> {
    let entry = entry_for(&provider)?;
    entry.set_password(&key).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_api_key(provider: String) -> Result<Option<String>, String> {
    let entry = entry_for(&provider)?;
    match entry.get_password() {
        Ok(pass) => Ok(Some(pass)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
pub fn delete_api_key(provider: String) -> Result<(), String> {
    let entry = entry_for(&provider)?;
    match entry.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
