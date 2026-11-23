//! Opaque process paints and linear one-dimensional spot tints.
use super::*;
use crate::swatches::{Definition, Process, Swatch};

pub(super) type Swatches = BTreeMap<String, Swatch>;

fn declare(swatches: &mut Swatches, id: &str, swatch: Swatch) -> Result<(), Error> {
    if let Some(old) = swatches.get(id) {
        if old != &swatch {
            return Err(unsupported(
                "Conflicting alternate colors for one PDF plate",
            ));
        }
    } else {
        if swatches.len() >= crate::swatches::MAX_SWATCHES {
            return Err(limit("PDF paint exceeds the named swatch limit"));
        }
        swatches.insert(id.to_owned(), swatch);
    }
    Ok(())
}

fn cmyk(components: [f64; 4]) -> Process {
    Process::Cmyk {
        components,
        preview_srgb: None,
    }
}

pub(super) fn process(swatches: &mut Swatches, components: [f64; 4]) -> Result<String, Error> {
    let [c, m, y, k] = components.map(|v| if v == 0.0 { 0 } else { v.to_bits() });
    let id = format!("pdf-process-{c:016x}{m:016x}{y:016x}{k:016x}");
    declare(
        swatches,
        &id,
        Swatch {
            name: "Process CMYK".into(),
            pdf_colorant: None,
            definition: Definition::Process {
                color: cmyk(components),
            },
        },
    )?;
    Ok(id)
}

pub(super) fn separation(
    pdf: &Container,
    parts: &[Value],
    swatches: &mut Swatches,
    remaining: &mut usize,
    control: &Control,
) -> Result<String, Error> {
    let [_, name, base, function] = parts else {
        return Err(invalid("Expected four PDF Separation entries"));
    };
    let Value::Name(name) = pdf.resolve(name)? else {
        return Err(invalid("Expected PDF separation name"));
    };
    let plate = std::str::from_utf8(name)
        .map_err(|_| unsupported("PDF plate name requires printable UTF-8"))?;
    if !pdf.resolve(base)?.named(b"DeviceCMYK") || !crate::swatches::valid_pdf_colorant(plate) {
        return Err(unsupported("Expected a named spot with a CMYK alternate"));
    }
    let id = format!("pdf-spot-{}", crate::assets::sha256(name));
    let components = tint_ramp(pdf, function, remaining, control)?;
    declare(
        swatches,
        &id,
        Swatch {
            name: plate.into(),
            pdf_colorant: Some(plate.into()),
            definition: Definition::Spot {
                alternate: cmyk(components),
            },
        },
    )?;
    Ok(id)
}

fn tint_ramp(
    pdf: &Container,
    function: &Value,
    remaining: &mut usize,
    control: &Control,
) -> Result<[f64; 4], Error> {
    let stream = match function {
        Value::Ref(id) => pdf.stream_dict(*id).ok().map(|d| (*id, d)),
        _ => None,
    };
    let d = match stream {
        Some((_, d)) => d,
        None => pdf.resolve(function)?.dict()?,
    };
    if numbers::<2>(pdf, field(d, b"Domain")?)? != [0., 1.] {
        return Err(unsupported("PDF spot tint domain must cover zero to one"));
    }
    let range = d
        .get(b"Range".as_slice())
        .map(|v| numbers::<8>(pdf, v))
        .transpose()?;
    if range.is_some_and(|v| v != [0., 1., 0., 1., 0., 1., 0., 1.]) {
        return Err(unsupported(
            "PDF spot tint requires four unit output ranges",
        ));
    }
    match (pdf.resolve(field(d, b"FunctionType")?)?.integer()?, stream) {
        (2, None) => {
            allowed(
                d,
                &[b"FunctionType", b"Domain", b"Range", b"N", b"C0", b"C1"],
            )?;
            let end = numbers::<4>(pdf, field(d, b"C1")?)?;
            if number(pdf.resolve(field(d, b"N")?)?)? != 1.
                || numbers::<4>(pdf, field(d, b"C0")?)? != [0.; 4]
                || !end.iter().all(|v| (0. ..=1.).contains(v))
            {
                return Err(unsupported(
                    "Expected linear PDF spot tint from paper to full ink",
                ));
            }
            Ok(end)
        }
        (4, Some((id, _))) if range.is_some() => {
            allowed(
                d,
                &[
                    b"FunctionType",
                    b"Domain",
                    b"Range",
                    b"Length",
                    b"Filter",
                    b"DecodeParms",
                ],
            )?;
            let bytes =
                filters::stream(pdf, id, bounds::MAX_TINT_FUNCTION_BYTES, remaining, control)?;
            *remaining -= bytes.len();
            linear_calculator(&bytes)
        }
        _ => Err(unsupported("Unsupported PDF spot tint function")),
    }
}

/// Prove a tint ramp symbolically. Every intermediate is either a constant
/// or a coefficient times the original tint. Never run a calculator program.
fn linear_calculator(bytes: &[u8]) -> Result<[f64; 4], Error> {
    #[derive(Clone, Copy)]
    enum Term {
        Constant(f64),
        Tint(f64),
    }
    use Term::*;
    let fail = || unsupported("Unsupported PDF calculator spot tint ramp");
    let whitespace = |c: char| matches!(c, '\0' | '\t' | '\n' | '\x0c' | '\r' | ' ');
    let text = std::str::from_utf8(bytes)
        .map_err(|_| fail())?
        .trim_matches(whitespace);
    let body = text
        .strip_prefix('{')
        .and_then(|v| v.strip_suffix('}'))
        .ok_or_else(fail)?;
    let mut stack = vec![Tint(1.)];
    for token in body.split(whitespace).filter(|v| !v.is_empty()) {
        match token {
            "dup" => stack.push(*stack.last().ok_or_else(fail)?),
            "pop" => {
                stack.pop().ok_or_else(fail)?;
            }
            "exch" => {
                let n = stack.len().checked_sub(2).ok_or_else(fail)?;
                stack.swap(n, n + 1);
            }
            "mul" => {
                let b = stack.pop().ok_or_else(fail)?;
                let a = stack.pop().ok_or_else(fail)?;
                stack.push(match (a, b) {
                    (Constant(a), Constant(b)) => Constant(a * b),
                    (Tint(a), Constant(b)) | (Constant(b), Tint(a)) => Tint(a * b),
                    _ => return Err(fail()),
                });
            }
            _ => {
                let v = program::scalar(token.as_bytes()).map_err(|_| fail())?;
                if !(0. ..=1.).contains(&v) {
                    return Err(fail());
                }
                stack.push(Constant(v));
            }
        }
        if stack.len() > crate::limits::vector_native::MAX_OPERANDS {
            return Err(limit("PDF tint operand limit exceeded"));
        }
    }
    let terms: [Term; 4] = stack.try_into().map_err(|_| fail())?;
    let mut result = [0.; 4];
    for (out, term) in result.iter_mut().zip(terms) {
        *out = match term {
            Tint(v) => v,
            Constant(0.) => 0.,
            _ => return Err(fail()),
        };
    }
    Ok(result)
}
