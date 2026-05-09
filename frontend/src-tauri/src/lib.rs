use tauri::Emitter;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // Spawn the Python pipeline sidecar.
            // If it fails (e.g. binary not yet bundled in dev), log and continue —
            // the React mock feed handles the UI in that case.
            match app.shell().sidecar("seld-pipeline") {
                Err(e) => {
                    eprintln!("[sidecar] seld-pipeline not found, running in UI-only mode: {e}");
                }
                Ok(cmd) => match cmd.spawn() {
                    Err(e) => {
                        eprintln!("[sidecar] failed to spawn seld-pipeline: {e}");
                    }
                    Ok((mut rx, _child)) => {
                        tauri::async_runtime::spawn(async move {
                            while let Some(event) = rx.recv().await {
                                if let CommandEvent::Stdout(bytes) = event {
                                    if let Ok(line) = String::from_utf8(bytes) {
                                        let line = line.trim().to_string();
                                        if !line.is_empty() {
                                            // Forward the raw JSON string to the React frontend.
                                            let _ = handle.emit("alert", line);
                                        }
                                    }
                                }
                            }
                        });
                    }
                },
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
