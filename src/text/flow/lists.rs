//! Source-independent list counters and pinned-font marker placement.
use super::*;

pub const MAX_LEVELS: usize = 9;
pub const MAX_LISTS: usize = 64;
pub const MAX_COUNTER: u32 = 999_999;
pub const MAX_AFFIX: usize = 32;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Format {
    Decimal,
    LowerAlpha,
    UpperAlpha,
    LowerRoman,
    UpperRoman,
}
fn suffix() -> String {
    ".".into()
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Marker {
    Bullet {
        text: String,
    },
    Ordered {
        format: Format,
        #[serde(default)]
        prefix: String,
        #[serde(default = "suffix")]
        suffix: String,
    },
}
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct List {
    pub id: String,
    #[serde(default)]
    pub level: usize,
    pub marker: Marker,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restart: Option<u32>,
    #[serde(default)]
    pub gap: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub style: Option<Style>,
}
#[derive(Clone, Debug, Serialize)]
pub struct Label {
    pub id: String,
    pub level: usize,
    pub counters: Vec<u32>,
    pub text: String,
}
#[derive(Debug, Serialize)]
pub struct Placement {
    #[serde(flatten)]
    pub label: Label,
    pub x: f64,
    pub advance: f64,
    pub glyph_start: usize,
    pub glyph_end: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bidi: Option<bidi::Line>,
}
pub(super) struct Prepared {
    pub frame: Frame,
    pub glyphs: Vec<Shaped>,
    pub advance: f64,
    label: Label,
    bidi: Option<bidi::Line>,
}
fn invalid(message: &str) -> Error {
    Error::new("INVALID_LIST", message)
}
fn literal(text: &str) -> Result<(), Error> {
    if text.chars().count() > MAX_AFFIX
        || text.chars().any(|c| {
            c.is_control()
                || bidi::is_control(c)
                || matches!(c, '\u{2028}' | '\u{2029}' | '\u{fffe}' | '\u{ffff}')
        })
    {
        return Err(invalid(
            "List bullet/prefix/suffix must have at most 32 scalars without controls or separators",
        ));
    }
    Ok(())
}
fn number(mut value: u32, format: Format) -> Result<String, Error> {
    match format {
        Format::Decimal => Ok(value.to_string()),
        Format::LowerAlpha | Format::UpperAlpha => {
            let mut chars = Vec::new();
            while value > 0 {
                value -= 1;
                chars.push((b'A' + (value % 26) as u8) as char);
                value /= 26;
            }
            let text: String = chars.into_iter().rev().collect();
            Ok(if format == Format::LowerAlpha {
                text.to_ascii_lowercase()
            } else {
                text
            })
        }
        Format::LowerRoman | Format::UpperRoman => {
            if value > 3999 {
                return Err(invalid("Roman list counters must be in 1..=3999"));
            }
            let mut text = String::new();
            for (n, symbol) in [
                (1000, "M"),
                (900, "CM"),
                (500, "D"),
                (400, "CD"),
                (100, "C"),
                (90, "XC"),
                (50, "L"),
                (40, "XL"),
                (10, "X"),
                (9, "IX"),
                (5, "V"),
                (4, "IV"),
                (1, "I"),
            ] {
                while value >= n {
                    text.push_str(symbol);
                    value -= n;
                }
            }
            Ok(if format == Format::LowerRoman {
                text.to_ascii_lowercase()
            } else {
                text
            })
        }
    }
}
pub(super) fn resolve(story: &Story) -> Result<Vec<Option<Label>>, Error> {
    let mut states: BTreeMap<&str, Vec<u32>> = BTreeMap::new();
    story.paragraphs.iter().map(|p| {
        let Some(list) = &p.list else { return Ok(None); };
        if !valid_id(&list.id) || list.level >= MAX_LEVELS
            || list.restart.is_some_and(|v| !(1..=MAX_COUNTER).contains(&v))
            || !list.gap.is_finite() || !(0.0..=32768.0).contains(&list.gap)
        {
            return Err(invalid("List requires a valid ID, level 0..=8, restart 1..=999999 and finite gap 0..=32768"));
        }
        let state = states.entry(&list.id).or_default();
        if list.level > state.len() {
            return Err(invalid("Nested list items require a preceding parent at every lower level"));
        }
        let value = list.restart.unwrap_or_else(|| state.get(list.level).map_or(1, |v| v + 1));
        if value > MAX_COUNTER { return Err(invalid("List counter exceeds 999999; explicitly restart it")); }
        state.truncate(list.level);
        state.push(value);
        let text = match &list.marker {
            Marker::Bullet { text } => {
                literal(text)?;
                if text.chars().all(char::is_whitespace) { return Err(invalid("List bullet must contain non-whitespace text")); }
                text.clone()
            }
            Marker::Ordered { format, prefix, suffix } => {
                literal(prefix)?;
                literal(suffix)?;
                format!("{prefix}{}{suffix}", number(value, *format)?)
            }
        };
        let label = Label { id:list.id.clone(), level:list.level, counters:state.clone(), text };
        if states.len() > MAX_LISTS { return Err(limit("Story exceeds 64 independent list IDs")); }
        Ok(Some(label))
    }).collect()
}
pub(super) fn frame(p: &Paragraph, label: &Label, direction: Direction) -> Frame {
    Frame {
        text: label.text.clone(),
        style: p
            .list
            .as_ref()
            .unwrap()
            .style
            .as_ref()
            .unwrap_or(&p.style)
            .clone(),
        ranges: Vec::new(),
        direction,
        bidi: p.bidi,
        align: Align::Left,
        wrap: false,
        leading: None,
        ..p.frame()
    }
}
pub(super) fn prepare(
    p: &Paragraph,
    label: &Label,
    direction: Direction,
    d: &Document,
    cache: &fonts::Cache,
    work: &mut usize,
) -> Result<Prepared, Error> {
    let frame = frame(p, label, direction);
    let analysis = Analysis::new(&frame)?;
    let end = frame.text.chars().count();
    let (glyphs, advance) = shape(&frame, &analysis, 0, end, d, cache, work)?;
    let bidi = analysis.line(0, end)?;
    Ok(Prepared {
        frame,
        glyphs,
        advance,
        label: label.clone(),
        bidi,
    })
}
pub(super) fn append(
    m: Prepared,
    target: &mut Layout,
    x: f64,
    baseline: f64,
    d: &Document,
    cache: &fonts::Cache,
    commands: &mut usize,
) -> Result<Placement, Error> {
    let glyph_start = target.glyphs.len();
    append_glyphs(
        &m.frame,
        d,
        cache,
        target,
        m.glyphs,
        [x, baseline],
        commands,
    )?;
    for g in &mut target.glyphs[glyph_start..] {
        g.generated = Some(Generated::ListMarker {
            start: g.start,
            end: g.end,
        });
        g.start = 0;
        g.end = 0;
    }
    Ok(Placement {
        label: m.label,
        x,
        advance: m.advance,
        glyph_start,
        glyph_end: target.glyphs.len(),
        bidi: m.bidi,
    })
}
