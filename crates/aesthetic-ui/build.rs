use std::path::{Path, PathBuf};

fn main() {
    println!("cargo:rerun-if-changed=../../tools/ffmpeg.exe");

    // Copy tools/ffmpeg.exe to target output dir (target/debug or target/release)
    if let Ok(out_dir) = std::env::var("OUT_DIR") {
        let out_path = PathBuf::from(out_dir);
        // OUT_DIR is typically: <target_dir>/<profile>/build/aesthetic-ui-<hash>/out
        if let Some(target_dir) = out_path.ancestors().nth(3) {
            let src = Path::new("../../tools/ffmpeg.exe");
            if src.exists() {
                let dest = target_dir.join("ffmpeg.exe");
                let _ = std::fs::copy(src, dest);
            }
        }
    }
}
