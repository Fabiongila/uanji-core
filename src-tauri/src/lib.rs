//! Processo desktop do UANJI CORE.
//!
//! Responsabilidades:
//! - Escolher uma porta livre em 127.0.0.1 e gerar um token aleatório por sessão.
//! - Lançar o backend Python (executável empacotado em produção; venv em desenvolvimento)
//!   com `UANJI_PORT`, `UANJI_TOKEN` e `UANJI_DATA_DIR`.
//! - Entregar `{ baseUrl, token }` ao frontend através do comando `backend_config`.
//! - Terminar o backend quando a aplicação fecha (e o backend termina sozinho se este
//!   processo desaparecer: `UANJI_WATCH_PARENT=1`).

use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{Manager, RunEvent};

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendConfig {
    base_url: String,
    token: String,
}

struct Backend {
    config: BackendConfig,
    port: u16,
    child: Mutex<Option<Child>>,
}

/// Porta preferida estável (o endereço dos webhooks não muda entre arranques); outra livre se estiver ocupada.
const PREFERRED_PORT: u16 = 48765;

fn free_port() -> std::io::Result<u16> {
    if let Ok(listener) = TcpListener::bind(("127.0.0.1", PREFERRED_PORT)) {
        return Ok(listener.local_addr()?.port());
    }
    let listener = TcpListener::bind("127.0.0.1:0")?;
    Ok(listener.local_addr()?.port())
}

fn random_token() -> String {
    let mut bytes = [0u8; 32];
    getrandom::getrandom(&mut bytes).expect("gerador aleatório do sistema indisponível");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn wait_ready(port: u16, timeout: Duration) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(250)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

/// Em desenvolvimento usa o Python do ambiente virtual; em produção o executável empacotado.
fn backend_command(app: &tauri::AppHandle) -> Result<Command, String> {
    if cfg!(debug_assertions) {
        let backend_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend");
        let python = backend_dir.join(".venv/bin/python");
        let mut cmd = Command::new(python);
        cmd.arg("-m").arg("uanji").current_dir(backend_dir);
        Ok(cmd)
    } else {
        let exe = app
            .path()
            .resource_dir()
            .map_err(|e| format!("pasta de recursos indisponível: {e}"))?
            .join("uanji-backend/uanji-backend");
        if !exe.exists() {
            return Err(format!("backend não encontrado em {}", exe.display()));
        }
        Ok(Command::new(exe))
    }
}

fn start_backend(app: &tauri::AppHandle) -> Result<Backend, String> {
    let port = free_port().map_err(|e| format!("sem porta local livre: {e}"))?;
    let token = random_token();
    // Em desenvolvimento, dados isolados no repositório; em produção, a pasta da aplicação.
    let data_dir = if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.dev-data-desktop")
    } else {
        app.path()
            .app_data_dir()
            .map_err(|e| format!("pasta de dados indisponível: {e}"))?
    };
    std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;

    let mut cmd = backend_command(app)?;
    cmd.env("UANJI_PORT", port.to_string())
        .env("UANJI_TOKEN", &token)
        .env("UANJI_DATA_DIR", &data_dir)
        .env("UANJI_ENV", if cfg!(debug_assertions) { "development" } else { "production" })
        .env("UANJI_WATCH_PARENT", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        // Os logs estruturados ficam em <dados>/logs/backend.log.
        .stderr(Stdio::null());
    let child = cmd.spawn().map_err(|e| format!("falha ao lançar o backend: {e}"))?;

    Ok(Backend {
        config: BackendConfig { base_url: format!("http://127.0.0.1:{port}"), token },
        port,
        child: Mutex::new(Some(child)),
    })
}

#[tauri::command]
async fn backend_config(state: tauri::State<'_, Backend>) -> Result<BackendConfig, String> {
    let port = state.port;
    // Espera (sem bloquear a interface) que o backend aceite ligações.
    let ready = tauri::async_runtime::spawn_blocking(move || wait_ready(port, Duration::from_secs(45)))
        .await
        .unwrap_or(false);
    if !ready {
        return Err("O backend local não respondeu a tempo. Consulte os logs em Definições → Diagnóstico.".into());
    }
    Ok(state.config.clone())
}

fn stop_backend(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<Backend>() {
        if let Some(mut child) = state.child.lock().ok().and_then(|mut c| c.take()) {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let backend = start_backend(app.handle()).map_err(|e| {
                log::error!("{e}");
                e
            })?;
            app.manage(backend);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_config])
        .build(tauri::generate_context!())
        .expect("erro ao iniciar o UANJI CORE");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_backend(handle);
        }
    });
}
