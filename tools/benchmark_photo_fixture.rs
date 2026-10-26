//! Original integer studio scene. Standalone fixture generator; never links the engine.
use std::io::{self, Write};

const ONE: i64 = 65_536;

fn power(mut value: i64, mut exponent: u32) -> i64 {
    let mut result = ONE;
    while exponent != 0 {
        if exponent & 1 != 0 {
            result = result * value / ONE;
        }
        value = value * value / ONE;
        exponent >>= 1;
    }
    result
}

fn main() -> io::Result<()> {
    let args: Vec<usize> = std::env::args()
        .skip(1)
        .map(|s| s.parse().expect("integer fixture extent"))
        .collect();
    assert!(args.len() == 6);
    let (width, height, px, py, pw, ph) = (args[0], args[1], args[2], args[3], args[4], args[5]);
    assert!(width > 0 && height > 0 && width <= 8192 && height <= 8192);
    assert!(px + pw <= width && py + ph <= height && pw > 0 && ph > 0);
    let objects = [
        (800, 630, 88, 175, [40000, 15000, 8000]),
        (320, 510, 130, 295, [8000, 28000, 33000]),
        (640, 570, 140, 245, [56000, 28000, 6000]),
    ];
    let xs: Vec<i64> = (0..width)
        .map(|x| x as i64 * 1024 * ONE / width as i64)
        .collect();
    let mut output = io::BufWriter::new(io::stdout().lock());
    let mut row = vec![0u8; width * 8];
    for y in 0..height {
        let sy = y as i64 * 1024 * ONE / height as i64;
        for (x, &sx) in xs.iter().enumerate() {
            let mut field =
                22000 + 6000 * (height - y) as i64 / height as i64 + 1800 * x as i64 / width as i64;
            for &(cx, cy, rx, ry, _) in &objects {
                let nx = (sx - (cx + 35) * ONE) / (rx + rx / 8);
                let ny = (sy - (cy + ry * 9 / 10) * ONE) / (ry / 5);
                let q = nx * nx + ny * ny;
                if q < ONE * ONE * 4 {
                    let shade = (ONE * ONE * 4 - q) / (ONE * 4);
                    field = field * (ONE - shade * 2 / 5) / ONE;
                }
            }
            let mut rgb = [field * 106 / 100, field * 102 / 100, field * 98 / 100];
            for &(cx, cy, rx, ry, color) in &objects {
                let nx = (sx - cx * ONE) / rx;
                let ny = (sy - cy * ONE) / ry;
                let q = nx * nx + ny * ny;
                if q >= ONE * ONE {
                    continue;
                }
                let nz = ((ONE * ONE - q) as u64).isqrt() as i64;
                let diffuse = 14000 + 51000 * ((-45 * nx - 60 * ny + 66 * nz) / 100).max(0) / ONE;
                let specular =
                    36000 * power(((-25 * nx - 32 * ny + 91 * nz) / 100).clamp(0, ONE), 80) / ONE;
                let radius = (rx * width as i64 / 1024).min(ry * height as i64 / 1024);
                let coverage = ((ONE * ONE - q) * radius / (2 * ONE)).min(ONE);
                for (out, base) in rgb.iter_mut().zip(color) {
                    let value = base * diffuse / ONE + specular;
                    *out = (*out * (ONE - coverage) + value * coverage) / ONE;
                }
            }
            let noise = (x as u32).wrapping_mul(73856093) ^ (y as u32).wrapping_mul(19349663);
            let noise = (noise ^ (noise >> 13)).wrapping_mul(1274126177);
            let grain = (noise % 197) as i64 - 98;
            for (component, value) in rgb.into_iter().enumerate() {
                let value = if (px..px + pw).contains(&x) && (py..py + ph).contains(&y) {
                    [61003, 4007, 54011][component]
                } else {
                    (value + grain).clamp(0, 65535) as u16
                };
                row[x * 8 + component * 2..x * 8 + component * 2 + 2]
                    .copy_from_slice(&value.to_le_bytes());
            }
            row[x * 8 + 6..x * 8 + 8].copy_from_slice(&65535u16.to_le_bytes());
        }
        output.write_all(&row)?;
    }
    output.flush()
}
