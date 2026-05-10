use tauri::Emitter;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;
use std::env;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, Stdio};

fn emit_backend_line(handle: &tauri::AppHandle, line: &str) {
    let trimmed = line.trim();
    if trimmed.is_empty() || !trimmed.starts_with('{') {
        return;
    }

    let Ok(value) = serde_json::from_str::<serde_json::Value>(trimmed) else {
        return;
    };
    let Some(channel) = value.get("channel").and_then(|v| v.as_str()) else {
        return;
    };

    if channel == "alert" || channel == "raw_event" || channel == "system_info" {
        let _ = handle.emit(channel, trimmed);
    }
}

fn backend_main_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("backend")
        .join("main.py")
}

fn python_path() -> PathBuf {
    let venv_python = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join(".venv")
        .join("bin")
        .join("python");

    if venv_python.exists() {
        venv_python
    } else {
        PathBuf::from("python3")
    }
}

fn backend_args() -> Vec<String> {
    if let Ok(path) = env::var("SELD_DEMO_JSON") {
        if !path.trim().is_empty() {
            return vec!["--demo-json".to_string(), path];
        }
    }
    if let Ok(path) = env::var("SELD_DEMO_FILE") {
        if !path.trim().is_empty() {
            return vec!["--demo-file".to_string(), path];
        }
    }
    Vec::new()
}

fn backend_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("backend")
}

fn spawn_dev_backend(handle: tauri::AppHandle, args: Vec<String>) {
    let backend = backend_main_path();
    let python = python_path();
    let cwd = backend_dir();
    tauri::async_runtime::spawn_blocking(move || {
        let Ok(mut child) = Command::new(&python)
            .arg("-u")
            .arg(&backend)
            .args(&args)
            .current_dir(&cwd)
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
        else {
            eprintln!(
                "[backend] failed to spawn {} {}",
                python.display(),
                backend.display()
            );
            return;
        };

        if let Some(stdout) = child.stdout.take() {
            let reader = BufReader::new(stdout);
            for line in reader.lines().map_while(Result::ok) {
                emit_backend_line(&handle, &line);
            }
        }

        let _ = child.kill();
        let _ = child.wait();
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let args = backend_args();

            // Spawn the Python pipeline sidecar.
            // If it fails (e.g. binary not yet bundled in dev), log and continue —
            // the React mock feed handles the UI in that case.
            match app.shell().sidecar("seld-pipeline") {
                Err(e) => {
                    eprintln!("[sidecar] seld-pipeline not found, spawning dev backend: {e}");
                    spawn_dev_backend(handle.clone(), args);
                }
                Ok(cmd) => {
                    let cmd = if args.is_empty() { cmd } else { cmd.args(args.clone()) };
                    match cmd.spawn() {
                    Err(e) => {
                        eprintln!("[sidecar] failed to spawn seld-pipeline, spawning dev backend: {e}");
                        spawn_dev_backend(handle.clone(), args);
                    }
                    Ok((mut rx, child)) => {
                        tauri::async_runtime::spawn(async move {
                            while let Some(event) = rx.recv().await {
                                if let CommandEvent::Stdout(bytes) = event {
                                    if let Ok(line) = String::from_utf8(bytes) {
                                        for part in line.lines() {
                                            emit_backend_line(&handle, part);
                                        }
                                    }
                                }
                            }
                            let _ = child.kill();
                        });
                    }
                    }
                },
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
