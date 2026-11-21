// Impede uma janela de consola adicional no Windows em release (sem efeito no macOS).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    uanji_core_lib::run()
}
