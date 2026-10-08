//! Explicit process and named plates with a supplied process fallback model.
use super::*;

pub(super) fn space(
    writer: &mut Writer,
    profile: usize,
    inks: &crate::ink_recipes::Combined<'_>,
) -> Result<usize, Error> {
    channel_space(
        writer,
        profile,
        &inks
            .named
            .recipe
            .inks
            .iter()
            .zip(&inks.alternates)
            .map(|(ink, values)| (ink.id.clone(), *values))
            .collect::<Vec<_>>(),
    )
}
pub(super) fn channel_space(
    writer: &mut Writer,
    profile: usize,
    alternates: &[(String, [f64; 4])],
) -> Result<usize, Error> {
    let n = 4 + alternates.len();
    let alternate = format!("[/ICCBased {profile} 0 R]");
    let mut names = String::from("/Cyan /Magenta /Yellow /Black");
    let mut colorants = String::new();
    for (id, values) in alternates {
        // Retained objects qualify document-local ink IDs with slash-separated
        // placement paths. Escape name-token bytes, preserving decoded identity.
        let encoded: String = id
            .bytes()
            .map(|b| {
                if b.is_ascii_alphanumeric() || b"._-".contains(&b) {
                    (b as char).to_string()
                } else {
                    format!("#{b:02X}")
                }
            })
            .collect();
        let name = format!("/Inkbolt.{encoded}");
        names.push_str(&format!(" {name}"));
        let function = writer.add(format!(
            "<< /FunctionType 2 /Domain [0 1] /C0 [0 0 0 0] /C1 [{}] /N 1 >>",
            numbers(values)?
        ))?;
        colorants.push_str(&format!(
            "{name} [/Separation {name} {alternate} {function} 0 R] "
        ));
    }
    let mut program = String::from("{ ");
    for c in 0..4 {
        program.push_str(&format!("{} index 1 exch sub ", n - 1));
        for (i, (_, a)) in alternates.iter().enumerate() {
            program.push_str(&format!(
                "{} index {} mul 1 exch sub mul ",
                n - 4 - i + c,
                number(a[c])?
            ));
        }
        program.push_str("1 exch sub ");
    }
    program.push_str(&format!("{} 4 roll ", n + 4));
    for _ in 0..n {
        program.push_str("pop ");
    }
    program.push('}');
    let domain = std::iter::repeat_n("0 1", n).collect::<Vec<_>>().join(" ");
    let function = writer.stream(
        &format!("/FunctionType 4 /Domain [{domain}] /Range [0 1 0 1 0 1 0 1]"),
        program.as_bytes(),
    )?;
    writer.add(format!("[/DeviceN [{names}] {alternate} {function} 0 R << /Subtype /NChannel /Process << /ColorSpace {alternate} /Components [/Cyan /Magenta /Yellow /Black] >> /Colorants << {colorants} >> >>]"))
}
